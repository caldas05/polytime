from __future__ import annotations
from dataclasses import replace
from fractions import Fraction

from model.pitch import Pitch
from model.events import Note, Rest, Chord, Event
from model.voice import Voice
from teoria.pitch import transpose as pitch_transpose, pitch_from_midi
from teoria.scale import Scale, degree_of, transpose_diatonic


def _map_pitches(event: Event, fn) -> Event:
    if isinstance(event, Rest):
        return event
    if isinstance(event, Note):
        return replace(event, pitch=fn(event.pitch))
    return replace(event, pitches=tuple(fn(p) for p in event.pitches))


def _invert_pitch(pitch: Pitch, axis: Pitch) -> Pitch:
    new_midi = 2 * axis.midi - pitch.midi
    if not (0 <= new_midi <= 127):
        raise ValueError(f"Inverted midi {new_midi} is out of range 0–127")
    return pitch_from_midi(new_midi)


def transpose_voice(voice: Voice, semitones: int) -> Voice:
    """Transpose all pitched events by the given number of semitones.

    Example: transpose_voice(voice, 7) transposes every note up a perfect fifth.
    """
    return Voice(
        id=voice.id,
        events=tuple(_map_pitches(e, lambda p: pitch_transpose(p, semitones)) for e in voice.events),
    )


def invert_melody(voice: Voice, axis: Pitch) -> Voice:
    """Mirror all pitches around the axis pitch (chromatic inversion).

    new_midi = 2 * axis.midi - original_midi.

    Example: invert_melody(voice, C4) maps G4 (midi+7) → F3 (midi-7).
    """
    return Voice(
        id=voice.id,
        events=tuple(_map_pitches(e, lambda p: _invert_pitch(p, axis)) for e in voice.events),
    )


def _invert_diatonic_pitch(pitch: Pitch, axis: Pitch, scale: Scale) -> Pitch:
    axis_deg = degree_of(scale, axis)
    pitch_deg = degree_of(scale, pitch)
    if axis_deg is None or pitch_deg is None:
        raise ValueError(
            f"Both axis ({axis.spelling}) and pitch ({pitch.spelling}) must be in the scale"
        )
    steps = axis_deg - pitch_deg  # mirror: axis + (axis - pitch)
    return transpose_diatonic(scale, axis, steps)


def invert_melody_diatonic(voice: Voice, axis: Pitch, scale: Scale) -> Voice:
    """Mirror all pitches around axis, staying within the given scale.

    Example: in C major with axis=E4, D4 (degree 2, one below axis degree 3)
    becomes F4 (degree 4, one above axis).
    """
    return Voice(
        id=voice.id,
        events=tuple(
            _map_pitches(e, lambda p: _invert_diatonic_pitch(p, axis, scale))
            for e in voice.events
        ),
    )
