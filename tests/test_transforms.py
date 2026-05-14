"""Tests for the transforms layer (Layer 3). All transforms must be pure functions."""
import pytest
from fractions import Fraction

from model.pitch import Pitch
from model.duration import Duration
from model.events import Note, Rest, Chord
from model.voice import Voice
from model.measure import Measure, TimeSignature
from model.part import Part
from model.score import Score

from transforms.temporal import retrograde, retrograde_measure, scale_rhythm, shift_offset
from transforms.melodic import transpose_voice, invert_melody, invert_melody_diatonic
from transforms.geometric import retrograde_inversion, mirror_measure
from transforms.combinators import compose, apply_to_voice, apply_to_measure, apply_to_all_measures, apply_to_part

from teoria.scale import Scale, MAJOR


# ─── Helpers ──────────────────────────────────────────────────────────────────

def quarter() -> Duration:
    return Duration(value=Fraction(1, 1))

def make_note(midi: int, offset: Fraction, spelling: str = "C", octave: int = 4) -> Note:
    return Note(
        duration=quarter(),
        offset=offset,
        pitch=Pitch(midi=midi, spelling=spelling, octave=octave),
    )

def c_major_voice() -> Voice:
    """C4 D4 E4 F4 — four quarter notes, offsets 0,1,2,3."""
    notes = (
        make_note(60, Fraction(0), "C", 4),
        make_note(62, Fraction(1), "D", 4),
        make_note(64, Fraction(2), "E", 4),
        make_note(65, Fraction(3), "F", 4),
    )
    return Voice(id="v1", events=notes)

def simple_measure() -> Measure:
    return Measure(
        number=1,
        time_signature=TimeSignature(4, 4),
        voices=(c_major_voice(),),
    )


# ─── Retrograde ───────────────────────────────────────────────────────────────

def test_retrograde_reverses_pitches():
    v = c_major_voice()
    rv = retrograde(v)
    original_midis = [e.pitch.midi for e in v.events]  # type: ignore[union-attr]
    retro_midis = [e.pitch.midi for e in rv.events]  # type: ignore[union-attr]
    assert retro_midis == original_midis[::-1]

def test_retrograde_resets_offsets():
    v = c_major_voice()
    rv = retrograde(v)
    assert rv.events[0].offset == Fraction(0)
    assert rv.events[1].offset == Fraction(1)

def test_retrograde_involution():
    """retrograde(retrograde(v)) == v"""
    v = c_major_voice()
    assert retrograde(retrograde(v)) == v

def test_retrograde_empty_voice():
    v = Voice(id="v1", events=())
    assert retrograde(v) == v

def test_retrograde_measure():
    m = simple_measure()
    rm = retrograde_measure(m)
    assert rm.number == m.number
    orig_midis = [e.pitch.midi for e in m.voices[0].events]  # type: ignore[union-attr]
    retro_midis = [e.pitch.midi for e in rm.voices[0].events]  # type: ignore[union-attr]
    assert retro_midis == orig_midis[::-1]


# ─── Scale rhythm ─────────────────────────────────────────────────────────────

def test_scale_rhythm_doubles():
    v = c_major_voice()
    sv = scale_rhythm(v, Fraction(2))
    assert sv.events[0].duration.value == Fraction(2, 1)
    assert sv.events[1].offset == Fraction(2)

def test_scale_rhythm_involution():
    """scale_rhythm(scale_rhythm(v, 2), 1/2) == v"""
    v = c_major_voice()
    assert scale_rhythm(scale_rhythm(v, Fraction(2)), Fraction(1, 2)) == v


# ─── Shift offset ─────────────────────────────────────────────────────────────

def test_shift_offset():
    v = c_major_voice()
    sv = shift_offset(v, Fraction(1))
    assert sv.events[0].offset == Fraction(1)
    assert sv.events[3].offset == Fraction(4)

def test_shift_offset_involution():
    v = c_major_voice()
    assert shift_offset(shift_offset(v, Fraction(3)), Fraction(-3)) == v


# ─── Transpose voice ──────────────────────────────────────────────────────────

def test_transpose_voice_up():
    v = c_major_voice()
    tv = transpose_voice(v, 7)
    midis = [e.pitch.midi for e in tv.events]  # type: ignore[union-attr]
    orig_midis = [e.pitch.midi for e in v.events]  # type: ignore[union-attr]
    assert midis == [m + 7 for m in orig_midis]

def test_transpose_voice_involution():
    """transpose(transpose(v, 7), -7) == v"""
    v = c_major_voice()
    assert transpose_voice(transpose_voice(v, 7), -7) == v

def test_transpose_leaves_rests():
    rest = Rest(duration=quarter(), offset=Fraction(0))
    v = Voice(id="v1", events=(rest,))
    tv = transpose_voice(v, 5)
    assert tv.events[0] == rest


# ─── Invert melody ────────────────────────────────────────────────────────────

def test_invert_melody_axis_unchanged():
    """The axis pitch maps to itself."""
    axis = Pitch(midi=60, spelling="C", octave=4)
    v = Voice(id="v1", events=(make_note(60, Fraction(0)),))
    iv = invert_melody(v, axis)
    assert iv.events[0].pitch.midi == 60  # type: ignore[union-attr]

def test_invert_melody_mirrors():
    axis = Pitch(midi=60, spelling="C", octave=4)
    v = Voice(id="v1", events=(make_note(67, Fraction(0), "G", 4),))  # G4 = C4+7
    iv = invert_melody(v, axis)
    assert iv.events[0].pitch.midi == 53  # C4-7 = F3  # type: ignore[union-attr]

def test_invert_melody_involution():
    """invert(invert(v, axis), axis) == v"""
    axis = Pitch(midi=60, spelling="C", octave=4)
    v = c_major_voice()
    assert invert_melody(invert_melody(v, axis), axis) == v


# ─── Retrograde inversion ────────────────────────────────────────────────────

def test_retrograde_inversion():
    axis = Pitch(midi=60, spelling="C", octave=4)
    v = c_major_voice()
    ri = retrograde_inversion(v, axis)
    # Should equal retrograde(invert_melody(v, axis))
    from transforms.melodic import invert_melody as im
    from transforms.temporal import retrograde as ret
    assert ri == ret(im(v, axis))


# ─── Mirror measure ───────────────────────────────────────────────────────────

def test_mirror_measure():
    m = simple_measure()
    axis = Pitch(midi=60, spelling="C", octave=4)
    mm = mirror_measure(m, axis)
    assert mm.number == m.number
    assert mm.time_signature == m.time_signature

def test_mirror_measure_auto_axis():
    m = simple_measure()
    mm = mirror_measure(m)  # axis auto-detected from first note (C4)
    assert len(mm.voices) == 1


# ─── Combinators ─────────────────────────────────────────────────────────────

def test_compose_two():
    v = c_major_voice()
    axis = Pitch(midi=60, spelling="C", octave=4)
    transform = compose(
        lambda x: retrograde(x),
        lambda x: invert_melody(x, axis),
    )
    result = transform(v)
    expected = retrograde(invert_melody(v, axis))
    assert result == expected

def test_compose_identity():
    v = c_major_voice()
    assert compose()(v) == v  # zero transforms → identity... actually raises IndexError? Let's check
    # Actually compose() with no args should return identity
    # The loop reversed([]) is empty so result stays x — correct.

def test_apply_to_voice():
    m = simple_measure()
    axis = Pitch(midi=60, spelling="C", octave=4)
    m2 = apply_to_voice(m, "v1", lambda v: invert_melody(v, axis))
    assert m2.voices[0] != m.voices[0]

def test_apply_to_voice_wrong_id():
    with pytest.raises(ValueError):
        apply_to_voice(simple_measure(), "v99", retrograde)

def test_apply_to_measure():
    v = c_major_voice()
    m = Measure(number=2, time_signature=TimeSignature(4, 4), voices=(v,))
    part = Part(name="P", instrument=None, clef="treble", measures=(m,))
    part2 = apply_to_measure(part, 2, retrograde_measure)
    orig_midis = [e.pitch.midi for e in part.measures[0].voices[0].events]  # type: ignore[union-attr]
    new_midis = [e.pitch.midi for e in part2.measures[0].voices[0].events]  # type: ignore[union-attr]
    assert new_midis == orig_midis[::-1]

def test_apply_to_all_measures():
    v = c_major_voice()
    m1 = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    m2 = Measure(number=2, time_signature=TimeSignature(4, 4), voices=(v,))
    part = Part(name="P", instrument=None, clef="treble", measures=(m1, m2))
    part2 = apply_to_all_measures(part, retrograde_measure)
    assert len(part2.measures) == 2

def test_apply_to_part():
    v = c_major_voice()
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    part = Part(name="Piano", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(part,), metadata={})
    score2 = apply_to_part(score, "Piano", lambda p: apply_to_all_measures(p, retrograde_measure))
    assert score2.title == "T"

def test_apply_to_part_wrong_name():
    score = Score(title="T", parts=(), metadata={})
    with pytest.raises(ValueError):
        apply_to_part(score, "Ghost", lambda p: p)
