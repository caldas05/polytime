from __future__ import annotations
from dataclasses import replace
from typing import Callable

from model.voice import Voice
from model.measure import Measure
from model.part import Part
from model.score import Score


def compose(*transforms: Callable) -> Callable:
    """Compose transforms right-to-left: compose(f, g)(x) == f(g(x)).

    The rightmost transform runs first, then each one to its left in turn.

    Example: compose(retrograde, transpose_voice_up5)(voice)
             first transposes (rightmost), then retrogrades.
    """
    def composed(x):
        result = x
        for transform in reversed(transforms):
            result = transform(result)
        return result
    return composed


def apply_to_voice(measure: Measure, voice_id: str, transform: Callable[[Voice], Voice]) -> Measure:
    """Apply transform to the voice with the given id, returning a new Measure.

    Example: apply_to_voice(m, "v1", retrograde) retrogrades voice "v1" only.
    Raises ValueError if voice_id is not found.
    """
    found = False
    new_voices = []
    for v in measure.voices:
        if v.id == voice_id:
            new_voices.append(transform(v))
            found = True
        else:
            new_voices.append(v)
    if not found:
        raise ValueError(f"Voice '{voice_id}' not found in measure {measure.number}")
    return replace(measure, voices=tuple(new_voices))


def apply_to_measure(part: Part, measure_number: int, transform: Callable[[Measure], Measure]) -> Part:
    """Apply transform to the measure with the given number, returning a new Part.

    Example: apply_to_measure(part, 2, retrograde_measure) retrogrades measure 2.
    Raises ValueError if measure_number is not found.
    """
    found = False
    new_measures = []
    for m in part.measures:
        if m.number == measure_number:
            new_measures.append(transform(m))
            found = True
        else:
            new_measures.append(m)
    if not found:
        raise ValueError(f"Measure number {measure_number} not found in part '{part.name}'")
    return replace(part, measures=tuple(new_measures))


def apply_to_all_measures(part: Part, transform: Callable[[Measure], Measure]) -> Part:
    """Apply transform to every measure in the part.

    Example: apply_to_all_measures(part, retrograde_measure) retrogrades all measures.
    """
    return replace(part, measures=tuple(transform(m) for m in part.measures))


def apply_to_part(score: Score, part_name: str, transform: Callable[[Part], Part]) -> Score:
    """Apply transform to the part with the given name, returning a new Score.

    Example: apply_to_part(score, "Violin", apply_to_all_measures(...)).
    Raises ValueError if part_name is not found.
    """
    found = False
    new_parts = []
    for p in score.parts:
        if p.name == part_name:
            new_parts.append(transform(p))
            found = True
        else:
            new_parts.append(p)
    if not found:
        raise ValueError(f"Part '{part_name}' not found in score")
    return replace(score, parts=tuple(new_parts))
