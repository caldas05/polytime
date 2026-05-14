"""Tests for the music theory layer (Layer 2)."""
import pytest
from fractions import Fraction

from model.pitch import Pitch
from teoria.interval import Interval, between, compound_to_simple, is_consonant, is_dissonant
from teoria.pitch import interval_semitones, transpose, enharmonic_equivalent, interval_name, invert_interval
from teoria.scale import Scale, MAJOR, NATURAL_MINOR, PENTATONIC_MAJOR, contains, degree_of, scale_pitches, transpose_diatonic, detect_scale
from teoria.harmony import HarmonicChord, chord_pitches, chord_from_pitches, roman_numeral


# Helpers
def C4() -> Pitch: return Pitch(midi=60, spelling="C", octave=4)
def D4() -> Pitch: return Pitch(midi=62, spelling="D", octave=4)
def E4() -> Pitch: return Pitch(midi=64, spelling="E", octave=4)
def F4() -> Pitch: return Pitch(midi=65, spelling="F", octave=4)
def G4() -> Pitch: return Pitch(midi=67, spelling="G", octave=4)
def A4() -> Pitch: return Pitch(midi=69, spelling="A", octave=4)
def B4() -> Pitch: return Pitch(midi=71, spelling="B", octave=4)
def Cs4() -> Pitch: return Pitch(midi=61, spelling="C#", octave=4)
def Db4() -> Pitch: return Pitch(midi=61, spelling="Db", octave=4)
def Fs4() -> Pitch: return Pitch(midi=66, spelling="F#", octave=4)

def C_major() -> Scale: return Scale(root=C4(), intervals=MAJOR)


# ─── Interval ────────────────────────────────────────────────────────────────

def test_interval_between_ascending():
    iv = between(C4(), G4())
    assert iv.semitones == 7
    assert iv.direction == 1

def test_interval_between_descending():
    iv = between(G4(), C4())
    assert iv.semitones == 7
    assert iv.direction == -1

def test_interval_between_unison():
    iv = between(C4(), C4())
    assert iv.semitones == 0
    assert iv.direction == 1

def test_compound_to_simple():
    iv = Interval(semitones=14, direction=1)
    assert compound_to_simple(iv).semitones == 2

def test_is_consonant_p5():
    assert is_consonant(Interval(7, 1))

def test_is_dissonant_tritone():
    assert is_dissonant(Interval(6, 1))

def test_is_consonant_m3():
    assert is_consonant(Interval(3, 1))


# ─── Pitch functions ─────────────────────────────────────────────────────────

def test_interval_semitones_positive():
    assert interval_semitones(C4(), G4()) == 7

def test_interval_semitones_negative():
    assert interval_semitones(G4(), C4()) == -7

def test_transpose_up():
    g4 = transpose(C4(), 7)
    assert g4.midi == 67
    assert g4.spelling == "G"

def test_transpose_down():
    f3 = transpose(C4(), -7)
    assert f3.midi == 53

def test_transpose_out_of_range():
    with pytest.raises(ValueError):
        transpose(Pitch(midi=120, spelling="C", octave=9), 20)

def test_enharmonic_sharp_to_flat():
    result = enharmonic_equivalent(Cs4())
    assert result.spelling == "Db"
    assert result.midi == 61

def test_enharmonic_flat_to_sharp():
    result = enharmonic_equivalent(Db4())
    assert result.spelling == "C#"

def test_enharmonic_natural_unchanged():
    result = enharmonic_equivalent(C4())
    assert result.spelling == "C"

def test_interval_name_p5():
    assert interval_name(7) == "P5"

def test_interval_name_m3():
    assert interval_name(3) == "m3"

def test_interval_name_M3():
    assert interval_name(4) == "M3"

def test_interval_name_p8():
    assert interval_name(12) == "P8"

def test_invert_interval_p5():
    assert invert_interval(7) == 5  # P5 → P4

def test_invert_interval_M3():
    assert invert_interval(4) == 8  # M3 → m6


# ─── Scale ───────────────────────────────────────────────────────────────────

def test_contains_true():
    assert contains(C_major(), E4())

def test_contains_false():
    assert not contains(C_major(), Fs4())

def test_degree_of_tonic():
    assert degree_of(C_major(), C4()) == 1

def test_degree_of_dominant():
    assert degree_of(C_major(), G4()) == 5

def test_degree_of_not_in_scale():
    assert degree_of(C_major(), Fs4()) is None

def test_scale_pitches_major_count():
    pitches = scale_pitches(C_major(), 4)
    assert len(pitches) == 7

def test_scale_pitches_first_and_last():
    pitches = scale_pitches(C_major(), 4)
    assert pitches[0].spelling == "C"
    assert pitches[6].spelling == "B"

def test_transpose_diatonic_up():
    # C4 up 4 steps in C major → G4
    result = transpose_diatonic(C_major(), C4(), 4)
    assert result.midi == 67  # G4

def test_transpose_diatonic_not_in_scale():
    with pytest.raises(ValueError):
        transpose_diatonic(C_major(), Fs4(), 1)

def test_detect_scale_finds_major():
    pitches = scale_pitches(C_major(), 4)
    candidates = detect_scale(pitches)
    # C major should be among candidates
    roots = [s.root.pitch_class for s in candidates]
    assert 0 in roots  # C


# ─── Harmony ─────────────────────────────────────────────────────────────────

def test_chord_pitches_major_triad():
    chord = HarmonicChord(root=C4(), quality="maj", extensions=())
    pitches = chord_pitches(chord)
    midis = [p.midi for p in pitches]
    assert 60 in midis  # C4
    assert 64 in midis  # E4
    assert 67 in midis  # G4

def test_chord_from_pitches_major():
    c = chord_from_pitches((C4(), E4(), G4()))
    assert c.quality == "maj"
    assert c.root.midi == 60

def test_chord_from_pitches_minor():
    eb4 = Pitch(midi=63, spelling="Eb", octave=4)
    c = chord_from_pitches((C4(), eb4, G4()))
    assert c.quality == "min"

def test_roman_numeral_tonic():
    chord = HarmonicChord(root=C4(), quality="maj", extensions=())
    assert roman_numeral(C_major(), chord) == "I"

def test_roman_numeral_dominant():
    chord = HarmonicChord(root=G4(), quality="dom7", extensions=())
    assert roman_numeral(C_major(), chord) == "V"

def test_roman_numeral_supertonic_minor():
    chord = HarmonicChord(root=D4(), quality="min", extensions=())
    assert roman_numeral(C_major(), chord) == "ii"
