"""Tests for the I/O layer (Layer 4): serializer and renderer."""
import pytest
from fractions import Fraction

from model.pitch import Pitch
from model.duration import Duration
from model.events import Note, Rest, Chord
from model.voice import Voice
from model.measure import Measure, TimeSignature, TempoMark, KeySignature
from model.part import Part
from model.score import Score
from score_io.serializers.lilypond import serialize, SerializeError
from score_io.renderer import render


# ─── Helpers ──────────────────────────────────────────────────────────────────

def quarter() -> Duration:
    return Duration(value=Fraction(1, 1))

def half() -> Duration:
    return Duration(value=Fraction(2, 1))

def make_score(title: str = "Test") -> Score:
    c4 = Pitch(midi=60, spelling="C", octave=4)
    n = Note(duration=quarter(), offset=Fraction(0), pitch=c4)
    d4 = Pitch(midi=62, spelling="D", octave=4)
    n2 = Note(duration=quarter(), offset=Fraction(1), pitch=d4)
    e4 = Pitch(midi=64, spelling="E", octave=4)
    n3 = Note(duration=quarter(), offset=Fraction(2), pitch=e4)
    f4 = Pitch(midi=65, spelling="F", octave=4)
    n4 = Note(duration=quarter(), offset=Fraction(3), pitch=f4)
    voice = Voice(id="v1", events=(n, n2, n3, n4))
    measure = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(voice,))
    part = Part(name="Piano", instrument=None, clef="treble", measures=(measure,))
    return Score(title=title, parts=(part,), metadata={})


# ─── LilyPond serializer ─────────────────────────────────────────────────────

def test_serialize_contains_version():
    ly = serialize(make_score())
    assert '\\version "2.24.0"' in ly

def test_serialize_contains_title():
    ly = serialize(make_score("My Piece"))
    assert 'My Piece' in ly

def test_serialize_contains_clef():
    ly = serialize(make_score())
    assert "\\clef treble" in ly

def test_serialize_contains_time():
    ly = serialize(make_score())
    assert "\\time 4/4" in ly

def test_serialize_c4_quarter():
    ly = serialize(make_score())
    # C4 in LilyPond is c' (one octave above c3), quarter = "2" (mínima)
    # Model beat = quarter note = Fraction(1,1) → lily "4" (quarter)
    # C4 = octave 4 → c' (4-3=1 tick)
    assert "c'" in ly

def test_serialize_rest():
    r = Rest(duration=quarter(), offset=Fraction(0))
    v = Voice(id="v1", events=(r,) * 4)
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "r4" in ly  # rest quarter = "r4" in lily

def test_serialize_dotted_duration():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    dotted_half = Duration(value=Fraction(2, 1), dots=1)  # 3 beats
    n1 = Note(duration=dotted_half, offset=Fraction(0), pitch=c4)
    g4 = Pitch(midi=67, spelling="G", octave=4)
    n2 = Note(duration=quarter(), offset=Fraction(3), pitch=g4)
    v = Voice(id="v1", events=(n1, n2))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "2." in ly  # dotted half

def _key_score(key: KeySignature) -> Score:
    s = make_score()
    p = s.parts[0]
    m = p.measures[0]
    new_m = Measure(
        number=m.number, time_signature=m.time_signature,
        voices=m.voices, tempo=m.tempo, key_signature=key,
    )
    new_p = Part(name=p.name, instrument=p.instrument, clef=p.clef, measures=(new_m,))
    return Score(title=s.title, parts=(new_p,), metadata=s.metadata)


def test_lily_key_d_major():
    ly = serialize(_key_score(KeySignature(fifths=2, mode="major")))
    assert "\\key d \\major" in ly

def test_lily_key_c_minor():
    ly = serialize(_key_score(KeySignature(fifths=-3, mode="minor")))
    assert "\\key c \\minor" in ly

def test_lily_key_omitted_when_none():
    ly = serialize(make_score())
    assert "\\key" not in ly

def _tied_score(tie_first: str, tie_second: str | None) -> Score:
    c4 = Pitch(midi=60, spelling="C", octave=4)
    h = Duration(value=Fraction(2, 1))
    n1 = Note(duration=h, offset=Fraction(0), pitch=c4, tie=tie_first)
    n2 = Note(duration=h, offset=Fraction(2), pitch=c4, tie=tie_second)
    v = Voice(id="v1", events=(n1, n2))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    return Score(title="T", parts=(p,), metadata={})


def test_lily_tie_emits_tilde_on_start():
    ly = serialize(_tied_score("start", "stop"))
    # First C4 half-note should be c'2~ (lily duration code "2" = model half), no ~ on second.
    assert "c'2~" in ly
    # Second note has no tie marker — count tildes
    assert ly.count("~") == 1

def test_lily_tie_emits_tilde_on_continue():
    ly = serialize(_tied_score("start", "continue"))
    assert ly.count("~") == 2

def test_invalid_tie_value_rejected():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    with pytest.raises(ValueError):
        Note(duration=quarter(), offset=Fraction(0), pitch=c4, tie="bogus")


def _piano_score() -> Score:
    """Two-staff piano score: RH treble C4 quarter, LH bass C2 quarter."""
    rh = Pitch(midi=60, spelling="C", octave=4)
    lh = Pitch(midi=36, spelling="C", octave=2)
    rh_voice = Voice(id="1", events=(
        Note(duration=quarter(), offset=Fraction(0), pitch=rh, staff=1),
    ) + tuple(
        Note(duration=quarter(), offset=Fraction(i), pitch=rh, staff=1)
        for i in (1, 2, 3)
    ))
    lh_voice = Voice(id="s2_1", events=tuple(
        Note(duration=quarter(), offset=Fraction(i), pitch=lh, staff=2)
        for i in range(4)
    ))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(rh_voice, lh_voice))
    p = Part(name="Piano", instrument="piano", clef="treble",
             measures=(m,), extra_staff_clefs=("bass",))
    return Score(title="T", parts=(p,), metadata={})


def test_part_staff_count():
    s = _piano_score()
    assert s.parts[0].staff_count == 2
    assert s.parts[0].staff_clef(1) == "treble"
    assert s.parts[0].staff_clef(2) == "bass"

def test_lily_pianostaff_emitted():
    ly = serialize(_piano_score())
    assert "\\new PianoStaff" in ly
    # Both staves and both clefs present
    assert ly.count("\\new Staff") == 2
    assert "\\clef treble" in ly
    assert "\\clef bass" in ly

def test_lily_voice_filter_routes_events_by_staff():
    ly = serialize(_piano_score())
    # Find the two staff blocks; treble block should contain c' (C4),
    # bass block should contain c, (C2). Split on PianoStaff to inspect.
    treble_idx = ly.index("\\clef treble", ly.index("PianoStaff"))
    bass_idx = ly.index("\\clef bass")
    treble_block = ly[treble_idx:bass_idx]
    bass_block = ly[bass_idx:]
    assert "c'" in treble_block
    assert "c," in bass_block
    # And NOT crossed
    assert "c'" not in bass_block
    assert "c," not in treble_block

def _triplet_score() -> Score:
    """4/4 measure with one quarter then a triplet of eighth notes
    (3 in the time of 2), then nothing else (we'll fill with rest)."""
    c4 = Pitch(midi=60, spelling="C", octave=4)
    d4 = Pitch(midi=62, spelling="D", octave=4)
    e4 = Pitch(midi=64, spelling="E", octave=4)
    eighth = Duration(value=Fraction(1, 2), tuplet=(3, 2))
    n1 = Note(duration=eighth, offset=Fraction(0), pitch=c4)
    n2 = Note(duration=eighth, offset=Fraction(1, 3), pitch=d4)
    n3 = Note(duration=eighth, offset=Fraction(2, 3), pitch=e4)
    rest = Rest(duration=Duration(value=Fraction(1, 1)), offset=Fraction(1))
    rest2 = Rest(duration=Duration(value=Fraction(2, 1)), offset=Fraction(2))
    v = Voice(id="1", events=(n1, n2, n3, rest, rest2))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    return Score(title="T", parts=(p,), metadata={})


def test_lily_emits_tuplet_wrapper():
    ly = serialize(_triplet_score())
    assert "\\tuplet 3/2 {" in ly
    # Inside the tuplet, each note gets the *written* duration (eighth = "8")
    assert "c'8" in ly
    assert "d'8" in ly
    assert "e'8" in ly

def test_lily_tuplet_wrapper_does_not_swallow_following_events():
    ly = serialize(_triplet_score())
    # The rest after the triplet must appear OUTSIDE the bracket
    tup_close = ly.index("}", ly.index("\\tuplet"))
    after = ly[tup_close:]
    assert "r" in after  # rest exists after the triplet group

def test_lily_duration_no_longer_scales_for_tuplet():
    """Regression: previously _lily_duration applied the tuplet ratio
    producing non-power-of-two values that always raised. Now the base
    value is emitted and \\tuplet handles the ratio externally."""
    # A quarter-note triplet (actual 3, normal 2) — base value Fraction(1,1).
    # Should serialize without error and produce "4" as the duration code.
    c4 = Pitch(midi=60, spelling="C", octave=4)
    qt = Duration(value=Fraction(1, 1), tuplet=(3, 2))
    notes = tuple(Note(duration=qt, offset=Fraction(i, 1) * Fraction(2, 3), pitch=c4)
                  for i in range(3))
    rest = Rest(duration=Duration(value=Fraction(2, 1)), offset=Fraction(2))
    v = Voice(id="1", events=notes + (rest,))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "\\tuplet 3/2 {" in ly
    assert "c'4" in ly  # quarter note → "4" in lily


def _grace_score() -> Score:
    """4/4 measure: grace eighth (D4) → quarter (C4) → three more quarters."""
    c4 = Pitch(midi=60, spelling="C", octave=4)
    d4 = Pitch(midi=62, spelling="D", octave=4)
    eighth = Duration(value=Fraction(1, 2))
    grace = Note(duration=eighth, offset=Fraction(0), pitch=d4, is_grace=True)
    n_quarter = Note(duration=quarter(), offset=Fraction(0), pitch=c4)
    fillers = tuple(
        Note(duration=quarter(), offset=Fraction(i), pitch=c4) for i in (1, 2, 3)
    )
    v = Voice(id="1", events=(grace, n_quarter) + fillers)
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    return Score(title="T", parts=(p,), metadata={})


def test_grace_does_not_count_against_capacity():
    # Constructing _grace_score must not raise — voice has 4 quarters of real
    # content plus a grace; capacity check should ignore the grace.
    s = _grace_score()
    assert s.parts[0].measures[0].voices[0].events[0].is_grace

def test_lily_emits_grace_block():
    ly = serialize(_grace_score())
    # The grace D should appear inside \grace { ... } before the host C
    assert "\\grace { d'8 } c'4" in ly

def test_grace_run_attaches_to_next_host():
    """Multiple consecutive graces should all attach to the next non-grace."""
    c4 = Pitch(midi=60, spelling="C", octave=4)
    d4 = Pitch(midi=62, spelling="D", octave=4)
    e4 = Pitch(midi=64, spelling="E", octave=4)
    eighth = Duration(value=Fraction(1, 2))
    g1 = Note(duration=eighth, offset=Fraction(0), pitch=d4, is_grace=True)
    g2 = Note(duration=eighth, offset=Fraction(0), pitch=e4, is_grace=True)
    n = Note(duration=quarter(), offset=Fraction(0), pitch=c4)
    fillers = tuple(
        Note(duration=quarter(), offset=Fraction(i), pitch=c4) for i in (1, 2, 3)
    )
    v = Voice(id="1", events=(g1, g2, n) + fillers)
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "\\grace { d'8 e'8 } c'4" in ly


def _dynamics_score() -> Score:
    c4 = Pitch(midi=60, spelling="C", octave=4)
    n1 = Note(duration=quarter(), offset=Fraction(0), pitch=c4, dynamic="p")
    n2 = Note(duration=quarter(), offset=Fraction(1), pitch=c4, dynamic="p")  # unchanged
    n3 = Note(duration=quarter(), offset=Fraction(2), pitch=c4, dynamic="f")  # change
    n4 = Note(duration=quarter(), offset=Fraction(3), pitch=c4, dynamic="f")
    v = Voice(id="1", events=(n1, n2, n3, n4))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    return Score(title="T", parts=(p,), metadata={})


def test_lily_emits_dynamic_after_note():
    ly = serialize(_dynamics_score())
    # First note carries \\p, third carries \\f
    assert "c'4\\p" in ly
    assert "c'4\\f" in ly


def _slur_score() -> Score:
    """4-note phrase: C-D-E-F where the slur spans the first three notes."""
    pitches = [Pitch(midi=m, spelling=s, octave=4)
               for m, s in [(60, "C"), (62, "D"), (64, "E"), (65, "F")]]
    n1 = Note(duration=quarter(), offset=Fraction(0), pitch=pitches[0], slur="start")
    n2 = Note(duration=quarter(), offset=Fraction(1), pitch=pitches[1])
    n3 = Note(duration=quarter(), offset=Fraction(2), pitch=pitches[2], slur="stop")
    n4 = Note(duration=quarter(), offset=Fraction(3), pitch=pitches[3])
    v = Voice(id="1", events=(n1, n2, n3, n4))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    return Score(title="T", parts=(p,), metadata={})


def test_lily_emits_slur_parens():
    ly = serialize(_slur_score())
    assert "c'4(" in ly
    assert "e'4)" in ly
    # Middle and trailing notes are bare
    assert "d'4 " in ly or ly.endswith("d'4")
    assert ly.count("(") == 1
    assert ly.count(")") == 1

def test_invalid_slur_value_rejected():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    with pytest.raises(ValueError):
        Note(duration=quarter(), offset=Fraction(0), pitch=c4, slur="bogus")

def test_slur_and_tie_coexist_on_same_note():
    """A note can both end a slur and start a tie. Make sure both render."""
    c4 = Pitch(midi=60, spelling="C", octave=4)
    n1 = Note(duration=quarter(), offset=Fraction(0), pitch=c4, slur="start")
    n2 = Note(duration=quarter(), offset=Fraction(1), pitch=c4,
              slur="stop", tie="start")
    n3 = Note(duration=quarter(), offset=Fraction(2), pitch=c4, tie="stop")
    n4 = Note(duration=quarter(), offset=Fraction(3), pitch=c4)
    v = Voice(id="1", events=(n1, n2, n3, n4))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    # n2 has tie=start and slur=stop → both ~ and ) appear on it.
    # In our emit order: pitch + duration + tie_mark + slur_mark → c'4~)
    assert "c'4~)" in ly


def test_invalid_staff_value_rejected():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    with pytest.raises(ValueError):
        Note(duration=quarter(), offset=Fraction(0), pitch=c4, staff=0)
    with pytest.raises(ValueError):
        Rest(duration=quarter(), offset=Fraction(0), staff=-1)


def test_serialize_two_voices():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    g4 = Pitch(midi=67, spelling="G", octave=4)
    n1 = Note(duration=quarter(), offset=Fraction(0), pitch=c4)
    n2 = Note(duration=quarter(), offset=Fraction(0), pitch=g4)
    v1 = Voice(id="v1", events=(n1,) * 4)
    v2 = Voice(id="v2", events=(n2,) * 4)
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v1, v2))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "<<" in ly
    assert "\\\\" in ly

def test_serialize_tempo():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    n = Note(duration=quarter(), offset=Fraction(0), pitch=c4)
    v = Voice(id="v1", events=(n,) * 4)
    tempo = TempoMark(bpm=120.0, beat_unit=Fraction(1, 1))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,), tempo=tempo)
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "\\tempo" in ly
    assert "120" in ly

def test_serialize_chord():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    e4 = Pitch(midi=64, spelling="E", octave=4)
    chord = Chord(duration=quarter(), offset=Fraction(0), pitches=(c4, e4))
    n2 = Note(duration=quarter(), offset=Fraction(1), pitch=c4)
    n3 = Note(duration=quarter(), offset=Fraction(2), pitch=c4)
    n4 = Note(duration=quarter(), offset=Fraction(3), pitch=c4)
    v = Voice(id="v1", events=(chord, n2, n3, n4))
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "<c' e'>" in ly

def test_serialize_flat_pitch():
    bb4 = Pitch(midi=70, spelling="Bb", octave=4)
    n = Note(duration=quarter(), offset=Fraction(0), pitch=bb4)
    v = Voice(id="v1", events=(n,) * 4)
    m = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m,))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "bes'" in ly

def test_serialize_time_changes():
    c4 = Pitch(midi=60, spelling="C", octave=4)
    n = Note(duration=quarter(), offset=Fraction(0), pitch=c4)
    v1 = Voice(id="v1", events=(n,) * 4)
    v2 = Voice(id="v1", events=(n,) * 3)
    m1 = Measure(number=1, time_signature=TimeSignature(4, 4), voices=(v1,))
    m2 = Measure(number=2, time_signature=TimeSignature(3, 4), voices=(v2,))
    p = Part(name="P", instrument=None, clef="treble", measures=(m1, m2))
    score = Score(title="T", parts=(p,), metadata={})
    ly = serialize(score)
    assert "\\time 3/4" in ly


# ─── Renderer ────────────────────────────────────────────────────────────────

def test_render_missing_lilypond(monkeypatch):
    """render() raises EnvironmentError when lilypond is not on PATH."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(EnvironmentError, match="LilyPond"):
        render("dummy source", "output/test")
