from __future__ import annotations
from dataclasses import dataclass

from model.pitch import Pitch
from teoria.pitch import transpose, _DEFAULT_SPELLING, pitch_from_midi

# Scale interval patterns (semitones from root, not including the octave repeat)
MAJOR           = (0, 2, 4, 5, 7, 9, 11)
NATURAL_MINOR   = (0, 2, 3, 5, 7, 8, 10)
DORIAN          = (0, 2, 3, 5, 7, 9, 10)
PHRYGIAN        = (0, 1, 3, 5, 7, 8, 10)
LYDIAN          = (0, 2, 4, 6, 7, 9, 11)
MIXOLYDIAN      = (0, 2, 4, 5, 7, 9, 10)
LOCRIAN         = (0, 1, 3, 5, 6, 8, 10)
HARMONIC_MINOR  = (0, 2, 3, 5, 7, 8, 11)
MELODIC_MINOR   = (0, 2, 3, 5, 7, 9, 11)
CHROMATIC       = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
WHOLE_TONE      = (0, 2, 4, 6, 8, 10)
PENTATONIC_MAJOR = (0, 2, 4, 7, 9)

# All named patterns for detect_scale, with each pattern's pitch-class set
# precomputed at root 0 (rotate per root by adding root_pc mod 12).
_ALL_PATTERNS: list[tuple[str, tuple[int, ...], frozenset[int]]] = [
    (name, pattern, frozenset(pattern))
    for name, pattern in (
        ("major", MAJOR),
        ("natural_minor", NATURAL_MINOR),
        ("dorian", DORIAN),
        ("phrygian", PHRYGIAN),
        ("lydian", LYDIAN),
        ("mixolydian", MIXOLYDIAN),
        ("locrian", LOCRIAN),
        ("harmonic_minor", HARMONIC_MINOR),
        ("melodic_minor", MELODIC_MINOR),
        ("chromatic", CHROMATIC),
        ("whole_tone", WHOLE_TONE),
        ("pentatonic_major", PENTATONIC_MAJOR),
    )
]


@dataclass(frozen=True)
class Scale:
    """A scale defined by a root pitch and an interval pattern in semitones.

    Example: Scale(root=Pitch(60, "C", 4), intervals=MAJOR) is C major.
    """

    root: Pitch
    intervals: tuple[int, ...]


def contains(scale: Scale, pitch: Pitch) -> bool:
    """Return True if the pitch belongs to the scale (octave-independent).

    Example: contains(C_major, E4) → True.
    Example: contains(C_major, F#4) → False.
    """
    root_pc = scale.root.pitch_class
    pitch_pc = pitch.pitch_class
    return any((root_pc + interval) % 12 == pitch_pc for interval in scale.intervals)


def degree_of(scale: Scale, pitch: Pitch) -> int | None:
    """Return the 1-based scale degree of the pitch, or None if not in scale.

    Example: degree_of(C_major, G4) → 5.
    """
    root_pc = scale.root.pitch_class
    pitch_pc = pitch.pitch_class
    for i, interval in enumerate(scale.intervals):
        if (root_pc + interval) % 12 == pitch_pc:
            return i + 1
    return None


def scale_pitches(scale: Scale, octave: int) -> tuple[Pitch, ...]:
    """Return all pitches of the scale in the given octave.

    Example: scale_pitches(C_major, 4) → (C4, D4, E4, F4, G4, A4, B4).
    """
    root_midi = (octave + 1) * 12 + scale.root.pitch_class
    pitches = []
    for interval in scale.intervals:
        midi = root_midi + interval
        if 0 <= midi <= 127:
            pitches.append(pitch_from_midi(midi))
    return tuple(pitches)


def transpose_diatonic(scale: Scale, pitch: Pitch, steps: int) -> Pitch:
    """Transpose a pitch by N diatonic steps within the scale.

    Example: transpose_diatonic(C_major, C4, 4) → G4 (up 4 steps: C→D→E→F→G).
    Raises ValueError if pitch is not in the scale.
    """
    deg = degree_of(scale, pitch)
    if deg is None:
        raise ValueError(f"{pitch.spelling} is not in the scale")
    n = len(scale.intervals)
    current_idx = deg - 1
    target_idx = (current_idx + steps) % n
    octave_shift = (current_idx + steps) // n

    root_pc = scale.root.pitch_class
    target_semitones = scale.intervals[target_idx]
    root_midi = pitch.midi - scale.intervals[current_idx]
    # Adjust root_midi to the root's octave
    new_midi = root_midi + target_semitones + octave_shift * 12
    if not (0 <= new_midi <= 127):
        raise ValueError(f"Transposed midi {new_midi} is out of range 0–127")
    return pitch_from_midi(new_midi)


def detect_scale(pitches: tuple[Pitch, ...]) -> list[Scale]:
    """Return candidate scales that contain every input pitch class,
    ordered by tightest fit (fewest extra scale notes first).

    Example: detect_scale((C4, D4, E4, G4, A4)) ranks C pentatonic major above
    C major, since both contain the input but pentatonic has fewer extra notes.
    """
    pitch_classes = {p.pitch_class for p in pitches}
    results: list[tuple[int, Scale]] = []

    for root_pc in range(12):
        root_pitch = pitch_from_midi(60 + root_pc)
        for _name, pattern, base_pcs in _ALL_PATTERNS:
            scale_pcs = {(pc + root_pc) % 12 for pc in base_pcs}
            if pitch_classes <= scale_pcs:
                extras = len(scale_pcs) - len(pitch_classes)
                results.append((extras, Scale(root=root_pitch, intervals=pattern)))

    results.sort(key=lambda x: x[0])
    return [s for _, s in results]
