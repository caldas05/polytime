"""MIDI serializer: converts a Score model to MIDI binary.

Uses music21 internally, same as the MIDI parser.
Preserves all notes, rests, chords, durations, time signatures, and tempos.
"""
from __future__ import annotations
import os
import tempfile
from fractions import Fraction

from model.score import Score
from model.events import Note, Rest, Chord, Event

try:
    import music21 as m21
except ImportError:  # deferred — raised at call time with a friendlier message
    m21 = None


def _require_m21():
    if m21 is None:
        raise ImportError("music21 is not installed. Run: pip install music21")
    return m21


def _event_to_m21(event: Event):
    """Convert an Event to a music21 note/rest/chord element."""
    m21 = _require_m21()
    quarter_length = float(event.duration.actual_beats)

    if isinstance(event, Rest):
        n = m21.note.Rest()
        n.quarterLength = quarter_length
        return n
    elif isinstance(event, Note):
        n = m21.note.Note()
        n.pitch.midi = event.pitch.midi
        n.quarterLength = quarter_length
        return n
    elif isinstance(event, Chord):
        c = m21.chord.Chord()
        c.pitches = [m21.pitch.Pitch(midi=p.midi) for p in event.pitches]
        c.quarterLength = quarter_length
        return c


def _build_stream(score: Score):
    m21 = _require_m21()
    score_stream = m21.stream.Score()

    for part in score.parts:
        part_stream = m21.stream.Part()

        if part.instrument:
            try:
                instr = m21.instrument.getInstrument(part.instrument.lower())
                if instr:
                    part_stream.append(instr)
            except Exception:
                pass

        events_with_offset: list[tuple[Fraction, object]] = []
        measure_offset = Fraction(0)

        for measure in part.measures:
            ts = measure.time_signature
            ts_m21 = m21.meter.TimeSignature(f"{ts.numerator}/{ts.denominator}")
            events_with_offset.append((measure_offset, ts_m21))

            if measure.tempo:
                tempo_m21 = m21.tempo.MetronomeMark(number=measure.tempo.bpm)
                events_with_offset.append((measure_offset, tempo_m21))

            for voice in measure.voices:
                for event in voice.events:
                    abs_offset = measure_offset + event.offset
                    m21_event = _event_to_m21(event)
                    events_with_offset.append((abs_offset, m21_event))

            measure_offset += measure.time_signature.beats_per_measure

        events_with_offset.sort(key=lambda x: x[0])
        for offset, elem in events_with_offset:
            elem.offset = float(offset)
            part_stream.append(elem)

        score_stream.append(part_stream)

    return score_stream


def serialize(score: Score) -> bytes:
    """Convert a Score to MIDI binary data.

    Raises ImportError if music21 is not installed.

    Example:
        midi_bytes = serialize(score)
        with open("out.mid", "wb") as f:
            f.write(midi_bytes)
    """
    score_stream = _build_stream(score)
    fd, tmp_path = tempfile.mkstemp(suffix=".mid")
    os.close(fd)
    try:
        score_stream.write("midi", fp=tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def save(score: Score, path: str) -> None:
    """Serialize score to a MIDI file.

    Example: save(score, "piece.mid")
    """
    _build_stream(score).write("midi", fp=path)
