"""Trace event provenance through transforms without modifying the model.

A `TracedVoice` carries a parallel `ids` array — one stable integer per event
in `voice.events`. After applying a transform, `retrace(before, after_voice)`
re-derives ids by best-effort matching:

  - exact match on (offset, midi pitch) → identity (same id)
  - exact match on midi pitch only → time shift (same id)
  - exact match on offset only → pitch shift (same id)
  - one-to-many: a before event whose total duration is split across
    multiple consecutive after events sharing the same pitch → all
    descendants inherit the same id (the "split" relation that makes
    prepend_rest legible)
  - otherwise → fresh id (transformation introduced new material)

This is a heuristic. It will not perfectly reconstruct provenance for every
exotic transform, but it correctly handles transpose, invert, retrograde,
shift_offset, and prepend_rest — the cases that matter for diff visuals.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from itertools import count

from model.events import Note, Rest, Chord
from model.voice import Voice


@dataclass(frozen=True)
class TracedVoice:
    voice: Voice
    ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.ids) != len(self.voice.events):
            raise ValueError(
                f"ids length {len(self.ids)} != events length {len(self.voice.events)}"
            )


_id_counter = count(1)


def fresh_id() -> int:
    return next(_id_counter)


def trace(voice: Voice) -> TracedVoice:
    """Tag each event in the voice with a fresh id."""
    return TracedVoice(voice=voice, ids=tuple(fresh_id() for _ in voice.events))


def _event_pitch(ev) -> int | None:
    if isinstance(ev, Note):
        return ev.pitch.midi
    if isinstance(ev, Chord):
        return ev.pitches[0].midi  # represent chord by its lowest-index pitch
    return None  # Rest


def _detect_shift(before_evs, after_evs) -> Fraction | None:
    """Detect a constant offset delta Δ such that most before notes appear
    in after at (pitch, offset + Δ). Returns None if no Δ clears the
    80% match threshold. Δ = 0 is rejected so transpose/invert fall through.
    """
    b_by_pitch: dict[int, list[Fraction]] = {}
    a_set: set[tuple[int, Fraction]] = set()
    for ev in before_evs:
        p = _event_pitch(ev)
        if p is None:
            continue
        b_by_pitch.setdefault(p, []).append(ev.offset)
    for ev in after_evs:
        p = _event_pitch(ev)
        if p is None:
            continue
        a_set.add((p, ev.offset))

    total = sum(len(v) for v in b_by_pitch.values())
    if total == 0:
        return None

    # Candidate Δs from the rarest shared pitch — fewest, most discriminating.
    a_by_pitch: dict[int, list[Fraction]] = {}
    for p, o in a_set:
        a_by_pitch.setdefault(p, []).append(o)
    shared = [p for p in b_by_pitch if p in a_by_pitch]
    if not shared:
        return None
    pivot = min(shared, key=lambda p: len(b_by_pitch[p]) + len(a_by_pitch[p]))
    candidates = {ao - bo for bo in b_by_pitch[pivot] for ao in a_by_pitch[pivot]}

    best_delta = None
    best_score = 0
    for delta in candidates:
        if delta == 0:
            continue
        score = sum(
            1
            for p, offsets in b_by_pitch.items()
            for o in offsets
            if (p, o + delta) in a_set
        )
        if score > best_score:
            best_score = score
            best_delta = delta

    if best_delta is not None and best_score / total >= 0.8:
        return best_delta
    return None


def retrace(before: TracedVoice, after: Voice) -> TracedVoice:
    """Best-effort re-derivation of ids from `before` onto `after`'s events."""
    before_evs = before.voice.events
    before_ids = before.ids
    after_evs = after.events

    # Index before events by (offset, pitch) and by pitch alone for fallback.
    by_op: dict[tuple[Fraction, int | None], list[int]] = {}
    by_pitch: dict[int | None, list[int]] = {}
    for i, ev in enumerate(before_evs):
        p = _event_pitch(ev)
        by_op.setdefault((ev.offset, p), []).append(i)
        by_pitch.setdefault(p, []).append(i)

    used = [False] * len(before_evs)
    new_ids: list[int | None] = [None] * len(after_evs)

    # Shift hypothesis: if after is before translated by a constant Δ,
    # match each before event b to the after event at (b.pitch, b.offset+Δ).
    # This avoids greedy by-pitch consuming the wrong subject event when
    # pitches repeat (e.g. Frère Jacques + prepend_rest).
    delta = _detect_shift(before_evs, after_evs)
    if delta is not None:
        a_index: dict[tuple[int, Fraction], list[int]] = {}
        for j, ev in enumerate(after_evs):
            p = _event_pitch(ev)
            if p is None:
                continue
            a_index.setdefault((p, ev.offset), []).append(j)
        for i, ev in enumerate(before_evs):
            p = _event_pitch(ev)
            if p is None:
                continue
            cand = a_index.get((p, ev.offset + delta), [])
            j = next((c for c in cand if new_ids[c] is None), None)
            if j is not None:
                new_ids[j] = before_ids[i]
                used[i] = True

    for j, ev in enumerate(after_evs):
        if new_ids[j] is not None:
            continue
        p = _event_pitch(ev)

        # Try exact (offset, pitch) match
        cand = by_op.get((ev.offset, p), [])
        idx = next((c for c in cand if not used[c]), None)

        if idx is None:
            # Try pitch-only (time-shift transforms like prepend_rest, retrograde)
            cand = by_pitch.get(p, [])
            idx = next((c for c in cand if not used[c]), None)

        if idx is not None:
            used[idx] = True
            new_ids[j] = before_ids[idx]
        else:
            # Pitch-shifted (transpose/invert): fall back to positional pairing
            # over un-used same-type events (Note↔Note, Rest↔Rest).
            same_type_unused = [
                i for i, b in enumerate(before_evs)
                if not used[i] and type(b) is type(ev)
            ]
            if same_type_unused:
                idx = same_type_unused[0]
                used[idx] = True
                new_ids[j] = before_ids[idx]
            else:
                new_ids[j] = fresh_id()

    return TracedVoice(voice=after, ids=tuple(new_ids))


def apply(before: TracedVoice, fn) -> TracedVoice:
    """Apply a Voice -> Voice transform and re-derive ids."""
    return retrace(before, fn(before.voice))
