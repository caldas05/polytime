"""Local web UI for polytime — drag-drop a MIDI, preview, configure, generate.

Run:   python app.py
Build: build.bat  (PyInstaller --onefile --noconsole)
"""
from __future__ import annotations
import base64
import json
import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, sys._MEIPASS)

from polytime import (  # noqa: E402
    polytime, detect_time_signature, detect_bpm, _parse_when, parse_scale,
)
from model.measure import TimeSignature  # noqa: E402


VIZ_CACHE: dict[str, bytes] = {}

# Auto-shutdown: the browser pings /heartbeat every few seconds. If we go
# HEARTBEAT_TIMEOUT_S without a ping, the server exits — so closing the tab
# (or the whole browser) doesn't leave a zombie process holding the port.
LAST_HEARTBEAT = time.monotonic()
HEARTBEAT_TIMEOUT_S = 20.0
HEARTBEAT_CHECK_S = 5.0


INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>polytime</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;padding:18px;background:#1a1a1a;color:#eee}
 h1{margin:0 0 14px;font-size:20px}
 #drop{border:2px dashed #555;border-radius:8px;padding:24px;text-align:center;
       cursor:pointer;background:#222;transition:.15s}
 #drop.hover{border-color:#7af;background:#2a3040}
 #drop input{display:none}
 .row{display:flex;gap:14px;margin:12px 0;flex-wrap:wrap;align-items:end}
 label{display:flex;flex-direction:column;font-size:13px;color:#aaa}
 label.inline{flex-direction:row;align-items:center;gap:6px;color:#ddd}
 input[type=text],input[type=number]{margin-top:4px;padding:6px 8px;background:#222;
   color:#eee;border:1px solid #444;border-radius:4px;font:inherit;width:110px}
 button{padding:8px 16px;background:#4a7;color:#000;border:0;border-radius:4px;
        font:inherit;font-weight:600;cursor:pointer}
 button:disabled{background:#555;color:#888;cursor:wait}
 button.dl{background:#7af}
 #status{margin:6px 0;font-size:13px;color:#aaa;min-height:1.2em}
 #status.err{color:#f77}
 .vizpane{display:flex;flex-direction:column;gap:10px;margin-top:10px}
 .vizpane h3{margin:0 0 4px;font-size:13px;color:#aaa;font-weight:500}
 iframe{width:100%;height:46vh;border:1px solid #333;border-radius:4px;background:#fff}
 iframe.empty{background:#222;border-style:dashed}
</style></head>
<body>
<h1>polytime — rhythm-scaled MIDI echoes</h1>
<div id="drop">
  <div>Drop a .mid file here, or click to choose</div>
  <div id="picked" style="margin-top:6px;color:#7af;font-size:13px"></div>
  <input id="file" type="file" accept=".mid,.midi,audio/midi" style="display:none">
</div>
<div id="recBox" style="margin-top:10px;padding:10px;border:1px solid #333;
     border-radius:6px;background:#1f1f1f;display:none">
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <strong style="font-size:13px;color:#bbb">MIDI keyboard:</strong>
    <span id="recDevice" style="font-size:12px;color:#7af">searching…</span>
    <button id="recBtn" disabled>● Record</button>
    <button id="recStop" disabled>■ Stop</button>
    <label class="inline">bpm
      <input id="recBpm" type="number" value="120" min="20" max="400" style="width:70px">
    </label>
    <span id="recStatus" style="font-size:12px;color:#aaa"></span>
  </div>
</div>
<div id="recNotSupported" style="margin-top:6px;font-size:12px;color:#888;display:none">
  MIDI keyboard input requires Chrome, Edge, Opera, or Brave (Web MIDI API).
</div>
<div class="row">
  <label>at (entry per voice, comma-sep — or one value = staggered)
    <input id="at" type="text" value="2b" placeholder="2b   or   2b, 5b, 9b" style="width:240px">
  </label>
  <label>scales (one per echo voice — fractions, decimals, sqrt(2), 60bpm…)
    <input id="scales" type="text" value="3/2" placeholder="3/2, 1.5, sqrt(2), 60bpm" style="width:320px">
  </label>
  <label>time sig (optional)
    <input id="tsig" type="text" placeholder="auto — e.g. 5/4">
  </label>
  <label class="inline">
    <input id="combine" type="checkbox" checked> include original in MIDI
  </label>
  <button id="go">Generate</button>
  <button id="dl" class="dl" style="display:none">Download MIDI</button>
  <button id="quit" style="background:#444;color:#ccc;margin-left:auto"
          title="Stop the server and close polytime">× Quit</button>
</div>
<div id="status"></div>
<div class="vizpane">
  <div><h3>before (loaded MIDI)</h3><iframe id="vizBefore" class="empty" sandbox="allow-scripts"></iframe></div>
  <div><h3>after (echoes)</h3><iframe id="vizAfter" class="empty" sandbox="allow-scripts"></iframe></div>
</div>
<script>
const $=(id)=>document.getElementById(id);
const drop=$('drop'), file=$('file'), picked=$('picked'),
      go=$('go'), dl=$('dl'), st=$('status'),
      vizB=$('vizBefore'), vizA=$('vizAfter');
let chosen=null, dlUrl=null, dlName=null;

function setStatus(msg, err=false){st.textContent=msg;st.className=err?'err':'';}

async function pickFile(f){
  chosen=f; picked.textContent=f.name;
  vizA.src='about:blank'; vizA.classList.add('empty');
  dl.style.display='none';
  setStatus('loading preview...');
  const fd=new FormData(); fd.append('mid', f);
  try{
    const r=await fetch('/preview',{method:'POST',body:fd});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error||'preview failed');
    vizB.src='/viz/'+j.viz_token; vizB.classList.remove('empty');
    $('tsig').placeholder='auto — detected '+j.detected_ts;
    setStatus('detected time signature: '+j.detected_ts);
  }catch(e){setStatus('error: '+e.message, true);}
}

// preventDefault on the whole window so the browser never tries to navigate
// to a dropped file (which is what eats the first drop event).
['dragenter','dragover','drop'].forEach(ev=>
  window.addEventListener(ev, e=>e.preventDefault()));
drop.addEventListener('click',()=>file.click());
file.addEventListener('change',e=>{if(e.target.files[0])pickFile(e.target.files[0]);});
drop.addEventListener('dragenter',e=>{e.preventDefault();drop.classList.add('hover');});
drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('hover');});
drop.addEventListener('dragleave',e=>{drop.classList.remove('hover');});
drop.addEventListener('drop',e=>{
  e.preventDefault();
  drop.classList.remove('hover');
  const f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];
  if(f) pickFile(f);
});

go.addEventListener('click',async()=>{
  if(!chosen){setStatus('pick a MIDI file first', true);return;}
  go.disabled=true; dl.style.display='none';
  setStatus('processing...');
  const fd=new FormData();
  fd.append('mid', chosen);
  fd.append('at', $('at').value);
  fd.append('scales', $('scales').value);
  fd.append('tsig', $('tsig').value);
  fd.append('combine', $('combine').checked ? '1' : '0');
  try{
    const r=await fetch('/process',{method:'POST',body:fd});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error||'failed');
    setStatus('time signature: '+j.detected_ts);
    // Scale the after-iframe height with the number of viz rows so each row
    // gets enough vertical space even with many echo voices.
    // Matplotlib renders ~180px per row at 100dpi (figsize 1.8" per row).
    // Give a touch more headroom for the title/xlabel padding.
    const perRow = 200;
    vizA.style.height = Math.max(320, perRow * (j.n_rows || 1) + 80) + 'px';
    vizA.src='/viz/'+j.viz_token; vizA.classList.remove('empty');
    dlUrl=j.midi_data_url; dlName=j.midi_filename;
    dl.style.display='inline-block';
  }catch(e){setStatus('error: '+e.message, true);}
  finally{go.disabled=false;}
});
dl.addEventListener('click',()=>{
  if(!dlUrl)return;
  const a=document.createElement('a');a.href=dlUrl;a.download=dlName;a.click();
});

// Keep-alive: ping every 5s so the server knows we're still here. If the
// user closes the tab, the pings stop, and the server self-terminates after
// ~20s. Also send an explicit shutdown beacon on unload as a fast path.
setInterval(() => fetch('/heartbeat').catch(()=>{}), 5000);
window.addEventListener('beforeunload', () => {
  try { navigator.sendBeacon('/shutdown'); } catch (e) {}
});
$('quit').addEventListener('click', () => {
  if (!confirm('Stop polytime?')) return;
  fetch('/shutdown', {method:'POST'}).catch(()=>{});
  document.body.innerHTML='<div style=\"padding:40px;font-family:sans-serif;'
    +'color:#aaa;text-align:center\">polytime stopped. You can close this tab.</div>';
});

// ── MIDI keyboard input (Web MIDI API) ──────────────────────────────────
const recBox=$('recBox'), recDevice=$('recDevice'), recBtn=$('recBtn'),
      recStop=$('recStop'), recStatus=$('recStatus'), recBpm=$('recBpm');
let midiAccess=null, recording=false, recStart=0, recEvents=[], openNotes={},
    recTimer=null, activeInputs=[];

if (navigator.requestMIDIAccess) {
  recBox.style.display='block';
  navigator.requestMIDIAccess().then(setupMidi, () => {
    recDevice.textContent='permission denied';
  });
} else {
  $('recNotSupported').style.display='block';
}

function setupMidi(access) {
  midiAccess=access;
  refreshInputs();
  access.onstatechange=refreshInputs;
}
function refreshInputs() {
  for (const inp of activeInputs) inp.onmidimessage=null;
  activeInputs=[];
  const names=[];
  for (const inp of midiAccess.inputs.values()) {
    inp.onmidimessage=onMidi;
    activeInputs.push(inp);
    names.push(inp.name);
  }
  if (names.length) {
    recDevice.textContent=names.join(', ');
    recBtn.disabled=false;
  } else {
    recDevice.textContent='no device — plug one in';
    recBtn.disabled=true;
  }
}
function onMidi(e) {
  if (!recording) return;
  const [status, data1, data2] = e.data;
  const cmd = status & 0xf0;
  const t = performance.now() - recStart;
  if (cmd === 0x90 && data2 > 0) {
    openNotes[data1] = t;
  } else if (cmd === 0x80 || (cmd === 0x90 && data2 === 0)) {
    const onT = openNotes[data1];
    if (onT === undefined) return;
    delete openNotes[data1];
    recEvents.push({midi: data1, onMs: onT, offMs: t});
  }
}
recBtn.addEventListener('click', () => {
  recording=true; recEvents=[]; openNotes={}; recStart=performance.now();
  recBtn.disabled=true; recStop.disabled=false;
  recStatus.textContent='recording — play now';
  recStatus.style.color='#f77';
  recTimer=setInterval(()=>{
    const s=Math.floor((performance.now()-recStart)/1000);
    recStatus.textContent=`recording ${s}s · ${recEvents.length} notes`;
  }, 250);
});
recStop.addEventListener('click', () => {
  recording=false; recBtn.disabled=false; recStop.disabled=true;
  clearInterval(recTimer);
  recStatus.style.color='#aaa';
  for (const midi in openNotes) {
    recEvents.push({midi: +midi, onMs: openNotes[midi],
                    offMs: performance.now()-recStart});
  }
  openNotes={};
  if (!recEvents.length) {
    recStatus.textContent='nothing recorded';
    return;
  }
  const bpm = Math.max(20, Math.min(400, parseFloat(recBpm.value) || 120));
  const blob = buildMidi(recEvents, bpm);
  const f = new File([blob], 'recording.mid', {type: 'audio/midi'});
  recStatus.textContent=`captured ${recEvents.length} notes`;
  pickFile(f);
});

// Minimal Standard MIDI File writer (Type-1, one track) — produces a file
// any DAW / parser will accept. ppq=480, includes a tempo meta so playback
// matches what was captured.
function buildMidi(notes, bpm) {
  const PPQ = 480;
  const msPerBeat = 60000 / bpm;
  const anchor = Math.min(...notes.map(n => n.onMs));
  const evs = [];
  for (const n of notes) {
    const onTick  = Math.max(0, Math.round((n.onMs  - anchor) / msPerBeat * PPQ));
    const offTick = Math.max(onTick + 1,
                             Math.round((n.offMs - anchor) / msPerBeat * PPQ));
    evs.push({tick: onTick,  type: 'on',  midi: n.midi});
    evs.push({tick: offTick, type: 'off', midi: n.midi});
  }
  // note_off before note_on at the same tick so zero-gap legato survives.
  evs.sort((a, b) => a.tick - b.tick || (a.type === 'off' ? -1 : 1));
  function vlq(n) {
    if (n < 0) n = 0;
    const out = [n & 0x7f];
    n >>= 7;
    while (n > 0) { out.unshift((n & 0x7f) | 0x80); n >>= 7; }
    return out;
  }
  const body = [];
  // tempo meta (FF 51 03 ttt ttt ttt)
  const usPerBeat = Math.round(60000000 / bpm);
  body.push(0, 0xff, 0x51, 0x03,
            (usPerBeat >> 16) & 0xff, (usPerBeat >> 8) & 0xff, usPerBeat & 0xff);
  // 4/4 time-sig meta (the polytime UI lets the user override before generating)
  body.push(0, 0xff, 0x58, 0x04, 4, 2, 24, 8);
  let prev = 0;
  for (const e of evs) {
    body.push(...vlq(e.tick - prev));
    body.push(e.type === 'on' ? 0x90 : 0x80, e.midi,
              e.type === 'on' ? 80 : 0);
    prev = e.tick;
  }
  // end of track
  body.push(0, 0xff, 0x2f, 0x00);

  const trackLen = body.length;
  const header = [
    0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6,
    0, 1, 0, 1,
    (PPQ >> 8) & 0xff, PPQ & 0xff,
  ];
  const trackHdr = [
    0x4d, 0x54, 0x72, 0x6b,
    (trackLen >>> 24) & 0xff, (trackLen >>> 16) & 0xff,
    (trackLen >>>  8) & 0xff,  trackLen        & 0xff,
  ];
  return new Uint8Array([...header, ...trackHdr, ...body]);
}
</script>
</body></html>
"""


def parse_multipart(body: bytes, boundary: bytes) -> dict[str, bytes | tuple[str, bytes]]:
    """Tiny multipart/form-data parser. Plain fields → bytes; file fields → (filename, bytes)."""
    out: dict[str, bytes | tuple[str, bytes]] = {}
    sep = b"--" + boundary
    for part in body.split(sep):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        header_blob, _, content = part.partition(b"\r\n\r\n")
        headers = header_blob.decode("utf-8", "replace")
        disp = next((ln for ln in headers.split("\r\n")
                     if ln.lower().startswith("content-disposition")), "")
        name = None
        filename = None
        for piece in disp.split(";"):
            piece = piece.strip()
            if piece.startswith("name="):
                name = piece.split("=", 1)[1].strip('"')
            elif piece.startswith("filename="):
                filename = piece.split("=", 1)[1].strip('"')
        if name is None:
            continue
        if content.endswith(b"\r\n"):
            content = content[:-2]
        out[name] = (filename, content) if filename is not None else content
    return out


def cache_viz(data: bytes) -> str:
    token = uuid.uuid4().hex
    VIZ_CACHE[token] = data
    if len(VIZ_CACHE) > 20:
        for k in list(VIZ_CACHE)[:-20]:
            VIZ_CACHE.pop(k, None)
    return token


def parse_ts(s: str | None) -> TimeSignature | None:
    if not s:
        return None
    s = s.strip()
    if not s or "/" not in s:
        return None
    num, den = s.split("/", 1)
    return TimeSignature(int(num), int(den))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a, **_k):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_fields(self) -> dict:
        ctype = self.headers.get("Content-Type", "")
        if "boundary=" not in ctype:
            raise ValueError("expected multipart/form-data")
        boundary = ctype.split("boundary=", 1)[1].strip().strip('"').encode()
        length = int(self.headers.get("Content-Length", "0"))
        return parse_multipart(self.rfile.read(length), boundary)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/heartbeat":
            global LAST_HEARTBEAT
            LAST_HEARTBEAT = time.monotonic()
            self._send(200, b"ok", "text/plain")
            return
        if self.path.startswith("/viz/"):
            data = VIZ_CACHE.get(self.path[len("/viz/"):])
            if data is None:
                self._send(404, b"not found", "text/plain")
                return
            self._send(200, data, "text/html; charset=utf-8")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        try:
            if self.path == "/preview":
                self._handle_preview()
            elif self.path == "/process":
                self._handle_process()
            elif self.path == "/shutdown":
                self._send(200, b"bye", "text/plain")
                threading.Thread(
                    target=lambda: (time.sleep(0.2), os._exit(0)),
                    daemon=True,
                ).start()
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as e:
            traceback.print_exc()
            self._send(400, json.dumps({"error": str(e)}).encode("utf-8"),
                       "application/json; charset=utf-8")

    def _handle_preview(self):
        fields = self._read_fields()
        mid_field = fields.get("mid")
        if not isinstance(mid_field, tuple):
            raise ValueError("missing MIDI file")
        _, mid_bytes = mid_field

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            f.write(mid_bytes)
            in_path = Path(f.name)
        try:
            detected = detect_time_signature(in_path)
            ts = detected or TimeSignature(4, 4)
            from score_io.live.midi_file import load_mido
            from viz.interactive import multi_row_html
            from polytime import _flatten_score
            score = load_mido(str(in_path), time_signature=ts)
            theme = _flatten_score(score)
            viz_tmp = Path(tempfile.mkstemp(suffix=".html")[1])
            try:
                multi_row_html([("theme", theme)], viz_tmp,
                               title="loaded MIDI", combined=False)
                viz_data = viz_tmp.read_bytes()
            finally:
                try: viz_tmp.unlink()
                except OSError: pass
        finally:
            try: in_path.unlink()
            except OSError: pass

        payload = {
            "viz_token": cache_viz(viz_data),
            "detected_ts": f"{ts.numerator}/{ts.denominator}" +
                           ("" if detected else " (default)"),
        }
        self._send(200, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _handle_process(self):
        fields = self._read_fields()
        mid_field = fields.get("mid")
        if not isinstance(mid_field, tuple):
            raise ValueError("missing MIDI file")
        filename, mid_bytes = mid_field
        at_str = (fields.get("at") or b"2b").decode().strip() or "2b"
        scales_str = (fields.get("scales") or b"3/2").decode().strip() or "3/2"
        tsig_str = (fields.get("tsig") or b"").decode().strip()
        combine = (fields.get("combine") or b"1").decode().strip() == "1"

        base_bpm = 120.0
        scales = tuple(parse_scale(s.strip(), base_bpm)
                       for s in scales_str.split(",") if s.strip())
        if not scales:
            raise ValueError("provide at least one scale")
        if len(scales) > 8:
            raise ValueError("max 8 echo voices")
        voice_rows = len(scales) + (1 if combine else 0)
        n_rows = voice_rows + (1 if voice_rows > 1 else 0)
        stem = Path(filename or "input").stem

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            f.write(mid_bytes)
            in_path = Path(f.name)
        out_mid = Path(tempfile.mkstemp(suffix=".mid")[1])
        out_viz = Path(tempfile.mkstemp(suffix=".html")[1])

        try:
            detected_bpm = detect_bpm(in_path)
            if detected_bpm:
                base_bpm = detected_bpm
                # Re-parse scales now that we know the file's tempo (only
                # changes results for entries that used the `bpm` suffix).
                scales = tuple(parse_scale(s.strip(), base_bpm)
                               for s in scales_str.split(",") if s.strip())
            ts_override = parse_ts(tsig_str)
            detected = detect_time_signature(in_path)
            ts = ts_override or detected or TimeSignature(4, 4)
            ts_label = f"{ts.numerator}/{ts.denominator}"
            if ts_override:
                ts_label += " (override)"
            elif not detected:
                ts_label += " (default)"

            at_tokens = [a.strip() for a in at_str.split(",") if a.strip()]
            if len(at_tokens) <= 1:
                at_f = _parse_when(at_str, ts.beats_per_measure)
                ats = None  # staggered: k*at
            else:
                if len(at_tokens) != len(scales):
                    raise ValueError(
                        f"got {len(at_tokens)} entry times but {len(scales)} scales — "
                        f"give one `at` value (staggered) or one per voice"
                    )
                at_f = _parse_when(at_tokens[0], ts.beats_per_measure)
                ats = tuple(_parse_when(t, ts.beats_per_measure) for t in at_tokens)
            mid_path, viz_path = polytime(
                in_path, at=at_f, scales=scales, ats=ats,
                out=out_mid, diff_png=out_viz, time_signature=ts,
                combine=combine, viz_connectors=False,
            )
            mid_data = mid_path.read_bytes()
            viz_data = viz_path.read_bytes()
        finally:
            for p in (in_path, out_mid, out_viz):
                try: p.unlink()
                except OSError: pass

        payload = {
            "viz_token": cache_viz(viz_data),
            "midi_data_url": "data:audio/midi;base64," +
                             base64.b64encode(mid_data).decode("ascii"),
            "midi_filename": f"{stem}_polytime.mid",
            "detected_ts": ts_label,
            "n_rows": n_rows,
        }
        self._send(200, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _watchdog():
    """Exit if the browser hasn't heart-beaten in HEARTBEAT_TIMEOUT_S.
    Grace period: ignore the first ~15s so a slow browser launch isn't fatal."""
    grace_until = time.monotonic() + 15.0
    while True:
        time.sleep(HEARTBEAT_CHECK_S)
        now = time.monotonic()
        if now < grace_until:
            continue
        if now - LAST_HEARTBEAT > HEARTBEAT_TIMEOUT_S:
            os._exit(0)


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Timer(0.4, lambda: webbrowser.open_new_tab(url)).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    print(f"polytime running at {url}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
