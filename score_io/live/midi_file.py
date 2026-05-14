"""Direct mido-based MIDI file writer/reader.

The music21-backed serializer (score_io.serializers.midi) renotates the
piece, which mangles polyrhythms because music21's notation layer collapses
voices onto a single notatable timeline. For pure MIDI fidelity — exact
tick onsets and durations, with each Voice on its own MIDI track — go
through this module instead. No notation reasoning involved.
"""
from __future__ import annotations
from fractions import Fraction

import mido

from model.duration import Duration
from model.events import Note, Rest, Chord
from model.pitch import Pitch
from model.voice import Voice
from model.measure import Measure, TimeSignature
from model.part import Part
from model.score import Score


_MIDI_SPELLING = {
    0: "C", 1: "C#", 2: "D", 3: "D#", 4: "E",
    5: "F", 6: "F#", 7: "G", 8: "G#", 9: "A",
    10: "Bb", 11: "B",
}


def _midi_to_pitch(midi: int) -> Pitch:
    return Pitch(midi=midi, spelling=_MIDI_SPELLING[midi % 12], octave=midi // 12 - 1)


def save_mido(score: Score, path: str, *, ppq: int = 480) -> None:
    """Write a Score to MIDI using mido directly. One track per (part, voice).

    Onsets and durations are rendered at full Fraction precision against
    `ppq` ticks-per-quarter; pick a large ppq (default 480) so triplets,
    quintuplets, etc. quantize cleanly.
    """
    mid = mido.MidiFile(ticks_per_beat=ppq)

    for part in score.parts:
        # Gather (voice_id -> list of (abs_beat, event)) across all measures.
        streams: dict[str, list[tuple[Fraction, object]]] = {}
        cum = Fraction(0)
        for m in part.measures:
            for v in m.voices:
                streams.setdefault(v.id, [])
                for ev in v.events:
                    streams[v.id].append((cum + ev.offset, ev))
            cum += m.time_signature.beats_per_measure

        for vid, stream in streams.items():
            track = mido.MidiTrack()
            mid.tracks.append(track)
            track.append(mido.MetaMessage("track_name", name=f"{part.name}/{vid}"))

            events: list[tuple[int, mido.Message]] = []
            for abs_beat, ev in stream:
                on_tick = int(round(abs_beat * ppq))
                dur_ticks = int(round(ev.duration.actual_beats * ppq))
                if dur_ticks <= 0:
                    continue
                off_tick = on_tick + dur_ticks
                if isinstance(ev, Note):
                    events.append((on_tick, mido.Message("note_on", note=ev.pitch.midi, velocity=80)))
                    events.append((off_tick, mido.Message("note_off", note=ev.pitch.midi, velocity=0)))
                elif isinstance(ev, Chord):
                    for p in ev.pitches:
                        events.append((on_tick, mido.Message("note_on", note=p.midi, velocity=80)))
                        events.append((off_tick, mido.Message("note_off", note=p.midi, velocity=0)))
                # Rests contribute no MIDI messages — silence is implicit.

            # Sort by tick; ties: note_off before note_on at the same tick so a
            # zero-gap legato doesn't drop the next note.
            events.sort(key=lambda t: (t[0], 0 if t[1].type == "note_off" else 1))
            prev = 0
            for tick, msg in events:
                msg.time = tick - prev
                track.append(msg)
                prev = tick

    mid.save(path)


def load_mido(
    path: str,
    *,
    time_signature: TimeSignature = TimeSignature(4, 4),
) -> Score:
    """Read a MIDI file written by save_mido (or any tick-accurate MIDI) and
    reconstruct a Score with one Voice per track. Offsets/durations are
    returned as exact Fractions (denominator ≤ 96) so triplet and quintuplet
    grids survive.
    """
    mid = mido.MidiFile(path)
    ppq = mid.ticks_per_beat
    capacity = Fraction(time_signature.numerator * 4, time_signature.denominator)

    voices: list[Voice] = []
    last_end = Fraction(0)
    for ti, track in enumerate(mid.tracks):
        track_name = f"v{ti}"
        for msg in track:
            if msg.type == "track_name":
                track_name = msg.name.split("/")[-1] or f"v{ti}"
                break

        absolute = 0
        open_notes: dict[int, int] = {}
        events: list[Note] = []
        for msg in track:
            absolute += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                open_notes[msg.note] = absolute
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                on_tick = open_notes.pop(msg.note, None)
                if on_tick is None:
                    continue
                onset = Fraction(on_tick, ppq).limit_denominator(96)
                dur = Fraction(absolute - on_tick, ppq).limit_denominator(96)
                if dur <= 0:
                    continue
                events.append(Note(
                    duration=Duration(value=dur),
                    offset=onset,
                    pitch=_midi_to_pitch(msg.note),
                ))
                end = onset + dur
                if end > last_end:
                    last_end = end

        if events:
            events.sort(key=lambda e: e.offset)
            voices.append(Voice(id=track_name, events=tuple(events)))

    # Re-bin all voice events into measures of `time_signature`, preserving
    # voice identity. Each measure contains one Voice per source voice that
    # has events in that bar.
    n_measures = max(1, int(-(-last_end // capacity))) if voices else 1
    measures: list[Measure] = []
    for i in range(n_measures):
        m_start = capacity * i
        m_end = m_start + capacity
        m_voices: list[Voice] = []
        for v in voices:
            from dataclasses import replace
            local = tuple(
                replace(e, offset=e.offset - m_start)
                for e in v.events
                if m_start <= e.offset < m_end
            )
            if local:
                m_voices.append(Voice(id=v.id, events=local))
        if not m_voices:
            m_voices = [Voice(id="rest", events=(
                Rest(duration=Duration(value=capacity), offset=Fraction(0)),
            ))]
        measures.append(Measure(
            number=i + 1,
            time_signature=time_signature,
            voices=tuple(m_voices),
        ))

    part = Part(name="MIDI", instrument=None, clef="treble", measures=tuple(measures))
    return Score(title="MIDI Load", parts=(part,), metadata={})
