from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property


@dataclass(frozen=True)
class Duration:
    """A rhythmic duration where Fraction(1, 1) represents one beat (crotchet/quarter note).

    Example: Duration(value=Fraction(1, 2)) is a quaver (eighth note).
    Example: Duration(value=Fraction(1, 1), dots=1) is a dotted crotchet.
    Example: Duration(value=Fraction(1, 1), tuplet=(3, 2)) is a crotchet in a triplet.
    """

    value: Fraction
    dots: int = 0
    tuplet: tuple[int, int] | None = None  # (actual_divisor, written_divisor)

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(f"value must be positive, got {self.value}")
        if self.dots < 0:
            raise ValueError(f"dots must be >= 0, got {self.dots}")
        if self.tuplet is not None:
            a, b = self.tuplet
            if a <= 0 or b <= 0:
                raise ValueError(f"tuplet values must be positive, got {self.tuplet}")

    @cached_property
    def actual_beats(self) -> Fraction:
        """Real duration in beats after applying dots and tuplet.

        Example: dotted quarter → Fraction(3, 2).
        Example: quarter in triplet (3,2) → Fraction(2, 3).
        """
        # Dotted value = value * (2 - 1/2^dots)
        scale = Fraction(2 ** (self.dots + 1) - 1, 2 ** self.dots)
        base = self.value * scale
        if self.tuplet is not None:
            actual_div, written_div = self.tuplet
            base = base * Fraction(written_div, actual_div)
        return base
