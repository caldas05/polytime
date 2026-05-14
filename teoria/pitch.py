from __future__ import annotations

from model.pitch import Pitch

# Default spellings for each pitch class (sharps preferred, except Bb)
_DEFAULT_SPELLING: dict[int, str] = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E",
    5: "F", 6: "F#", 7: "G", 8: "G#", 9: "A",
    10: "Bb", 11: "B",
}

# Enharmonic pairs: spelling → alternative spelling
_ENHARMONIC: dict[str, str] = {
    "C#": "Db", "Db": "C#",
    "D#": "Eb", "Eb": "D#",
    "F#": "Gb", "Gb": "F#",
    "G#": "Ab", "Ab": "G#",
    "A#": "Bb", "Bb": "A#",
    "B#": "C",  "Cb": "B",
    "E#": "F",  "Fb": "E",
}

# Interval quality names by semitone count (simple, 0–12)
_INTERVAL_NAMES: dict[int, str] = {
    0: "P1", 1: "m2", 2: "M2", 3: "m3", 4: "M3",
    5: "P4", 6: "A4", 7: "P5", 8: "m6", 9: "M6",
    10: "m7", 11: "M7", 12: "P8",
}


def pitch_from_midi(midi: int, spelling: str | None = None) -> Pitch:
    """Build a Pitch from a MIDI number using the default spelling unless overridden."""
    pc = midi % 12
    return Pitch(
        midi=midi,
        spelling=spelling if spelling is not None else _DEFAULT_SPELLING[pc],
        octave=midi // 12 - 1,
    )


def interval_semitones(a: Pitch, b: Pitch) -> int:
    """Signed semitone distance from a to b (positive = ascending).

    Example: interval_semitones(C4, G4) → 7.
    Example: interval_semitones(G4, C4) → -7.
    """
    return b.midi - a.midi


def transpose(pitch: Pitch, semitones: int) -> Pitch:
    """Return a new Pitch transposed by the given number of semitones.

    Example: transpose(Pitch(60, "C", 4), 7) → Pitch(67, "G", 4).
    """
    new_midi = pitch.midi + semitones
    if not (0 <= new_midi <= 127):
        raise ValueError(f"Transposed midi {new_midi} is out of range 0–127")
    return pitch_from_midi(new_midi)


def enharmonic_equivalent(pitch: Pitch) -> Pitch:
    """Return the enharmonic equivalent of the given pitch.

    Example: enharmonic_equivalent(Pitch(61, "C#", 4)) → Pitch(61, "Db", 4).
    Example: enharmonic_equivalent(Pitch(60, "C", 4)) → Pitch(60, "C", 4) (no change).
    """
    alt = _ENHARMONIC.get(pitch.spelling)
    if alt is None:
        return pitch
    # Octave may shift for B#→C and Cb→B crossings
    return pitch_from_midi(pitch.midi, spelling=alt)


def interval_name(semitones: int) -> str:
    """Return the quality-number name for a simple interval in semitones.

    Example: interval_name(7) → "P5".
    Example: interval_name(4) → "M3".
    Compound intervals are reduced to their simple form.
    """
    simple = abs(semitones) % 12
    # Handle octave: abs(semitones)==12 → P8
    if abs(semitones) == 12:
        return "P8"
    name = _INTERVAL_NAMES.get(simple)
    if name is None:
        raise ValueError(f"Cannot name interval of {semitones} semitones")
    return name


def invert_interval(semitones: int, octave_semitones: int = 12) -> int:
    """Return the inversion of a simple interval within the given octave.

    Example: invert_interval(7) → 5 (P5 inverts to P4).
    Example: invert_interval(4) → 8 (M3 inverts to m6).
    """
    return octave_semitones - (abs(semitones) % octave_semitones)
