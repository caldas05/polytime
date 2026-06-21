"""Constructive inversion of polytemporal coincidence structures.

The forward polyrhythm question is "given constant tempi, when do their pulses
coincide?" This module solves the inverse: the composer declares where the lines
must coincide (a set of beat times T = {T_1, ..., T_m}), and we return a small
set of constant-tempo lines whose pulses, together, land on every prescribed
point.

The method is a subharmonic cover. First normalize T to a lowest-terms integer
set K on a base grid r (see normalize). A subharmonic tempo r/a then pulses on
T_j exactly when a divides n_j, so covering the targets reduces to a set-cover
over the divisors of the K values. Where the pure subharmonics can't supply
enough independent voices, the cover reaches for rational harmonics h·r/a.

The reason for rational harmonics rather than just more subharmonics: r/a pulses
at 0, a, 2a, ..., a subset of r/b's pulses whenever b divides a. A voice in that
relation is masked — it only ever sounds on top of the coarser voice, so it adds
no audible second stream at a coincidence. The cover avoids that: where r/4 would
be masked by r/2 it uses 3·r/4, and an isolated point that needs two voices gets
two independent harmonics (2·r/5 + 3·r/5) instead of r/5 + 2·r/5. Masking is
judged only between generated voices, never against the base grid r — every
subharmonic is a subset of r, which is just what makes it a subharmonic.

Pure stdlib, Fraction-native — no model imports.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from math import gcd, lcm
from typing import Iterable


def _as_fraction(value) -> Fraction:
    """Coerce int / Fraction / numeric-string / float to an exact Fraction.

    Floats are snapped via limit_denominator so "0.4" entered in the UI
    becomes 2/5, not the binary-rounded 3602879701896397/9007199254740992."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        return Fraction(value.strip())
    return Fraction(value).limit_denominator(1_000_000)


def normalize(times: Iterable) -> tuple[Fraction, list[int]]:
    """Map the target times T onto a sorted, lowest-terms integer set K.

    Returns (S, K) with each target landing at beat K_j / S exactly. K is reduced
    so its gcd is 1, which makes the inversion depend only on the ratios of the
    targets, not their absolute size: the same points given in beats or in bars (a
    uniform ×beats_per_bar) yield the same K and the same cover, and only S moves
    to absorb the scale. S is therefore rational, not integer — T in bars gives
    S = lcm/gcd.

    A 0 among the targets survives reduction (gcd(0, ...) is the gcd of the rest),
    so a composer can state "align on the downbeat too" explicitly. The cover
    works on the positive targets only; the 0 adds no further constraint, since
    voices entered on the downbeat already coincide there. Negatives are an error.
    """
    ts: list[Fraction] = []
    for t in times:
        f = _as_fraction(t)
        if f < 0:
            raise ValueError(f"coincidence times must be >= 0: {f}")
        ts.append(f)
    if not ts:
        raise ValueError("need at least one coincidence point")
    if not any(f > 0 for f in ts):
        raise ValueError("need at least one positive coincidence point — beat 0 alone is degenerate")
    D = 1
    for f in ts:
        D = lcm(D, f.denominator)
    K_raw = sorted({D * f.numerator // f.denominator for f in ts})
    g = gcd(*K_raw) or 1  # gcd(0) == 0; guard the (already-rejected) all-zero case
    S = Fraction(D, g)
    K = [k // g for k in K_raw]
    return S, K


@dataclass(frozen=True)
class Tempo:
    """A tempo h·r/a relative to the base tempo r (from normalize).

    Hits target T_j = n_j / r exactly when a divides h·n_j. a = 1 is the base
    tempo's harmonic family (hits every target trivially); h = 1 is a pure
    subharmonic; a general (h, a) is a rational harmonic of a subharmonic.
    """

    h: int
    a: int

    def hits(self, n: int) -> bool:
        return (self.h * n) % self.a == 0

    @property
    def ratio(self) -> Fraction:
        return Fraction(self.h, self.a)

    @property
    def period(self) -> Fraction:
        """Pulse spacing in K base-grid units (= a / h). Beats = period / S."""
        return Fraction(self.a, self.h)


_H_MAX = 256  # safety cap on the harmonic numerator; in practice h stays small.


def _masked_by(period: Fraction, others: Iterable[Fraction]) -> bool:
    """True if a pulse train at `period` is a subset of one already placed.

    A is a subset of B exactly when A's spacing is an integer multiple of B's:
    every A-pulse lands on a B-pulse, so A never sounds on its own and is masked.
    The reverse (A's spacing a divisor of B's) is fine — there A is the richer
    voice, not the masked one.
    """
    return any((period / p).denominator == 1 for p in others)


def subharmonic_cover(
    times: Iterable, *, pair_with_base: bool = True
) -> tuple[Fraction, list[int], list[Tempo]]:
    """Invert a set of coincidence points into a covering set of tempi.

    Returns (S, K, tempi). With pair_with_base=True (default) the base tempo r
    counts as an always-present voice, so each target needs only one selected
    tempo to be paired. With False each target must be hit by two selected tempi,
    which forces rational harmonics wherever a target has too few distinct
    divisors to supply two independent voices on its own.

    The cover is built in two phases. Phase A is a greedy set-cover over the
    divisor classes — pick the class covering the most still-uncovered targets,
    ties going to the smaller (simpler) divisor — and records how many voices each
    class must contribute. Phase B (_materialize) turns those counts into concrete
    tempi with no voice masked by another.
    """
    S, K = normalize(times)
    K_pos = sorted({n for n in K if n > 0})
    if not K_pos:
        raise ValueError("subharmonic_cover needs at least one positive target")

    target = 1 if pair_with_base else 2

    # Phase A: decide how many voices each divisor class contributes. A class a
    # (a proper divisor of some target) pulses on exactly the targets it divides.
    # The base-harmonic class a = 1 (voices h·r, h >= 2) hits every target and is
    # the only thing that can pair a target sitting on the grid unit itself
    # (n == 1). Raise the per-class counts greedily until every target is covered.
    coverage = {n: 0 for n in K_pos}
    counts: dict[int, int] = {}          # class a -> number of voices
    chosen: list[int] = []               # proper-divisor classes, in pick order
    candidates = sorted({a for n in K_pos
                         for a in range(2, n + 1) if n % a == 0})

    # Pass 1: each class used at most once, greedy largest-new-coverage first.
    while any(c < target for c in coverage.values()):
        best_a, best_score = None, 0
        for a in candidates:
            if a in chosen:
                continue
            score = sum(1 for n in K_pos
                        if coverage[n] < target and (n % a) == 0)
            if score > best_score:
                best_score, best_a = score, a
        if best_a is None:
            break
        chosen.append(best_a)
        counts[best_a] = 1
        for n in K_pos:
            if n % best_a == 0:
                coverage[n] += 1

    # Pass 2: a still-short point gets an extra voice from a class already
    # covering it; a point with no proper divisor (n == 1) falls back to the
    # base-harmonic class a = 1. Each added voice strictly raises coverage[n],
    # so the loop terminates.
    for n in K_pos:
        while coverage[n] < target:
            base_a = next((a for a in chosen if n % a == 0), 1)
            counts[base_a] = counts.get(base_a, 0) + 1
            for m in K_pos:
                if m % base_a == 0:
                    coverage[m] += 1

    return S, K_pos, _materialize(counts)


def _materialize(counts: dict[int, int]) -> list[Tempo]:
    """Phase B: turn per-class voice counts into concrete, unmasked tempi.

    For each class a it emits counts[a] voices k·r/a (k coprime to a), chosen so
    that no voice's pulses are a subset of another's. Two rules do the work.
    Within a class the numerators k are pairwise non-dividing, so the voices that
    serve an isolated point — one only this class can reach — stay mutually
    independent: 2·r/5 + 3·r/5, never r/5 + 2·r/5 (r/5 sits inside 2·r/5). That
    means a class contributing two or more voices can't use k = 1, since 1 divides
    every k. Across classes a candidate is dropped if its pulses are a subset of a
    voice already placed — r/4 falls inside r/2 once r/2 is in, so 3·r/4 is used.

    Single-voice classes go first so they keep the simplest subharmonic r/a, and
    the base-harmonic class a = 1 goes last.
    """
    tempi: list[Tempo] = []
    periods: list[Fraction] = []         # pulse spacing of every placed voice
    ratios: set[Fraction] = set()
    order = sorted(counts, key=lambda a: (counts[a] >= 2, a == 1, a))
    for a in order:
        used_k: list[int] = []           # numerators already chosen for this class
        placed = 0
        k = 1 if counts[a] == 1 else 2   # two-plus voices can't use the masking k=1
        while placed < counts[a] and k < _H_MAX:
            ratio, period = Fraction(k, a), Fraction(a, k)
            within_ok = all(k % j and j % k for j in used_k)  # neither divides

            if (gcd(k, a) == 1 and ratio != 1 and ratio not in ratios
                    and within_ok and not _masked_by(period, periods)):
                tempi.append(Tempo(k, a))
                periods.append(period)
                ratios.add(ratio)
                used_k.append(k)
                placed += 1
            k += 1
    tempi.sort(key=lambda t: (t.a, t.h))
    return tempi


def subharmonic_cover_report(
    times: Iterable, *, pair_with_base: bool = True
) -> dict:
    """JSON-ready summary of `subharmonic_cover`.

    Each tempo is reported with its (h, a), the ratio h/a relative to r, the
    period in beats (a / (h · S)), and which T_j it hits.
    """
    S, K, tempi = subharmonic_cover(times, pair_with_base=pair_with_base)
    items = []
    for t in tempi:
        period_beats = Fraction(t.a, t.h * S)
        items.append({
            "h": t.h,
            "a": t.a,
            "ratio_str": str(t.ratio),
            "period_beats": float(period_beats),
            "period_str": str(period_beats),
            "hits_K": [n for n in K if t.hits(n)],
            "hits_beats": [float(Fraction(n, S)) for n in K if t.hits(n)],
        })
    return {
        "scale": float(S),
        "scale_num": S.numerator,
        "scale_den": S.denominator,
        "K": K,
        "K_beats": [float(Fraction(n, S)) for n in K],
        "pair_with_base": pair_with_base,
        "tempi": items,
        "num_tempi": len(items),
    }
