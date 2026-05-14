"""Self-contained interactive HTML diff: matplotlib SVG + minimal pan/zoom JS.

No external runtime dependencies — the resulting .html file is a single
artifact that opens in any browser with mouse-wheel zoom and click-drag pan.
"""
from __future__ import annotations
import io
from pathlib import Path

from model.voice import Voice


_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  html, body {{ margin: 0; height: 100%; background: #fafafa; font-family: sans-serif; }}
  #wrap {{ width: 100vw; height: 100vh; overflow: hidden; cursor: grab; }}
  #wrap.dragging {{ cursor: grabbing; }}
  #stage {{ transform-origin: 0 0; }}
  #stage svg {{ display: block; }}
  #ctrl {{ position: fixed; top: 8px; right: 12px; display: flex; gap: 4px;
           background: rgba(255,255,255,0.9); border-radius: 4px; padding: 4px;
           font-size: 12px; color: #444; box-shadow: 0 1px 3px rgba(0,0,0,0.15); }}
  #ctrl button {{ font: inherit; padding: 2px 8px; background: #f4f4f4;
                  border: 1px solid #ccc; border-radius: 3px; cursor: pointer; }}
  #ctrl button:hover {{ background: #e8e8e8; }}
  #ctrl span {{ align-self: center; padding: 0 4px; color: #888; }}
</style></head>
<body>
<div id="wrap"><div id="stage">{svg}</div></div>
<div id="ctrl">
  <button id="zout">−</button>
  <button id="zin">+</button>
  <span id="zlbl">100%</span>
  <button id="reset">reset</button>
</div>
<script>
(function () {{
  const wrap = document.getElementById('wrap');
  const stage = document.getElementById('stage');
  const zlbl = document.getElementById('zlbl');
  let scale = 1, tx = 0, ty = 0;
  function apply() {{
    stage.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
    zlbl.textContent = Math.round(scale * 100) + '%';
  }}
  function zoomAt(factor, cx, cy) {{
    const newScale = Math.max(0.2, Math.min(20, scale * factor));
    tx = cx - (cx - tx) * (newScale / scale);
    ty = cy - (cy - ty) * (newScale / scale);
    scale = newScale; apply();
  }}
  function centerZoom(factor) {{
    const r = wrap.getBoundingClientRect();
    zoomAt(factor, r.width / 2, r.height / 2);
  }}
  document.getElementById('zin').onclick = () => centerZoom(1.25);
  document.getElementById('zout').onclick = () => centerZoom(1/1.25);
  document.getElementById('reset').onclick = () => {{
    scale = 1; tx = 0; ty = 0; apply();
  }};
  let dragging = false, lx = 0, ly = 0;
  wrap.addEventListener('mousedown', (e) => {{
    if (e.target.closest('#ctrl')) return;
    dragging = true; lx = e.clientX; ly = e.clientY;
    wrap.classList.add('dragging');
  }});
  window.addEventListener('mousemove', (e) => {{
    if (!dragging) return;
    tx += e.clientX - lx; ty += e.clientY - ly;
    lx = e.clientX; ly = e.clientY;
    apply();
  }});
  window.addEventListener('mouseup', () => {{
    dragging = false; wrap.classList.remove('dragging');
  }});
  wrap.addEventListener('dblclick', (e) => {{
    if (e.target.closest('#ctrl')) return;
    scale = 1; tx = 0; ty = 0; apply();
  }});
}})();
</script>
</body></html>
"""


def diff_html(
    before: Voice,
    after: Voice | None,
    out_path: str | Path,
    *,
    title: str = "",
    connectors: bool = True,
) -> Path:
    """Render the diff to a standalone interactive HTML file.

    The diff is drawn with matplotlib (same renderer as the PNG/SVG paths),
    then embedded as inline SVG with a tiny pan/zoom shim. Open the file
    in a browser — scroll to zoom, click-drag to pan.
    """
    import matplotlib
    matplotlib.use("Agg")
    from viz import diff, trace

    fig = diff(trace(before), after, title=title, connectors=connectors)
    buf = io.StringIO()
    fig.savefig(buf, format="svg")
    svg = buf.getvalue()
    # Strip the XML preamble so the SVG embeds cleanly inside <div>.
    if "<svg" in svg:
        svg = svg[svg.index("<svg"):]

    html = _HTML_TEMPLATE.format(title=title or "diff", svg=svg)
    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def multi_row_html(
    rows: list[tuple[str, Voice]],
    out_path: str | Path,
    *,
    title: str = "",
    combined: bool = True,
) -> Path:
    """Render N voices stacked vertically — one row per (label, voice) —
    plus an optional final row that overlays all voices in different colors.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from viz.piano_roll import draw_voice, voice_pitch_range

    voices = [v for _, v in rows]
    n_rows = len(rows) + (1 if combined and len(rows) > 1 else 0)
    end_total = max(
        (float(e.offset) + float(e.duration.actual_beats)
         for v in voices for e in v.events),
        default=4.0,
    )
    width = min(60.0, max(12.0, end_total / 8.0))
    height = max(3.0, 1.8 * n_rows)

    fig, axes = plt.subplots(n_rows, 1, figsize=(width, height), sharex=True,
                             gridspec_kw={"hspace": 0.5})
    if n_rows == 1:
        axes = [axes]

    palette = ["#3a7bd5", "#d55e3a", "#3ad57b", "#d5c43a",
               "#9933cc", "#33aaff", "#ff6699", "#66cc88", "#aaaa44"]
    lo, hi = voice_pitch_range(voices) if voices else (60, 72)

    for i, (label, v) in enumerate(rows):
        draw_voice(v, axes[i], color=palette[i % len(palette)], label=label)
        axes[i].set_ylim(lo, hi)
        axes[i].set_xlim(-0.2, end_total + 0.2)
        axes[i].set_title(label, fontsize=10, loc="left", color="#333", pad=2)

    if combined and len(rows) > 1:
        ax = axes[-1]
        for i, (_, v) in enumerate(rows):
            draw_voice(v, ax, color=palette[i % len(palette)], alpha=0.6)
        ax.set_ylim(lo, hi)
        ax.set_xlim(-0.2, end_total + 0.2)
        ax.set_title("combined", fontsize=10, loc="left", color="#333", pad=2)

    axes[-1].set_xlabel("beats")
    if title:
        fig.suptitle(title, fontsize=11)

    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    svg = buf.getvalue()
    if "<svg" in svg:
        svg = svg[svg.index("<svg"):]
    html = _HTML_TEMPLATE.format(title=title or "voices", svg=svg)
    out_path = Path(out_path)
    out_path.write_text(html, encoding="utf-8")
    plt.close(fig)
    return out_path
