from __future__ import annotations
from fractions import Fraction

from model.pitch import Pitch
from model.duration import Duration
from model.events import Note, Rest, Chord, Event
from model.voice import Voice
from model.measure import Measure, TimeSignature, TempoMark, KeySignature
from model.part import Part
from model.score import Score


class SerializeError(Exception):
    pass


# Model beat = quarter note = Fraction(1, 1)
# LilyPond duration numbers: 1=whole, 2=half, 4=quarter, 8=eighth, 16=16th, 32=32nd
_BEAT_TO_LILY: dict[Fraction, str] = {
    Fraction(16, 1): "\\longa",
    Fraction(8, 1):  "\\breve",
    Fraction(4, 1):  "1",
    Fraction(2, 1):  "2",
    Fraction(1, 1):  "4",
    Fraction(1, 2):  "8",
    Fraction(1, 4):  "16",
    Fraction(1, 8):  "32",
    Fraction(1, 16): "64",
}

# LilyPond note names (pitch class → base name)
_PC_TO_LILY: dict[int, str] = {
    0: "c", 1: "cis", 2: "d", 3: "dis", 4: "e",
    5: "f", 6: "fis", 7: "g", 8: "gis", 9: "a",
    10: "bes", 11: "b",
}

# Override for flat spellings
_SPELLING_TO_LILY: dict[str, str] = {
    "Cb": "ces", "Db": "des", "Eb": "ees", "Fb": "fes",
    "Gb": "ges", "Ab": "aes", "Bb": "bes",
    "C#": "cis", "D#": "dis", "E#": "eis", "F#": "fis",
    "G#": "gis", "A#": "ais", "B#": "bis",
}


def _lily_pitch(pitch: Pitch) -> str:
    """Convert Pitch to LilyPond note name with octave marks."""
    base = _SPELLING_TO_LILY.get(pitch.spelling, _PC_TO_LILY.get(pitch.pitch_class))
    if base is None:
        raise SerializeError(f"Cannot serialize pitch spelling '{pitch.spelling}'")
    # LilyPond octave: c' = C4 (octave 4), c = C3, c, = C2, c'' = C5
    octave_marks: str
    if pitch.octave >= 4:
        octave_marks = "'" * (pitch.octave - 3)
    elif pitch.octave == 3:
        octave_marks = ""
    else:
        octave_marks = "," * (3 - pitch.octave)
    return base + octave_marks


def _lily_duration(duration: Duration) -> str:
    """Convert Duration to LilyPond duration string.

    The returned code reflects the *written* duration only; tuplet ratios
    are emitted by `\\tuplet N/M { ... }` wrappers in `_lily_voice`, not by
    scaling individual note durations.
    """
    code = _BEAT_TO_LILY.get(duration.value)
    if code is None:
        raise SerializeError(
            f"Cannot represent duration value {duration.value} in LilyPond notation"
        )
    return code + ("." * duration.dots)


def _lily_event(event: Event) -> str:
    dur = _lily_duration(event.duration)
    if isinstance(event, Rest):
        return f"r{dur}"
    # In LilyPond, `~` after the starting note creates a tie to the next note.
    # We emit it on "start" and "continue"; the receiving "stop" note bears no marker.
    tie_mark = "~" if getattr(event, "tie", None) in ("start", "continue") else ""
    slur = getattr(event, "slur", None)
    slur_mark = "(" if slur == "start" else (")" if slur == "stop" else "")
    if isinstance(event, Note):
        pitch_str = _lily_pitch(event.pitch)
        result = f"{pitch_str}{dur}{tie_mark}{slur_mark}"
        if event.articulations:
            result += "".join(f"-{a}" for a in event.articulations)
        if event.dynamic:
            result += f"\\{event.dynamic}"
        return result
    # Chord
    pitches_str = " ".join(_lily_pitch(p) for p in event.pitches)
    result = f"<{pitches_str}>{dur}{tie_mark}{slur_mark}"
    if event.articulations:
        result += "".join(f"-{a}" for a in event.articulations)
    if event.dynamic:
        result += f"\\{event.dynamic}"
    return result


def _lily_voice(voice: Voice) -> str:
    """Emit a Voice.

    - Runs of consecutive grace events become `\\grace { ... }` and are
      attached to the next non-grace event.
    - Runs of consecutive same-tuplet events become `\\tuplet a/n { ... }`.

    Grace processing happens before tuplet processing — graces themselves
    don't participate in tuplet groups.
    """
    # First pass: split into grace runs followed by their host event.
    # Each item is either a host token (str) or a (graces, host) where graces
    # is a list of grace-event strings already rendered.
    items: list[str] = []
    grace_buffer: list[str] = []
    pending_tup: tuple[int, int] | None = None
    tup_buffer: list[str] = []

    def flush_tup() -> None:
        nonlocal tup_buffer, pending_tup
        if not tup_buffer:
            return
        if pending_tup is None:
            items.extend(tup_buffer)
        else:
            a, n = pending_tup
            items.append(f"\\tuplet {a}/{n} {{ {' '.join(tup_buffer)} }}")
        tup_buffer = []

    for e in voice.events:
        if getattr(e, "is_grace", False):
            # Graces buffer up; they don't break/start tuplet groups.
            grace_buffer.append(_lily_event(e))
            continue
        e_tup = e.duration.tuplet
        if e_tup != pending_tup:
            flush_tup()
            pending_tup = e_tup
        host = _lily_event(e)
        if grace_buffer:
            host = f"\\grace {{ {' '.join(grace_buffer)} }} {host}"
            grace_buffer = []
        tup_buffer.append(host)
    flush_tup()
    # Trailing graces with no host: attach as bare \grace block.
    if grace_buffer:
        items.append(f"\\grace {{ {' '.join(grace_buffer)} }}")
    return " ".join(items)


def _voice_filter_staff(voice: Voice, staff: int) -> Voice | None:
    """Return a copy of `voice` containing only events on `staff`, or None if empty.

    Note: this is a simple filter — events on other staves are dropped, which can
    leave timing gaps for the rare case of a voice that genuinely crosses staves.
    Typical piano music keeps each voice on one staff, so this works in practice.
    """
    filtered = tuple(e for e in voice.events if getattr(e, "staff", 1) == staff)
    if not filtered:
        return None
    return Voice(id=voice.id, events=filtered)


def _lily_measure_voices(measure: Measure, staff: int | None = None) -> str:
    voices = measure.voices
    if staff is not None:
        voices = tuple(v for v in (_voice_filter_staff(v, staff) for v in voices) if v is not None)
    if not voices:
        # Whole-staff rest for the measure capacity
        capacity = measure.time_signature.beats_per_measure
        rest_dur = _BEAT_TO_LILY.get(capacity, "1")
        return f"r{rest_dur}"
    if len(voices) == 1:
        return _lily_voice(voices[0])
    parts = " \\\\ ".join(f"{{ {_lily_voice(v)} }}" for v in voices)
    return f"<< {parts} >>"


def _lily_time(ts: TimeSignature) -> str:
    return f"\\time {ts.numerator}/{ts.denominator}"


# fifths (-7..+7) → LilyPond tonic for major and minor keys
_FIFTHS_TO_MAJOR_TONIC: dict[int, str] = {
    -7: "ces", -6: "ges", -5: "des", -4: "aes", -3: "ees", -2: "bes", -1: "f",
    0: "c",
    1: "g", 2: "d", 3: "a", 4: "e", 5: "b", 6: "fis", 7: "cis",
}
_FIFTHS_TO_MINOR_TONIC: dict[int, str] = {
    -7: "aes", -6: "ees", -5: "bes", -4: "f", -3: "c", -2: "g", -1: "d",
    0: "a",
    1: "e", 2: "b", 3: "fis", 4: "cis", 5: "gis", 6: "dis", 7: "ais",
}


def _lily_key(key: KeySignature) -> str:
    table = _FIFTHS_TO_MAJOR_TONIC if key.mode == "major" else _FIFTHS_TO_MINOR_TONIC
    tonic = table[key.fifths]
    return f"\\key {tonic} \\{key.mode}"


def _lily_tempo(tm: TempoMark) -> str:
    # beat_unit is in model beats (quarter = Fraction(1,1))
    lily_beat = _BEAT_TO_LILY.get(tm.beat_unit, "4")
    bpm = int(tm.bpm)
    return f"\\tempo {lily_beat}={bpm}"


def _measure_is_anacrusis(measure: Measure) -> bool:
    """Check if a measure contains fewer beats than its time signature allows."""
    capacity = measure.time_signature.beats_per_measure
    # Calculate total beats in all voices
    max_beats = Fraction(0)
    for voice in measure.voices:
        voice_beats = sum(e.duration.actual_beats for e in voice.events)
        max_beats = max(max_beats, voice_beats)
    return max_beats < capacity and max_beats > 0


def _lily_partial(measure: Measure) -> str | None:
    """Return LilyPond \\partial directive if measure is anacrusis, else None.
    
    Only emits \\partial for the first anacrusis in a sequence (when the
    time signature is also being changed).
    """
    if not _measure_is_anacrusis(measure):
        return None
    
    # Calculate the partial value (beats that ARE present)
    max_beats = Fraction(0)
    for voice in measure.voices:
        voice_beats = sum(e.duration.actual_beats for e in voice.events)
        max_beats = max(max_beats, voice_beats)
    
    # Convert to LilyPond duration number
    partial_code = _BEAT_TO_LILY.get(max_beats)
    if partial_code is None:
        return None
    return f"\\partial {partial_code}"


def _lily_single_staff(part: Part, staff_idx: int, indent: str = "  ") -> list[str]:
    """Emit one `\\new Staff { ... }` block for the given staff (1-based).

    For single-staff parts, pass staff_idx=1 with `staff_filter=None` semantics —
    we still pass 1 because the filter matches default events (staff=1).
    """
    lines: list[str] = []
    clef = part.staff_clef(staff_idx)
    lines.append(f"{indent}\\new Staff {{")
    lines.append(f"{indent}  \\clef {clef}")

    prev_ts: TimeSignature | None = None
    prev_tempo: TempoMark | None = None
    prev_key: KeySignature | None = None
    is_first_measure = True

    # When the part is single-staff, don't filter — preserves backward behavior.
    use_filter: int | None = staff_idx if part.staff_count > 1 else None

    for measure in part.measures:
        ts = measure.time_signature

        ts_changed = ts != prev_ts
        need_partial = (is_first_measure or ts_changed) and _measure_is_anacrusis(measure)
        partial = _lily_partial(measure) if need_partial else None

        if ts_changed:
            lines.append(f"{indent}  {_lily_time(ts)}")
            prev_ts = ts
        if partial:
            lines.append(f"{indent}  {partial}")
        if measure.key_signature is not None and measure.key_signature != prev_key:
            lines.append(f"{indent}  {_lily_key(measure.key_signature)}")
            prev_key = measure.key_signature
        if measure.tempo is not None and measure.tempo != prev_tempo:
            lines.append(f"{indent}  {_lily_tempo(measure.tempo)}")
            prev_tempo = measure.tempo
        content = _lily_measure_voices(measure, staff=use_filter)
        lines.append(f"{indent}  {content}")
        
        is_first_measure = False

    lines.append(f"{indent}}}")
    return lines


def _lily_part(part: Part) -> str:
    if part.staff_count == 1:
        return "\n".join(_lily_single_staff(part, staff_idx=1))
    
    context = part.get_lilypond_context()
    lines: list[str] = [f"  \\new {context} <<"]
    
    for staff_idx in range(1, part.staff_count + 1):
        lines.extend(_lily_single_staff(part, staff_idx=staff_idx, indent="    "))
    
    lines.append("  >>")
    return "\n".join(lines)


def serialize(score: Score) -> str:
    """Serialize a Score to a LilyPond source string.

    Example: serialize(score) → '\\version "2.24.0" ...' valid LilyPond code.
    Raises SerializeError for pitches or durations that cannot be represented.
    """
    parts: list[str] = []
    parts.append('\\version "2.24.0"')
    parts.append("")
    title = score.title.replace('"', '\\"')
    parts.append(f'\\header {{ title = "{title}" }}')
    parts.append("")
    parts.append("\\score {")
    parts.append("  <<")
    for part in score.parts:
        parts.append(_lily_part(part))
    parts.append("  >>")
    parts.append("  \\layout { }")
    parts.append("  \\midi { }")
    parts.append("}")
    return "\n".join(parts) + "\n"


def save(score: Score, path: str) -> None:
    """Serialize score to LilyPond and write to path.

    The recipient does not need LilyPond installed locally — they can render
    the .ly file in MuseScore 4 (File → Import), Frescobaldi, or an online
    editor like https://www.lilybin.com/.

    Example: save(score, "canon.ly")
    """
    with open(path, "w", encoding="utf-8") as f:
        f.write(serialize(score))


def save_bundle(score: Score, zip_path: str) -> None:
    """Write a self-contained zip with the .ly source and a README.

    The recipient gets one file to email/share, with instructions for rendering
    that don't require a LilyPond install.

    Example: save_bundle(score, "canon.zip")
    """
    import zipfile

    readme = (
        "How to render score.ly\n"
        "======================\n"
        "\n"
        "You do NOT need LilyPond installed. Pick any one of:\n"
        "\n"
        "  1. Online: paste the contents of score.ly at https://www.lilybin.com/\n"
        "     or https://www.hacklily.org/ and click Render. Download PDF/MIDI.\n"
        "\n"
        "  2. MuseScore 4 (free, GUI): File -> Import -> select score.ly.\n"
        "     Edit and export to PDF, MIDI, MP3, etc.\n"
        "\n"
        "  3. Frescobaldi (desktop LilyPond IDE, bundles its own LilyPond on\n"
        "     Windows/Mac): open score.ly and press Ctrl+M.\n"
        "\n"
        "  4. Command line, if you do have LilyPond:  lilypond score.ly\n"
    )
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("score.ly", serialize(score))
        z.writestr("README.txt", readme)
