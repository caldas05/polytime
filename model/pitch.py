from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Pitch:
    """A musical pitch identified by MIDI number, enharmonic spelling, and octave.

    Example: Pitch(midi=60, spelling="C", octave=4) is middle C.
    """

    midi: int
    spelling: str
    octave: int

    def __post_init__(self) -> None:
        if not (0 <= self.midi <= 127):
            raise ValueError(f"midi must be 0–127, got {self.midi}")

    @property
    def pitch_class(self) -> int:
        """Pitch class 0–11 (C=0, C#/Db=1, …, B=11)."""
        return self.midi % 12

    @property
    def name_without_octave(self) -> str:
        """Spelling without octave number, e.g. 'C#', 'Bb'."""
        return self.spelling
