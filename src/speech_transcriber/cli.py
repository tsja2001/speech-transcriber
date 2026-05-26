"""Command line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from speech_transcriber import __version__
from speech_transcriber.config import Settings
from speech_transcriber.errors import SpeechTranscriberError
from speech_transcriber.models import TranscribeOptions, TranscriptResult
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
) -> None:
    """Transcribe a local audio file and print the result."""
    if not audio_path.exists():
        typer.echo(f"Audio file not found: {audio_path}", err=True)
        raise typer.Exit(code=1)
    try:
        result = asyncio.run(_transcribe(audio_path, provider))
    except SpeechTranscriberError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if output == "text":
        typer.echo(result.text)
        return
    if output != "json":
        typer.echo(f"Unsupported output format: {output}", err=True)
        raise typer.Exit(code=1)
    typer.echo(result.model_dump_json())


async def _transcribe(audio_path: Path, provider: str | None) -> TranscriptResult:
    settings = Settings()
    transcriber = get_transcriber(settings, provider)
    provider_name = provider or settings.default_provider
    return await transcriber.transcribe(
        audio_path,
        TranscribeOptions(provider=provider_name),
    )
