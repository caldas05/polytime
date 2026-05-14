from __future__ import annotations
from dataclasses import dataclass

from model.pitch import Pitch
from teoria.pitch import transpose, _DEFAULT_SPELLING, pitch_from_midi
from teoria.scale import Scale, degree_of

# Chord quality interval patterns (semitones above root)
_QUALITY_INTERVALS: dict[str, tuple[int, ...]] = {
    "maj":   (0, 4, 7),
    "min":   (0, 3, 7),
    "dim":   (0, 3, 6),
    "aug":   (0, 4, 8),
    "maj7":  (0, 4, 7, 11),
    "min7":  (0, 3, 7, 10),
    "dom7":  (0, 4, 7, 10),
    "dim7":  (0, 3, 6, 9),
    "hdim7": (0, 3, 6, 10),
}

# Roman numerals 1–7
_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]


@dataclass(frozen=True)
class HarmonicChord:
    """An abstract harmonic chord (not to be confused with model.Chord).

    Example: HarmonicChord(root=C4, quality="maj", extensions=()) is a C major triad.
    Example: HarmonicChord(root=G4, quality="dom7", extensions=()) is a G dominant seventh.
    """

    root: Pitch
    quality: str
    extensions: tuple[int, ...]  # additional semitones above root beyond quality


def chord_pitches(chord: HarmonicChord) -> tuple[Pitch, ...]:
    """Return all pitches of a harmonic chord in root position.

    Example: chord_pitches(C_maj) → (C4, E4, G4).
    """
    base = _QUALITY_INTERVALS.get(chord.quality, (0,))
    all_intervals = base + chord.extensions
    pitches = []
    for interval in all_intervals:
        new_midi = chord.root.midi + interval
        if 0 <= new_midi <= 127:
            pitches.append(pitch_from_midi(new_midi))
    return tuple(pitches)


def chord_from_pitches(pitches: tuple[Pitch, ...]) -> HarmonicChord:
    """Identify the chord quality from a set of pitches.

    Uses the lowest pitch as root. Raises ValueError if unrecognised.

    Example: chord_from_pitches((C4, E4, G4)) → HarmonicChord(C4, "maj", ()).
    """
    if not pitches:
        raise ValueError("Cannot identify chord from empty pitches")
    sorted_pitches = sorted(pitches, key=lambda p: p.midi)
    root = sorted_pitches[0]
    intervals = tuple(sorted(set((p.midi - root.midi) % 12 for p in sorted_pitches)))
    for quality, pattern in _QUALITY_INTERVALS.items():
        if tuple(sorted(set(pattern))) == intervals:
            return HarmonicChord(root=root, quality=quality, extensions=())
    # Unknown quality — store raw intervals as extensions
    return HarmonicChord(root=root, quality="unknown", extensions=intervals[1:])


def roman_numeral(scale: Scale, chord: HarmonicChord) -> str:
    """Return the Roman numeral function of a chord within a scale.

    Example: roman_numeral(C_major, G_dom7) → "V".
    Raises ValueError if the chord root is not in the scale.
    """
    deg = degree_of(scale, chord.root)
    if deg is None:
        raise ValueError(f"Chord root {chord.root.spelling} is not in the scale")
    numeral = _ROMAN[deg - 1]
    if "min" in chord.quality or "dim" in chord.quality:
        numeral = numeral.lower()
    return numeral
