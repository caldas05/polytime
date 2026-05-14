from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from model.pitch import Pitch
from model.duration import Duration


@dataclass(frozen=True)
class Note:
    """A single pitched note.

    Example: Note(duration=quarter, offset=Fraction(0), pitch=Pitch(60, "C", 4))
    """

    duration: Duration
    offset: Fraction
    pitch: Pitch
    dynamic: str | None = None
    articulations: tuple[str, ...] = ()
    tie: str | None = None
    staff: int = 1
    is_grace: bool = False
    slur: str | None = None

    def __post_init__(self) -> None:
        if self.tie is not None and self.tie not in ("start", "stop", "continue"):
            raise ValueError(f"tie must be 'start', 'stop', 'continue', or None, got {self.tie!r}")
        if self.staff < 1:
            raise ValueError(f"staff must be >= 1, got {self.staff}")
        if self.slur is not None and self.slur not in ("start", "stop"):
            raise ValueError(f"slur must be 'start', 'stop', or None, got {self.slur!r}")


@dataclass(frozen=True)
class Rest:
    """A silent rest.

    Example: Rest(duration=quarter, offset=Fraction(1, 1))
    """

    duration: Duration
    offset: Fraction
    staff: int = 1

    def __post_init__(self) -> None:
        if self.staff < 1:
            raise ValueError(f"staff must be >= 1, got {self.staff}")


@dataclass(frozen=True)
class Chord:
    """Two or more simultaneous pitches.

    Example: Chord(duration=quarter, offset=Fraction(0), pitches=(C4, E4, G4))
    """

    duration: Duration
    offset: Fraction
    pitches: tuple[Pitch, ...]
    dynamic: str | None = None
    articulations: tuple[str, ...] = ()
    tie: str | None = None
    staff: int = 1
    is_grace: bool = False
    slur: str | None = None

    def __post_init__(self) -> None:
        if len(self.pitches) < 2:
            raise ValueError(f"Chord requires at least 2 pitches, got {len(self.pitches)}")
        if self.tie is not None and self.tie not in ("start", "stop", "continue"):
            raise ValueError(f"tie must be 'start', 'stop', 'continue', or None, got {self.tie!r}")
        if self.staff < 1:
            raise ValueError(f"staff must be >= 1, got {self.staff}")
        if self.slur is not None and self.slur not in ("start", "stop"):
            raise ValueError(f"slur must be 'start', 'stop', or None, got {self.slur!r}")


Event = Note | Rest | Chord
