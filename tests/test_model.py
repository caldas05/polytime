"""Tests for the model layer (Layer 1). No external dependencies."""
import pytest
from fractions import Fraction

from model.pitch import Pitch
from model.duration import Duration
from model.events import Note, Rest, Chord
from model.voice import Voice
from model.measure import Measure, TimeSignature, TempoMark
from model.part import Part
from model.score import Score


# ─── Pitch ────────────────────────────────────────────────────────────────────

def test_pitch_valid():
    p = Pitch(midi=60, spelling="C", octave=4)
    assert p.midi == 60
    assert p.spelling == "C"
    assert p.octave == 4

def test_pitch_pitch_class():
    assert Pitch(midi=60, spelling="C", octave=4).pitch_class == 0
    assert Pitch(midi=61, spelling="C#", octave=4).pitch_class == 1
    assert Pitch(midi=71, spelling="B", octave=4).pitch_class == 11

def test_pitch_name_without_octave():
    assert Pitch(midi=60, spelling="C", octave=4).name_without_octave == "C"
    assert Pitch(midi=61, spelling="Db", octave=4).name_without_octave == "Db"

def test_pitch_midi_out_of_range():
    with pytest.raises(ValueError):
        Pitch(midi=-1, spelling="C", octave=4)
    with pytest.raises(ValueError):
        Pitch(midi=128, spelling="C", octave=10)

def test_pitch_frozen():
    p = Pitch(midi=60, spelling="C", octave=4)
    with pytest.raises(Exception):  # FrozenInstanceError
        p.midi = 61  # type: ignore


# ─── Duration ─────────────────────────────────────────────────────────────────

def make_quarter() -> Duration:
    return Duration(value=Fraction(1, 1))

def test_duration_quarter_actual_beats():
    assert make_quarter().actual_beats == Fraction(1, 1)

def test_duration_eighth_actual_beats():
    eighth = Duration(value=Fraction(1, 2))
    assert eighth.actual_beats == Fraction(1, 2)

def test_duration_dotted_quarter():
    d = Duration(value=Fraction(1, 1), dots=1)
    assert d.actual_beats == Fraction(3, 2)

def test_duration_double_dotted_quarter():
    d = Duration(value=Fraction(1, 1), dots=2)
    assert d.actual_beats == Fraction(7, 4)

def test_duration_triplet_quarter():
    # triplet: 3 notes in the space of 2 → tuplet=(3, 2)
    d = Duration(value=Fraction(1, 1), tuplet=(3, 2))
    assert d.actual_beats == Fraction(2, 3)

def test_duration_negative_value():
    with pytest.raises(ValueError):
        Duration(value=Fraction(-1, 1))

def test_duration_frozen():
    d = make_quarter()
    with pytest.raises(Exception):
        d.dots = 1  # type: ignore


# ─── Events ───────────────────────────────────────────────────────────────────

def _note(offset: Fraction = Fraction(0)) -> Note:
    return Note(
        duration=make_quarter(),
        offset=offset,
        pitch=Pitch(midi=60, spelling="C", octave=4),
    )

def test_note_fields():
    n = _note()
    assert n.pitch.midi == 60
    assert n.offset == Fraction(0)
    assert n.dynamic is None
    assert n.articulations == ()

def test_rest_fields():
    r = Rest(duration=make_quarter(), offset=Fraction(1))
    assert r.offset == Fraction(1)

def test_chord_requires_two_pitches():
    p = Pitch(midi=60, spelling="C", octave=4)
    with pytest.raises(ValueError):
        Chord(duration=make_quarter(), offset=Fraction(0), pitches=(p,))

def test_chord_valid():
    p1 = Pitch(midi=60, spelling="C", octave=4)
    p2 = Pitch(midi=64, spelling="E", octave=4)
    c = Chord(duration=make_quarter(), offset=Fraction(0), pitches=(p1, p2))
    assert len(c.pitches) == 2


# ─── Voice ────────────────────────────────────────────────────────────────────

def test_voice_ordered():
    n1 = _note(Fraction(0))
    n2 = _note(Fraction(1))
    v = Voice(id="v1", events=(n1, n2))
    assert len(v.events) == 2

def test_voice_unordered_raises():
    n1 = _note(Fraction(1))
    n2 = _note(Fraction(0))
    with pytest.raises(ValueError):
        Voice(id="v1", events=(n1, n2))

def test_voice_frozen():
    v = Voice(id="v1", events=())
    with pytest.raises(Exception):
        v.id = "v2"  # type: ignore


# ─── Measure ──────────────────────────────────────────────────────────────────

def _four_four_voice() -> Voice:
    events = tuple(_note(Fraction(i)) for i in range(4))
    return Voice(id="v1", events=events)

def test_measure_valid():
    v = _four_four_voice()
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    assert m.number == 1

def test_measure_accepts_overflow():
    """time_signature is a hint, not a hard cap — overflow is allowed."""
    events = tuple(_note(Fraction(i)) for i in range(5))
    v = Voice(id="v1", events=events)
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    assert len(m.voices[0].events) == 5

def test_time_signature_beats():
    assert TimeSignature(4, 4).beats_per_measure == Fraction(4)
    assert TimeSignature(3, 4).beats_per_measure == Fraction(3)
    assert TimeSignature(6, 8).beats_per_measure == Fraction(3)

def test_measure_with_tempo():
    v = _four_four_voice()
    tempo = TempoMark(bpm=120.0, beat_unit=Fraction(1, 1))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,), tempo=tempo)
    assert m.tempo.bpm == 120.0


# ─── Part & Score ─────────────────────────────────────────────────────────────

def test_part_and_score():
    v = _four_four_voice()
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    part = Part(name="Piano", instrument=None, clef="treble", measures=(m,))
    score = Score(title="Test", parts=(part,), metadata={})
    assert score.title == "Test"
    assert len(score.parts) == 1
