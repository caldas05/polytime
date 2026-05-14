from __future__ import annotations
from dataclasses import replace
from fractions import Fraction

from model.duration import Duration
from model.events import Event, Note, Rest, Chord
from model.voice import Voice
from model.measure import Measure
from model.part import Part


def _scale_event(event: Event, factor: Fraction, offset_delta: Fraction = Fraction(0)) -> Event:
    new_dur = replace(event.duration, value=event.duration.value * factor)
    return replace(event, duration=new_dur, offset=event.offset * factor + offset_delta)


def _shift_event(event: Event, delta: Fraction) -> Event:
    return replace(event, offset=event.offset + delta)


def retrograde(voice: Voice) -> Voice:
    """Reverse the order of events in time, recomputing offsets.

    The retrograde places the last event first. Offsets are recalculated so that
    the total duration is preserved.

    Example: [C4 q@0, D4 q@1, E4 q@2] → [E4 q@0, D4 q@1, C4 q@2].
    """
    if not voice.events:
        return voice
    total = sum((e.duration.actual_beats for e in voice.events), Fraction(0))
    reversed_events = voice.events[::-1]
    result: list[Event] = []
    offset = Fraction(0)
    for event in reversed_events:
        result.append(_shift_event(event, offset - event.offset))
        offset += event.duration.actual_beats
    return Voice(id=voice.id, events=tuple(result))


def retrograde_measure(measure: Measure) -> Measure:
    """Apply retrograde to all voices in a measure.

    Example: retrograde_measure(m) reverses each voice independently.
    """
    return replace(measure, voices=tuple(retrograde(v) for v in measure.voices))


def scale_rhythm(voice: Voice, factor: Fraction) -> Voice:
    """Scale all durations and offsets by factor (augmentation or diminution).

    Example: scale_rhythm(voice, Fraction(2)) doubles all durations (augmentation).
    Example: scale_rhythm(voice, Fraction(1, 2)) halves all durations (diminution).
    """
    scaled = tuple(_scale_event(e, factor) for e in voice.events)
    return Voice(id=voice.id, events=scaled)


def echo(voice: Voice, start_at: Fraction, scale: Fraction = Fraction(1)) -> Voice:
    """Append a rhythm-scaled copy of `voice` to itself, starting at beat
    `start_at` (absolute, measured from the original voice's offset 0).

    `scale` is the augmentation factor applied to the echo: 1 = same speed,
    3/2 = 1.5× slower, 2 = twice as slow, 2/3 = 1.5× faster. The original
    events keep their offsets; echo events are scaled then shifted so the
    first echo event lands exactly at `start_at`.

    Example: echo(theme, Fraction(8), Fraction(3, 2)) — the theme plays
    normally, then at beat 8 a 1.5× slower copy enters in the same voice.
    """
    echo_events = tuple(
        _scale_event(e, scale, offset_delta=start_at) for e in voice.events
    )
    merged = sorted(voice.events + echo_events, key=lambda e: e.offset)
    return Voice(id=voice.id, events=tuple(merged))


def shift_offset(voice: Voice, delta: Fraction) -> Voice:
    """Shift all events by delta beats (can be negative).

    Example: shift_offset(voice, Fraction(1)) moves all events one beat later.

    Note: this only mutates `event.offset` metadata. Sequential serializers
    (LilyPond) ignore offsets, so a per-measure shift_offset is invisible
    there. For a real delay that re-bins events across measures, use
    `prepend_rest`.
    """
    shifted = tuple(_shift_event(e, delta) for e in voice.events)
    return Voice(id=voice.id, events=shifted)


# ── prepend_rest: a real part-level delay ────────────────────────────────────


_DURATION_CANDIDATES: list[tuple[Fraction, Duration]] | None = None


def _duration_candidates() -> list[tuple[Fraction, Duration]]:
    """All (actual_beats, Duration) candidates ordered largest first."""
    global _DURATION_CANDIDATES
    if _DURATION_CANDIDATES is not None:
        return _DURATION_CANDIDATES
    out: list[tuple[Fraction, Duration]] = []
    for k in range(-6, 5):  # 1/64 quarter to 16 quarters
        base = Fraction(2) ** k
        for dots in range(3):
            d = Duration(value=base, dots=dots)
            out.append((d.actual_beats, d))
    out.sort(key=lambda x: x[0], reverse=True)
    _DURATION_CANDIDATES = out
    return out


def _decompose_beats(beats: Fraction) -> list[Duration]:
    """Express `beats` as a list of standard Durations (to be tied together).

    Greedy: pick the largest dyadic Duration <= remaining, subtract, repeat.
    For non-dyadic residues (triplets, quintuplets — anything 1/3, 1/6, 2/3,
    etc.) falls back to a single Duration with the raw value. MIDI handles
    these fine; LilyPond/notational output may not render them correctly.
    """
    if beats == 0:
        return []
    if beats < 0:
        raise ValueError(f"Cannot decompose negative beats: {beats}")

    # If the denominator isn't a power of two, this is a tuplet duration that
    # cannot be expressed as dotted dyadic notes. Emit it raw — MIDI handles
    # arbitrary durations; only notational output cares.
    denom = beats.denominator
    if denom & (denom - 1) != 0:
        return [Duration(value=beats)]

    candidates = _duration_candidates()
    out: list[Duration] = []
    remaining = beats
    while remaining > 0:
        for ab, d in candidates:
            if ab <= remaining:
                out.append(d)
                remaining -= ab
                break
        else:
            out.append(Duration(value=remaining))
            remaining = Fraction(0)
    return out


def _measure_index(abs_off: Fraction, starts: list[Fraction], caps: list[Fraction]) -> int:
    """Index of the measure containing abs_off; the right edge belongs to the next measure."""
    for i, c in enumerate(caps):
        if starts[i] <= abs_off < starts[i] + c:
            return i
    return len(caps) - 1


def _retie(orig_tie: str | None, n_pieces: int, idx: int) -> str | None:
    if n_pieces == 1:
        return orig_tie
    has_in = orig_tie in ("stop", "continue")
    has_out = orig_tie in ("start", "continue")
    incoming = has_in if idx == 0 else True
    outgoing = has_out if idx == n_pieces - 1 else True
    if incoming and outgoing:
        return "continue"
    if outgoing:
        return "start"
    if incoming:
        return "stop"
    return None


def _split_event(
    event: Event,
    abs_start: Fraction,
    starts: list[Fraction],
    caps: list[Fraction],
) -> list[tuple[int, Event]]:
    """Split an event across barlines, decomposing each segment into representable
    Durations. Returns (measure_index, event_with_local_offset_and_tie) tuples."""
    if getattr(event, "is_grace", False):
        mi = _measure_index(abs_start, starts, caps)
        return [(mi, replace(event, offset=abs_start - starts[mi]))]

    remaining = event.duration.actual_beats
    # If the event fits inside its starting measure, keep it whole — don't
    # round-trip through _decompose_beats, which can split an irregular
    # duration (e.g. 15/4) into multiple tied pieces and inflate the event
    # count vs the source.
    start_mi = _measure_index(abs_start, starts, caps)
    start_local = abs_start - starts[start_mi]
    if remaining <= caps[start_mi] - start_local:
        return [(start_mi, replace(event, offset=start_local))]

    cur_abs = abs_start
    raw: list[tuple[int, Fraction, Duration]] = []
    while remaining > 0:
        mi = _measure_index(cur_abs, starts, caps)
        local = cur_abs - starts[mi]
        space = caps[mi] - local
        chunk = min(remaining, space)
        for d in _decompose_beats(chunk):
            raw.append((mi, local, d))
            local += d.actual_beats
        cur_abs += chunk
        remaining -= chunk

    n = len(raw)
    if n == 0:
        return []

    is_pitched = isinstance(event, (Note, Chord))
    orig_tie = getattr(event, "tie", None) if is_pitched else None
    orig_slur = getattr(event, "slur", None) if is_pitched else None

    out: list[tuple[int, Event]] = []
    for i, (mi, local, dur) in enumerate(raw):
        new_event = replace(event, duration=dur, offset=local)
        if is_pitched:
            new_tie = _retie(orig_tie, n, i)
            if n == 1:
                new_slur = orig_slur
            elif i == 0:
                new_slur = orig_slur if orig_slur == "start" else None
            elif i == n - 1:
                new_slur = orig_slur if orig_slur == "stop" else None
            else:
                new_slur = None
            updates: dict = {"tie": new_tie, "slur": new_slur}
            if i > 0:
                updates["dynamic"] = None
                updates["articulations"] = ()
            new_event = replace(new_event, **updates)
        out.append((mi, new_event))
    return out


def prepend_rest(part: Part, delay: Fraction) -> Part:
    """Push every voice in `part` forward by `delay` beats.

    Inserts a leading rest of `delay` beats at the start of each voice,
    re-bins all events into measures (splitting events that straddle barlines
    with tied pieces), and appends new tail measures so spillover material is
    preserved. Tail measures inherit the last measure's time/key signature.

    Example: prepend_rest(comes, Fraction(2)) — delay the comes voice by
    two beats for a canon at the second.
    """
    if delay <= 0 or not part.measures:
        return part

    voice_ids: list[str] = []
    for m in part.measures:
        for v in m.voices:
            if v.id not in voice_ids:
                voice_ids.append(v.id)

    caps = [m.time_signature.beats_per_measure for m in part.measures]
    starts: list[Fraction] = [Fraction(0)]
    for c in caps:
        starts.append(starts[-1] + c)

    streams: dict[str, list[tuple[Fraction, Event]]] = {vid: [] for vid in voice_ids}
    for i, m in enumerate(part.measures):
        for v in m.voices:
            for e in v.events:
                streams[v.id].append((starts[i] + e.offset + delay, e))

    leading_rest = Rest(duration=Duration(value=delay), offset=Fraction(0))
    for vid in voice_ids:
        streams[vid].insert(0, (Fraction(0), leading_rest))

    max_end = starts[-1]
    for stream in streams.values():
        for abs_off, e in stream:
            if getattr(e, "is_grace", False):
                continue
            end = abs_off + e.duration.actual_beats
            if end > max_end:
                max_end = end

    last_m = part.measures[-1]
    cap_tail = last_m.time_signature.beats_per_measure
    while starts[-1] < max_end:
        caps.append(cap_tail)
        starts.append(starts[-1] + cap_tail)

    n_measures = len(caps)
    by_measure: list[dict[str, list[Event]]] = [
        {vid: [] for vid in voice_ids} for _ in range(n_measures)
    ]
    for vid, stream in streams.items():
        for abs_off, e in stream:
            for mi, ne in _split_event(e, abs_off, starts, caps):
                by_measure[mi][vid].append(ne)

    new_measures: list[Measure] = []
    for i in range(n_measures):
        if i < len(part.measures):
            base = part.measures[i]
        else:
            tail_idx = i - len(part.measures)
            base = Measure(
                number=last_m.number + tail_idx + 1,
                time_signature=last_m.time_signature,
                voices=(),
                key_signature=last_m.key_signature,
            )
        new_voices = tuple(
            Voice(id=vid, events=tuple(sorted(by_measure[i][vid], key=lambda e: e.offset)))
            for vid in voice_ids
            if by_measure[i][vid]
        )
        new_measures.append(replace(base, voices=new_voices))

    return replace(part, measures=tuple(new_measures))
