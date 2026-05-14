"""Piano-roll renderer for a single Voice.

Time axis = beats (Fraction(1) == quarter note). Pitch axis = MIDI number.
Rests render as low-opacity grey bars on a fixed lane below the lowest note.
"""
from __future__ import annotations
from fractions import Fraction
from typing import Iterable

from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

from model.events import Note, Rest, Chord
from model.voice import Voice


def _pitches_in_voice(voice: Voice) -> list[int]:
    pitches: list[int] = []
    for ev in voice.events:
        if isinstance(ev, Note):
            pitches.append(ev.pitch.midi)
        elif isinstance(ev, Chord):
            pitches.extend(p.midi for p in ev.pitches)
    return pitches


def voice_pitch_range(voices: Iterable[Voice]) -> tuple[int, int]:
    """Pitch range across multiple voices, padded by 2 semitones."""
    all_p: list[int] = []
    for v in voices:
        all_p.extend(_pitches_in_voice(v))
    if not all_p:
        return (60, 72)
    return (min(all_p) - 2, max(all_p) + 2)


def draw_voice(
    voice: Voice,
    ax: Axes,
    *,
    color: str = "#3a7bd5",
    alpha: float = 0.85,
    label: str | None = None,
    rest_lane: int | None = None,
) -> None:
    """Draw a Voice as piano-roll rectangles on the given Axes.

    Offset semantics: events use offset *within their measure*. This function
    treats `voice` as already flat — the caller is responsible for re-offsetting
    if rendering a multi-measure Part. For multi-measure use, build a synthetic
    Voice with absolute offsets, or call this once per measure with an x-shift.
    """
    if rest_lane is None:
        pitches = _pitches_in_voice(voice)
        rest_lane = (min(pitches) - 2) if pitches else 58

    for ev in voice.events:
        x = float(ev.offset)
        w = float(ev.duration.actual_beats)
        if isinstance(ev, Note):
            _add_rect(ax, x, ev.pitch.midi, w, color=color, alpha=alpha)
        elif isinstance(ev, Chord):
            for p in ev.pitches:
                _add_rect(ax, x, p.midi, w, color=color, alpha=alpha)
        elif isinstance(ev, Rest):
            _add_rect(ax, x, rest_lane, w, color="#999999", alpha=0.3)

    if label is not None:
        ax.set_ylabel(label)


def _add_rect(ax: Axes, x: float, midi: int, w: float, *, color: str, alpha: float) -> None:
    # No edge: at long pieces the rectangles become a few pixels wide and the
    # edge alone turns every note into a fat vertical bar. Use a slightly
    # darker face for separation between adjacent notes instead.
    rect = Rectangle(
        (x, midi - 0.4),
        w,
        0.8,
        facecolor=color,
        edgecolor="none",
        alpha=alpha,
    )
    ax.add_patch(rect)
