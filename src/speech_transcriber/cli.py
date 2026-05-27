"""Command line interface."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from speech_transcriber import __version__
from speech_transcriber.config import Settings
from speech_transcriber.errors import SpeechTranscriberError
from speech_transcriber.models import SpeakerRole, TranscribeOptions, TranscriptResult
from speech_transcriber.providers.factory import get_transcriber

app = typer.Typer(help="Speech Transcriber CLI")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(f"speech-transcriber {__version__}")


@app.command()
def transcribe(
    audio_path: Annotated[Path, typer.Argument(help="Local audio file path")],
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Provider name, default from .env"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: json or text"),
    ] = "json",
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output-file",
            help=(
                "Write output to a file path, or to a directory with an "
                "auto-generated filename."
            ),
        ),
    ] = None,
    speaker_role_name: Annotated[
        str | None,
        typer.Option(
            "--speaker-role-name",
            help="Target speaker role name for role separation.",
        ),
    ] = None,
    speaker_role_audio: Annotated[
        Path | None,
        typer.Option(
            "--speaker-role-audio",
            help="Local clean voice sample for the target speaker.",
        ),
    ] = None,
    speaker_role_audio_url: Annotated[
        str | None,
        typer.Option(
            "--speaker-role-audio-url",
            help="Public URL for the target speaker voice sample.",
        ),
    ] = None,
) -> None:
    """Transcribe a local audio file and print the result."""
    if not audio_path.exists():
        typer.echo(f"Audio file not found: {audio_path}", err=True)
        raise typer.Exit(code=1)
    speaker_role = _build_speaker_role(
        speaker_role_name,
        speaker_role_audio,
        speaker_role_audio_url,
    )
    if speaker_role_audio and not speaker_role_audio.exists():
        typer.echo(f"Speaker role audio file not found: {speaker_role_audio}", err=True)
        raise typer.Exit(code=1)
    try:
        result = asyncio.run(_transcribe(audio_path, provider, speaker_role))
    except SpeechTranscriberError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    rendered = _render_result(result, output)
    if output_file:
        written_path = _write_output_file(
            output_file,
            audio_path=audio_path,
            output_format=output,
            content=rendered,
        )
        typer.echo(f"Wrote transcript to: {written_path}")
        return

    typer.echo(rendered)


def _render_result(result: TranscriptResult, output: str) -> str:
    if output == "text":
        return result.text
    if output != "json":
        typer.echo(f"Unsupported output format: {output}", err=True)
        raise typer.Exit(code=1)
    return result.model_dump_json()


def _write_output_file(
    output_file: Path,
    *,
    audio_path: Path,
    output_format: str,
    content: str,
) -> Path:
    output_path = _resolve_output_path(output_file, audio_path, output_format)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{content}\n", encoding="utf-8")
    return output_path


def _resolve_output_path(
    output_file: Path,
    audio_path: Path,
    output_format: str,
) -> Path:
    if output_file.is_dir() or not output_file.suffix:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
        extension = "txt" if output_format == "text" else output_format
        return output_file / f"{timestamp}-{audio_path.name}.{extension}"
    return output_file


def _build_speaker_role(
    name: str | None,
    audio_path: Path | None,
    audio_url: str | None,
) -> SpeakerRole | None:
    if not any([name, audio_path, audio_url]):
        return None
    if not name:
        typer.echo(
            "--speaker-role-name is required for speaker role separation",
            err=True,
        )
        raise typer.Exit(code=1)
    if bool(audio_path) == bool(audio_url):
        typer.echo(
            "--speaker-role-name requires --speaker-role-audio or "
            "--speaker-role-audio-url, but not both",
            err=True,
        )
        raise typer.Exit(code=1)
    return SpeakerRole(name=name, audio_path=audio_path, audio_url=audio_url)


async def _transcribe(
    audio_path: Path,
    provider: str | None,
    speaker_role: SpeakerRole | None,
) -> TranscriptResult:
    settings = Settings()
    transcriber = get_transcriber(settings, provider)
    provider_name = provider or settings.default_provider
    return await transcriber.transcribe(
        audio_path,
        TranscribeOptions(provider=provider_name, speaker_role=speaker_role),
    )
