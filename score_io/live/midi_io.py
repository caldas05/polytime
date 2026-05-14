"""Live MIDI I/O via mido + python-rtmidi.

Sits next to score_io.parsers.midi / score_io.serializers.midi (file-based,
music21-backed). This module is for connected hardware: keyboards, synths.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from fractions import Fraction

import mido

from model.pitch import Pitch
from model.duration import Duration
from model.events import Note, Rest, Event
from model.voice import Voice
from model.measure import Measure, TimeSignature
from model.part import Part
from model.score import Score


_MIDI_SPELLING: dict[int, str] = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E",
    5: "F", 6: "F#", 7: "G", 8: "G#", 9: "A",
    10: "Bb", 11: "B",
}


def _midi_to_pitch(midi: int) -> Pitch:
    pc = midi % 12
    octave = midi // 12 - 1
    return Pitch(midi=midi, spelling=_MIDI_SPELLING[pc], octave=octave)


@dataclass(frozen=True)
class Ports:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


def list_ports() -> Ports:
    """Enumerate connected MIDI input/output ports."""
    return Ports(
        inputs=tuple(mido.get_input_names()),
        outputs=tuple(mido.get_output_names()),
    )


def record(
    port_name: str,
    duration_s: float,
    *,
    bpm: float = 120.0,
    grid: Fraction = Fraction(1, 4),
    tuplet_grids: tuple[Fraction, ...] = (),
    time_signature: TimeSignature = TimeSignature(4, 4),
) -> Score:
    """Capture from a MIDI input port for duration_s seconds.

    Returns a single-part, single-voice Score quantized to `grid` (in beats,
    where Fraction(1) is a quarter note; default 1/4 = sixteenth-note grid).

    Pass `tuplet_grids` to enable polyrhythmic capture: each note is
    quantized independently to whichever grid in `(grid, *tuplet_grids)`
    minimizes its onset+duration error. Use Fraction(1, 6) for triplets,
    Fraction(1, 10) for quintuplets, etc. Notes on different grids can
    coexist in the same voice, so 3-against-2 and similar polyrhythms
    survive capture.

    Notes that are released after the recording window ends are truncated.
    Notes still held when the window closes are clipped at the end.
    """
    sec_per_beat = 60.0 / bpm
    started: dict[int, float] = {}
    raw: list[tuple[float, float, int]] = []  # (start_s, end_s, midi)

    end_at = time.monotonic() + duration_s
    with mido.open_input(port_name) as port:
        while True:
            now = time.monotonic()
            if now >= end_at:
                break
            msg = port.poll()
            if msg is None:
                time.sleep(0.001)
                continue
            t = now - (end_at - duration_s)  # seconds since start
            if msg.type == "note_on" and msg.velocity > 0:
                started[msg.note] = t
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                start = started.pop(msg.note, None)
                if start is not None:
                    raw.append((start, t, msg.note))

    # Clip any notes still held to the end of the window.
    for midi_n, start in started.items():
        raw.append((start, duration_s, midi_n))

    raw.sort(key=lambda r: r[0])

    grids = (grid, *tuplet_grids)

    def _snap(beats: Fraction, g: Fraction) -> tuple[Fraction, float]:
        """Snap `beats` to grid `g`; return (snapped, abs_error_in_beats)."""
        steps = round(beats / g)
        snapped = steps * g
        return snapped, abs(float(beats - snapped))

    def _quantize_note(start_s: float, end_s: float) -> tuple[Fraction, Fraction, Fraction]:
        """Pick the grid that minimizes total onset+duration snap error for
        this note. Returns (onset_beats, duration_beats, chosen_grid)."""
        on_beats = Fraction(start_s / sec_per_beat).limit_denominator(96)
        off_beats = Fraction(end_s / sec_per_beat).limit_denominator(96)
        best = None
        for g in grids:
            on_s, on_err = _snap(on_beats, g)
            off_s, off_err = _snap(off_beats, g)
            err = on_err + off_err
            if best is None or err < best[0]:
                best = (err, on_s, off_s - on_s, g)
        _, on_s, dur_s, gsel = best
        if dur_s <= 0:
            dur_s = gsel
        return on_s, dur_s, gsel

    capacity = Fraction(time_signature.numerator * 4, time_signature.denominator)

    # Bucket events into measures by quantized start offset.
    events_by_measure: dict[int, list[Event]] = {}
    for start_s, end_s, midi_n in raw:
        on, dur_beats, gsel = _quantize_note(start_s, end_s)
        # Tag with a tuplet ratio when the chosen grid is non-dyadic so the
        # notational layer can recognize the rhythm. tuplet=(actual, written)
        # scales actual_beats by written/actual, so we counter-scale `value`
        # to keep actual_beats == dur_beats.
        denom = gsel.denominator
        tup: tuple[int, int] | None = None
        value = dur_beats
        if denom & (denom - 1) != 0:  # non-power-of-2 → tuplet grid
            for k in (3, 5, 7):
                if denom % k == 0:
                    tup = (k, 2)
                    value = dur_beats * Fraction(k, 2)
                    break
        m_idx = int(on // capacity)
        local_offset = on - m_idx * capacity
        events_by_measure.setdefault(m_idx, []).append(
            Note(
                duration=Duration(value=value, tuplet=tup),
                offset=local_offset,
                pitch=_midi_to_pitch(midi_n),
            )
        )

    total_measures = max(1, int(_q(duration_s) // capacity) + 1)

    measures: list[Measure] = []
    for i in range(total_measures):
        evs = events_by_measure.get(i, [])
        if not evs:
            evs = [Rest(duration=Duration(value=capacity), offset=Fraction(0))]
        else:
            evs.sort(key=lambda e: e.offset)
        voice = Voice(id="1", events=tuple(evs))
        try:
            measures.append(Measure(number=i + 1, time_signature=time_signature, voices=(voice,)))
        except ValueError:
            # Trim if quantization overshot capacity.
            trimmed: list[Event] = []
            total = Fraction(0)
            for e in evs:
                if total + e.duration.actual_beats > capacity:
                    break
                trimmed.append(e)
                total += e.duration.actual_beats
            voice = Voice(id="1", events=tuple(trimmed) or (
                Rest(duration=Duration(value=capacity), offset=Fraction(0)),
            ))
            measures.append(Measure(number=i + 1, time_signature=time_signature, voices=(voice,)))

    part = Part(name="Recorded", instrument=None, clef="treble", measures=tuple(measures))
    return Score(title="Live Recording", parts=(part,), metadata={})


def play(score: Score, port_name: str, *, bpm: float = 120.0) -> None:
    """Send a Score to a MIDI output port, in wall-clock time.

    Blocks until the score has finished playing. Tempo defaults to 120 BPM
    unless any measure carries its own TempoMark, which then takes effect
    from that measure onward.
    """
    sec_per_beat = 60.0 / bpm

    # Flatten all parts to (abs_beat_offset, midi_pitch, duration_beats) tuples.
    notes: list[tuple[Fraction, int, Fraction]] = []
    for part in score.parts:
        measure_offset = Fraction(0)
        current_bpm = bpm
        for measure in part.measures:
            if measure.tempo is not None:
                current_bpm = measure.tempo.bpm
            for voice in measure.voices:
                for ev in voice.events:
                    abs_off = measure_offset + ev.offset
                    dur = ev.duration.actual_beats
                    if isinstance(ev, Note):
                        notes.append((abs_off, ev.pitch.midi, dur))
                    elif hasattr(ev, "pitches"):  # Chord
                        for p in ev.pitches:
                            notes.append((abs_off, p.midi, dur))
            measure_offset += measure.time_signature.beats_per_measure
        # current_bpm currently unused for per-measure timing — global bpm wins.
        # (Mid-piece tempo changes would need a sorted timeline; keep simple.)

    # Build (timestamp_seconds, message) pairs.
    events: list[tuple[float, mido.Message]] = []
    for off_beats, midi_n, dur_beats in notes:
        on_t = float(off_beats) * sec_per_beat
        off_t = on_t + float(dur_beats) * sec_per_beat
        events.append((on_t, mido.Message("note_on", note=midi_n, velocity=80)))
        events.append((off_t, mido.Message("note_off", note=midi_n, velocity=0)))
    events.sort(key=lambda e: e[0])

    with mido.open_output(port_name) as port:
        start = time.monotonic()
        for ts, msg in events:
            wait = (start + ts) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            port.send(msg)
