from __future__ import annotations
import subprocess
import tempfile
import os
import shutil


def render(
    ly_source: str,
    output_path: str,
    formats: list[str] | None = None,
) -> None:
    """Render LilyPond source to one or more output formats.

    Writes a temporary .ly file, calls the LilyPond CLI, then cleans up.

    Args:
        ly_source: Valid LilyPond source code.
        output_path: Path prefix for output files (without extension).
        formats: List of formats to generate — "pdf", "svg", "png", "midi".
                 Defaults to ["pdf"].

    Raises:
        EnvironmentError: If the lilypond executable is not found in PATH.
        RuntimeError: If LilyPond exits with a non-zero status.

    Example: render(ly_code, "output/piece") generates output/piece.pdf.
    """
    if formats is None:
        formats = ["pdf"]

    if shutil.which("lilypond") is None:
        raise EnvironmentError(
            "LilyPond executable not found in PATH.\n"
            "\n"
            "If you don't want to install LilyPond locally, write the source\n"
            "to a file instead and render it elsewhere:\n"
            "\n"
            "    from score_io.serializers.lilypond import save, save_bundle\n"
            "    save(score, 'out.ly')              # plain .ly file\n"
            "    save_bundle(score, 'out.zip')      # .ly + README with render options\n"
            "\n"
            "The .ly file can be rendered at https://www.lilybin.com/, in\n"
            "MuseScore 4 (File -> Import), or in Frescobaldi -- none require a\n"
            "system LilyPond install.\n"
            "\n"
            "Otherwise install LilyPond from https://lilypond.org/download.html\n"
            "and ensure it is on your PATH."
        )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ly", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(ly_source)
        tmp.close()

        cmd = ["lilypond"]
        for fmt in formats:
            if fmt == "pdf":
                pass  # default
            elif fmt == "svg":
                cmd += ["-dbackend=svg"]
            elif fmt == "png":
                cmd += ["-dbackend=eps", "-dpaper-size=a4", "--png"]
            elif fmt == "midi":
                pass  # LilyPond generates MIDI via \midi{} block in source
            else:
                raise ValueError(f"Unsupported format '{fmt}'")
        cmd += [f"--output={output_path}", tmp.name]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"LilyPond failed (exit {result.returncode}):\n{result.stderr}"
            )
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
