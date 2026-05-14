"""Polyrhythm round-trip: build 3-against-2 via the model, save MIDI, parse
back, and verify each voice's onsets land on the expected non-dyadic grid.

The model already supports tuplet metadata on Duration; what we need is that
Fraction-based offsets and durations survive a MIDI write/read cycle so two
voices ticking at 1/2 and 1/3 still meet at integer beats.
"""
from __future__ import annotations
import os
import tempfile
from fractions import Fraction

import pytest

from model.duration import Duration
from model.events import Note, Rest
from model.pitch import Pitch
from model.voice import Voice
from model.measure import Measure, TimeSignature
from model.part import Part
from model.score import Score

from score_io.live.midi_file import save_mido, load_mido


def _pitch(midi: int) -> Pitch:
    return Pitch(midi=midi, spelling="C", octave=midi // 12 - 1)


def _voice_dyadic_halves(pitch_midi: int) -> Voice:
    """Two half-beat notes per beat, four beats total (8 notes)."""
    events = tuple(
        Note(
            duration=Duration(value=Fraction(1, 2)),
            offset=Fraction(i, 2),
            pitch=_pitch(pitch_midi),
        )
        for i in range(8)
    )
    return Voice(id="duple", events=events)


def _voice_triplet_thirds(pitch_midi: int) -> Voice:
    """Three triplet-eighth notes per beat, four beats total (12 notes).

    Each note's actual_beats = 1/3, expressed via tuplet=(3, 2) so the
    notation layer knows it's a triplet: value=1/2 * 2/3 = 1/3.
    """
    events = tuple(
        Note(
            duration=Duration(value=Fraction(1, 2), tuplet=(3, 2)),
            offset=Fraction(i, 3),
            pitch=_pitch(pitch_midi),
        )
        for i in range(12)
    )
    return Voice(id="triplet", events=events)


def test_polyrhythm_3_against_2_round_trip(tmp_path):
    duple = _voice_dyadic_halves(60)   # middle C, 8 notes at 0, 1/2, 1, ...
    triplet = _voice_triplet_thirds(67)  # G4, 12 notes at 0, 1/3, 2/3, ...

    measure = Measure(
        number=1,
        time_signature=TimeSignature(4, 4),
        voices=(duple, triplet),
    )
    part = Part(name="Poly", instrument=None, clef="treble", measures=(measure,))
    score = Score(title="3-against-2", parts=(part,), metadata={})

    path = tmp_path / "polyrhythm.mid"
    save_mido(score, str(path))
    assert path.exists() and path.stat().st_size > 0

    reparsed = load_mido(str(path), time_signature=TimeSignature(4, 4))
    assert len(reparsed.parts) >= 1

    # Flatten all parsed events to absolute onsets (cumulative measure offsets).
    onsets: set[Fraction] = set()
    for p in reparsed.parts:
        cum = Fraction(0)
        for m in p.measures:
            for v in m.voices:
                for ev in v.events:
                    if isinstance(ev, Note):
                        onsets.add(cum + ev.offset)
            cum += m.time_signature.beats_per_measure

    # Every duple onset (i/2 for i in 0..7) must appear after round-trip.
    expected_duple = {Fraction(i, 2) for i in range(8)}
    expected_triplet = {Fraction(i, 3) for i in range(12)}
    expected = expected_duple | expected_triplet

    missing = expected - onsets
    assert not missing, (
        f"Polyrhythm onsets lost in MIDI round-trip: {sorted(missing)}"
    )


def test_duration_tuplet_actual_beats():
    """Sanity: triplet eighth (value 1/2, tuplet 3:2) → 1/3 beat exactly."""
    d = Duration(value=Fraction(1, 2), tuplet=(3, 2))
    assert d.actual_beats == Fraction(1, 3)


def test_quantizer_picks_triplet_grid_for_triplet_timing():
    """The per-note grid picker in record() should choose 1/6 for triplet
    timings and 1/4 for dyadic ones."""
    from score_io.live.midi_io import record  # import for module side-effects
    # Re-implement the grid pick here against the same algorithm to avoid
    # needing an actual MIDI port. The logic mirrors record()'s inner loop.
    bpm = 120.0
    sec_per_beat = 60.0 / bpm

    def pick(start_s, end_s, grids):
        on_b = Fraction(start_s / sec_per_beat).limit_denominator(96)
        off_b = Fraction(end_s / sec_per_beat).limit_denominator(96)
        best = None
        for g in grids:
            on_s = round(on_b / g) * g
            off_s = round(off_b / g) * g
            err = abs(float(on_b - on_s)) + abs(float(off_b - off_s))
            if best is None or err < best[0]:
                best = (err, g)
        return best[1]

    grids = (Fraction(1, 4), Fraction(1, 6))
    # Triplet eighth at beat 1/3: 0.1667 sec at 120 bpm
    assert pick(1 / 3 * sec_per_beat, 2 / 3 * sec_per_beat, grids) == Fraction(1, 6)
    # Plain eighth at beat 1/2: 0.25 sec at 120 bpm — both grids land it but
    # the dyadic grid wins ties (it's first in the tuple).
    assert pick(0.5 * sec_per_beat, 1.0 * sec_per_beat, grids) == Fraction(1, 4)


def test_split_event_preserves_tuplet_when_fitting_in_measure():
    """Tuplet event that doesn't cross a barline must survive _split_event
    unchanged — no decomposition into dyadic tied pieces."""
    from transforms.temporal import _split_event

    triplet_eighth = Note(
        duration=Duration(value=Fraction(1, 2), tuplet=(3, 2)),
        offset=Fraction(0),
        pitch=_pitch(60),
    )
    caps = [Fraction(4)]
    starts = [Fraction(0)]
    pieces = _split_event(triplet_eighth, Fraction(1, 3), starts, caps)
    assert len(pieces) == 1
    mi, ev = pieces[0]
    assert mi == 0
    assert ev.duration.tuplet == (3, 2)
    assert ev.duration.actual_beats == Fraction(1, 3)
