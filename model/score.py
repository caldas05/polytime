from __future__ import annotations
from dataclasses import dataclass

from model.part import Part


@dataclass(frozen=True)
class Score:
    """The top-level container for an entire musical score.

    Example: Score(title="Sonata", parts=(piano_part,), metadata={"composer": "Bach"})
    """

    title: str
    parts: tuple[Part, ...]
    metadata: dict
