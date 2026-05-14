"""Side-by-side transform diff: the headline visualization.

Stacks `before` and `after` voices on a shared time axis with connector
arrows that classify each correspondence:

  - identity (same offset & pitch)            : no connector
  - pitch-shifted (same id, different pitch)  : solid arrow, color = interval
  - time-shifted (same id, different offset)  : dashed horizontal line
  - split (one id → multiple after events)    : bracket spanning descendants
  - new (fresh id in after)                   : red star marker

This is what makes prepend_rest's tie-splitting and invert/transpose's pitch
geometry legible at a glance.
"""
from __future__ import annotations
from collections import defaultdict
from fractions import Fraction

from matplotlib.figure import Figure
import matplotlib.pyplot as plt

from model.events import Note, Chord
from model.voice import Voice
from viz.piano_roll import draw_voice, voice_pitch_range
from viz.trace import TracedVoice, trace, retrace


def _event_pitch(ev) -> int | None:
    if isinstance(ev, Note):
        return ev.pitch.midi
    if isinstance(ev, Chord):
        return ev.pitches[0].midi
    return None


def _event_center(ev) -> tuple[float, int | None]:
    x = float(ev.offset) + float(ev.duration.actual_beats) / 2
    return x, _event_pitch(ev)


def diff(
    before: Voice | TracedVoice,
    after: Voice | TracedVoice | None = None,
    *,
    title: str = "",
    connectors: bool = True,
) -> Figure:
    """Render a transform diff figure.

    `before` may be a Voice or a TracedVoice. If `after` is a plain Voice,
    its ids will be re-derived from `before` via `retrace`. If `after` is
    omitted, only the before-voice is drawn (useful for exploration).
    """
    if isinstance(before, Voice):
        before = trace(before)
    assert isinstance(before, TracedVoice)

    if after is None:
        fig, ax = plt.subplots(figsize=(12, 4))
        draw_voice(before.voice, ax, color="#3a7bd5", label="before")
        lo, hi = voice_pitch_range([before.voice])
        ax.set_ylim(lo, hi)
        ax.set_xlabel("beats")
        if title:
            fig.suptitle(title)
        return fig

    if isinstance(after, Voice):
        after_t = retrace(before, after)
    else:
        after_t = after

    # Scale figure width with content length so notes don't get squashed
    # into vertical hairlines on long pieces. Cap to keep file size sane.
    end_total = max(
        (float(e.offset) + float(e.duration.actual_beats) for e in before.voice.events),
        default=4.0,
    )
    if isinstance(after, TracedVoice):
        end_total = max(
            end_total,
            max(
                (float(e.offset) + float(e.duration.actual_beats) for e in after.voice.events),
                default=4.0,
            ),
        )
    width = min(60.0, max(12.0, end_total / 8.0))  # ~8 beats per inch
    fig, (ax_a, ax_b) = plt.subplots(
        2, 1, figsize=(width, 6), sharex=True,
        gridspec_kw={"hspace": 0.4},
    )
    draw_voice(before.voice, ax_a, color="#3a7bd5", label="before")
    draw_voice(after_t.voice, ax_b, color="#d55e3a", label="after")

    lo, hi = voice_pitch_range([before.voice, after_t.voice])
    ax_a.set_ylim(lo, hi)
    ax_b.set_ylim(lo, hi)
    ax_b.set_xlabel("beats")

    # Pitch range for x-limits
    end_a = max(
        (float(e.offset) + float(e.duration.actual_beats) for e in before.voice.events),
        default=4.0,
    )
    end_b = max(
        (float(e.offset) + float(e.duration.actual_beats) for e in after_t.voice.events),
        default=4.0,
    )
    ax_a.set_xlim(-0.2, max(end_a, end_b) + 0.2)

    if not connectors:
        if title:
            fig.suptitle(title)
        return fig

    # Index after events by id
    after_by_id: dict[int, list[int]] = defaultdict(list)
    for i, eid in enumerate(after_t.ids):
        after_by_id[eid].append(i)

    before_ids_set = set(before.ids)

    for b_idx, eid in enumerate(before.ids):
        descendants = after_by_id.get(eid, [])
        b_ev = before.voice.events[b_idx]
        b_x, b_p = _event_center(b_ev)
        if b_p is None:
            continue

        if not descendants:
            # Event was deleted by the transform
            ax_a.plot([b_x], [b_p], marker="x", color="black", markersize=8)
            continue

        if len(descendants) == 1:
            a_ev = after_t.voice.events[descendants[0]]
            a_x, a_p = _event_center(a_ev)
            if a_p is None:
                continue
            same_offset = a_ev.offset == b_ev.offset
            same_pitch = a_p == b_p
            if same_offset and same_pitch:
                continue  # identity — no connector
            elif same_pitch and not same_offset:
                # time shift: dashed
                _draw_connector(fig, ax_a, ax_b, b_x, b_p, a_x, a_p,
                                style="dashed", color="#666666")
            elif same_offset and not same_pitch:
                # pitch shift: solid, colored by interval
                interval = a_p - b_p
                color = _interval_color(interval)
                _draw_connector(fig, ax_a, ax_b, b_x, b_p, a_x, a_p,
                                style="solid", color=color)
            else:
                # both changed
                _draw_connector(fig, ax_a, ax_b, b_x, b_p, a_x, a_p,
                                style="solid", color="#9933cc")
        else:
            # Split: one before → many after. Bracket the descendants and
            # draw a single arrow tail at the before event.
            xs = []
            for d in descendants:
                a_ev = after_t.voice.events[d]
                ax_, ap_ = _event_center(a_ev)
                if ap_ is None:
                    continue
                xs.append(ax_)
                _draw_connector(fig, ax_a, ax_b, b_x, b_p, ax_, ap_,
                                style="dotted", color="#cc6633", alpha=0.5)
            if xs:
                # Bracket on the after axis
                y_bracket = ax_b.get_ylim()[0] + 0.5
                ax_b.annotate(
                    "", xy=(max(xs), y_bracket), xytext=(min(xs), y_bracket),
                    arrowprops=dict(arrowstyle="<->", color="#cc6633", lw=1.5),
                )

    # Mark new events (id not in before)
    for a_idx, eid in enumerate(after_t.ids):
        if eid not in before_ids_set:
            a_ev = after_t.voice.events[a_idx]
            a_x, a_p = _event_center(a_ev)
            if a_p is None:
                continue
            ax_b.plot([a_x], [a_p], marker="*", color="red", markersize=10)

    if title:
        fig.suptitle(title)

    return fig


def _draw_connector(fig, ax_top, ax_bot, x0, y0, x1, y1, *, style, color, alpha=0.7):
    """Connector line from (x0,y0) on ax_top to (x1,y1) on ax_bot."""
    from matplotlib.patches import ConnectionPatch
    cp = ConnectionPatch(
        xyA=(x0, y0), coordsA=ax_top.transData,
        xyB=(x1, y1), coordsB=ax_bot.transData,
        arrowstyle="->", linestyle=style, color=color,
        alpha=alpha, lw=1.2,
    )
    fig.add_artist(cp)


def _interval_color(semitones: int) -> str:
    """Color-code by interval magnitude. Up = warm, down = cool."""
    if semitones == 0:
        return "#888888"
    mag = min(abs(semitones), 12)
    if semitones > 0:
        # Warm scale: yellow → red
        t = mag / 12
        return f"#{int(255):02x}{int(200 - 150 * t):02x}{int(50 - 50 * t):02x}"
    else:
        t = mag / 12
        return f"#{int(50 - 50 * t):02x}{int(150 - 100 * t):02x}{int(255):02x}"
