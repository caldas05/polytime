from __future__ import annotations
from dataclasses import replace

from model.pitch import Pitch
from model.voice import Voice
from model.measure import Measure
from transforms.temporal import retrograde, retrograde_measure
from transforms.melodic import invert_melody


def retrograde_inversion(voice: Voice, axis: Pitch) -> Voice:
    """Apply melodic inversion then retrograde (or vice versa — same result for these ops).

    Example: retrograde_inversion(voice, C4) inverts around C4, then reverses in time.
    """
    return retrograde(invert_melody(voice, axis))


def mirror_measure(source: Measure, axis: Pitch | None = None) -> Measure:
    """Create a new measure that is the melodic and rhythmic mirror of source.

    If axis is None, the axis is the first pitch found in the first voice.
    Raises ValueError if no pitched event is found and axis is None.

    Example: mirror_measure(m) produces a measure with all voices retrogressed and inverted.
    """
    if axis is None:
        axis = _find_first_pitch(source)

    mirrored_voices = tuple(
        retrograde(invert_melody(v, axis)) for v in source.voices
    )
    return replace(source, voices=mirrored_voices)


def _find_first_pitch(measure: Measure) -> Pitch:
    from model.events import Note, Chord
    for voice in measure.voices:
        for event in voice.events:
            if isinstance(event, Note):
                return event.pitch
            if isinstance(event, Chord):
                return event.pitches[0]
    raise ValueError("No pitched event found in measure to use as inversion axis")
