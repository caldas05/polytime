from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction

from model.events import Note, Rest, Chord
from model.voice import Voice


@dataclass(frozen=True)
class TimeSignature:
    """A time signature such as 4/4 or 3/8.

    Example: TimeSignature(numerator=4, denominator=4)
    """

    numerator: int
    denominator: int

    @property
    def beats_per_measure(self) -> Fraction:
        """Capacity in beats (quarter notes) per measure.

        Since the model beat unit is the quarter note (Fraction(1,1)),
        each denominator-th note is worth Fraction(4, denominator) beats.
        Total capacity = numerator * Fraction(4, denominator).

        Example: 4/4 → 4 beats; 6/8 → 3 beats; 3/4 → 3 beats.
        """
        return Fraction(self.numerator * 4, self.denominator)


@dataclass(frozen=True)
class KeySignature:
    """A key signature expressed as a count of sharps/flats and a mode.

    `fifths` follows the MusicXML convention: positive = sharps, negative = flats,
    so 0 = C major / A minor, 2 = D major / B minor, -3 = Eb major / C minor.
    `mode` is "major" or "minor".

    Example: KeySignature(fifths=2, mode="major") — D major.
    """

    fifths: int
    mode: str = "major"

    def __post_init__(self) -> None:
        if not -7 <= self.fifths <= 7:
            raise ValueError(f"fifths must be in [-7, 7], got {self.fifths}")
        if self.mode not in ("major", "minor"):
            raise ValueError(f"mode must be 'major' or 'minor', got {self.mode!r}")


@dataclass(frozen=True)
class TempoMark:
    """A tempo marking in BPM for a given beat unit.

    Example: TempoMark(bpm=120.0, beat_unit=Fraction(1, 1)) — 120 crotchets per minute.
    """

    bpm: float
    beat_unit: Fraction


@dataclass(frozen=True)
class Measure:
    """A single measure containing one or more simultaneous voices.

    The time signature describes the *intended* meter — i.e. where the
    barline falls — but it is not enforced as a hard capacity. A voice may
    contain more total beats than the time signature suggests; the extra
    material is treated as spilling past the barline. Sequential serializers
    (LilyPond) may render this awkwardly, but MIDI playback and the
    transform/visualization pipeline handle it gracefully.

    Example: Measure(number=1, time_signature=TimeSignature(4, 4), voices=(voice,))
    """

    number: int
    time_signature: TimeSignature
    voices: tuple[Voice, ...]
    tempo: TempoMark | None = None
    key_signature: KeySignature | None = None
