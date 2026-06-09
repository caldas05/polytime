from __future__ import annotations
from dataclasses import dataclass

from model.measure import Measure


@dataclass(frozen=True)
class Part:
    """A single instrumental part. May be a single staff (default) or a multi-staff
    part such as a piano grand staff.

    `clef` is the clef for staff 1. For multi-staff parts (piano, organ, harp),
    `extra_staff_clefs` lists clefs for staves 2..N. Events tagged with `staff=N`
    will be rendered on the corresponding staff.

    Example: Part(name="Piano", instrument="piano", clef="treble",
                  extra_staff_clefs=("bass",), measures=(m1, m2))
    """

    name: str
    instrument: str | None
    clef: str  # clef name: "treble", "bass", "alto", etc.
    measures: tuple[Measure, ...]
    extra_staff_clefs: tuple[str, ...] = ()

    @property
    def staff_count(self) -> int:
        return 1 + len(self.extra_staff_clefs)

    def staff_clef(self, staff: int) -> str:
        if staff == 1:
            return self.clef
        return self.extra_staff_clefs[staff - 2]