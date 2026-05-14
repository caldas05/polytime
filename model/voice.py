from __future__ import annotations
from dataclasses import dataclass

from model.events import Event


@dataclass(frozen=True)
class Voice:
    """A single linear timeline of non-overlapping events.

    Events must be sorted by offset. Overlaps between voices happen at the Measure level.

    Example: Voice(id="v1", events=(note_on_beat_1, note_on_beat_2))
    """

    id: str
    events: tuple[Event, ...]

    def __post_init__(self) -> None:
        for a, b in zip(self.events, self.events[1:]):
            if a.offset > b.offset:
                raise ValueError(
                    f"Voice events must be ordered by offset; "
                    f"found offset {a.offset} before {b.offset}"
                )
            
    def find_first_pitched_event(self):
        """Find the first Note or Chord (event with pitch) in a voice."""
        for event in self.events:
            if hasattr(event, 'pitch'):  # Note or Chord have pitch
                return event
        return None
