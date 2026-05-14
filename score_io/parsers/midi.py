"""MIDI parser: reads a .mid file via music21 and converts to the model.

MIDI has no reliable dynamic or articulation data, so those fields are omitted.
Enharmonic spelling defaults: C# not Db, except F# and Bb which keep their
conventional spellings.

music21 is used only in this module.
"""
from __future__ import annotations
from fractions import Fraction

from model.pitch import Pitch
from model.duration import Duration
from model.events import Note, Rest, Event
from model.voice import Voice
from model.measure import Measure, TimeSignature
from model.part import Part
from model.score import Score

class ParseError(Exception):
    pass


# music21 note-type names → quarter-note-relative Fractions
_M21_TYPE_TO_VALUE: dict[str, Fraction] = {
    "longa": Fraction(16),
    "breve": Fraction(8),
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
    "128th": Fraction(1, 32),
}


# Preferred spelling per pitch class for MIDI (sharps by default, except Bb)
_MIDI_SPELLING: dict[int, str] = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E",
    5: "F", 6: "F#", 7: "G", 8: "G#", 9: "A",
    10: "Bb", 11: "B",
}


def _midi_to_pitch(midi: int) -> Pitch:
    pc = midi % 12
    octave = midi // 12 - 1
    return Pitch(midi=midi, spelling=_MIDI_SPELLING[pc], octave=octave)


def parse(path: str, *, time_signature: TimeSignature | None = None) -> Score:
    """Parse a MIDI file and return a Score.

    No dynamics or articulations are set (MIDI doesn't carry them reliably).
    Uses music21 internally; the resulting Score contains only model types.

    If `time_signature` is given, music21's measure detection is bypassed:
    all notes are flattened to absolute offsets and re-binned into uniform
    measures of the requested meter. This is what you want for raw MIDI
    captures or whenever music21's auto-detected boundaries don't match
    musical reality.

    Raises ParseError on any structural problem.

    Example: parse("piece.mid", time_signature=TimeSignature(4, 4))
    """
    try:
        import music21.converter as converter
    except ImportError as e:
        raise ParseError("music21 is not installed. Run: pip install music21") from e

    try:
        stream = converter.parse(path)
    except Exception as e:
        raise ParseError(f"Cannot parse MIDI '{path}': {e}") from e

    import music21.stream as m21stream
    import music21.note as m21note
    import music21.meter as m21meter

    parts: list[Part] = []

    m21_parts = list(stream.getElementsByClass(m21stream.Part))
    if not m21_parts:
        m21_parts = [stream]

    for part_idx, m21_part in enumerate(m21_parts):
        measures: list[Measure] = []

        m21_measures = list(m21_part.getElementsByClass(m21stream.Measure))
        force_flat = time_signature is not None
        if force_flat or not m21_measures:
            all_notes = list(m21_part.flatten().getElementsByClass(m21note.GeneralNote))
            events = _build_events(all_notes)
            ts = time_signature or TimeSignature(4, 4)
            capacity = Fraction(ts.numerator * 4, ts.denominator)
            measures = _events_to_measures(events, ts, capacity)
        else:
            for i, m21_measure in enumerate(m21_measures, start=1):
                ts_objs = m21_measure.getElementsByClass(m21meter.TimeSignature)
                ts = TimeSignature(4, 4)
                if ts_objs:
                    t = ts_objs[0]
                    ts = TimeSignature(t.numerator, t.denominator)

                notes = list(m21_measure.flatten().getElementsByClass(m21note.GeneralNote))
                events = _build_events(notes)

                if not events:
                    capacity = Fraction(ts.numerator * 4, ts.denominator)
                    rest = Rest(duration=Duration(value=capacity), offset=Fraction(0))
                    events = [rest]

                voice = Voice(id="1", events=tuple(events))
                measures.append(Measure(number=i, time_signature=ts, voices=(voice,)))

        part_name = getattr(m21_part, "partName", None) or f"Part {part_idx + 1}"
        parts.append(Part(
            name=part_name,
            instrument=None,
            clef="treble",
            measures=tuple(measures),
        ))

    return Score(title="Untitled", parts=tuple(parts), metadata={})


def _build_events(m21_notes) -> list[Event]:
    events = []
    for element in m21_notes:
        try:
            offset = Fraction(float(element.offset)).limit_denominator(64)
            if getattr(element.duration, "isGrace", False) or element.duration.quarterLength == 0:
                continue
            base = _M21_TYPE_TO_VALUE.get(getattr(element.duration, "type", None))
            if base is not None:
                dur = Duration(value=base, dots=element.duration.dots or 0)
            else:
                value = Fraction(float(element.duration.quarterLength)).limit_denominator(64)
                if value <= 0:
                    continue
                dur = Duration(value=value)

            import music21.note as m21note
            if isinstance(element, m21note.Rest):
                events.append(Rest(duration=dur, offset=offset))
            elif hasattr(element, "pitch"):
                pitch = _midi_to_pitch(element.pitch.midi)
                events.append(Note(duration=dur, offset=offset, pitch=pitch))
        except Exception:
            continue
    return sorted(events, key=lambda e: e.offset)


def _events_to_measures(
    events: list[Event],
    ts: TimeSignature,
    capacity: Fraction,
) -> list[Measure]:
    from dataclasses import replace
    if not events:
        return []
    last_end = max(e.offset + e.duration.actual_beats for e in events)
    n_measures = max(1, int(-(-last_end // capacity)))  # ceil

    measures: list[Measure] = []
    for i in range(n_measures):
        m_start = capacity * i
        m_end = m_start + capacity
        bin_events = [
            replace(e, offset=e.offset - m_start)
            for e in events
            if m_start <= e.offset < m_end
        ]
        if not bin_events:
            bin_events = [Rest(duration=Duration(value=capacity), offset=Fraction(0))]
        voice = Voice(id="1", events=tuple(bin_events))
        measures.append(Measure(number=i + 1, time_signature=ts, voices=(voice,)))
    return measures
