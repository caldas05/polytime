from __future__ import annotations
from dataclasses import dataclass

from model.pitch import Pitch


@dataclass(frozen=True)
class Interval:
    """A directed interval measured in semitones.

    Example: Interval(semitones=7, direction=1) is a perfect fifth upward.
    Example: Interval(semitones=5, direction=-1) is a perfect fourth downward.
    """

    semitones: int   # always non-negative
    direction: int   # +1 (ascending) or -1 (descending)

    def __post_init__(self) -> None:
        if self.semitones < 0:
            raise ValueError(f"semitones must be >= 0, got {self.semitones}")
        if self.direction not in (1, -1):
            raise ValueError(f"direction must be +1 or -1, got {self.direction}")


def between(a: Pitch, b: Pitch) -> Interval:
    """Interval from pitch a to pitch b.

    Example: between(C4, G4) → Interval(7, +1).
    Example: between(G4, C4) → Interval(7, -1).
    """
    diff = b.midi - a.midi
    if diff == 0:
        return Interval(semitones=0, direction=1)
    return Interval(semitones=abs(diff), direction=1 if diff > 0 else -1)


def compound_to_simple(interval: Interval) -> Interval:
    """Reduce a compound interval to its simple equivalent within one octave.

    Example: compound_to_simple(Interval(14, 1)) → Interval(2, 1).
    """
    return Interval(semitones=interval.semitones % 12, direction=interval.direction)


# Consonant intervals: unison, minor 3rd, major 3rd, perfect 4th, perfect 5th,
# minor 6th, major 6th, octave
_CONSONANT = {0, 3, 4, 5, 7, 8, 9, 12}


def is_consonant(interval: Interval) -> bool:
    """Return True for consonant intervals (simple, within one octave).

    Example: is_consonant(Interval(7, 1)) → True (perfect fifth).
    Example: is_consonant(Interval(6, 1)) → False (tritone).
    """
    return (interval.semitones % 12) in _CONSONANT


def is_dissonant(interval: Interval) -> bool:
    """Return True for dissonant intervals.

    Example: is_dissonant(Interval(6, 1)) → True (tritone).
    """
    return not is_consonant(interval)
