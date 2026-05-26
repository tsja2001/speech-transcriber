"""CLI behavior tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from speech_transcriber.cli import app
from speech_transcriber.models import TranscriptResult, TranscriptSegment


class FakeTranscriber:
    async def transcribe(self, audio_path: Path, options: object) -> TranscriptResult:
        return TranscriptResult(
            text=f"transcribed:{audio_path.name}",
            segments=[
                TranscriptSegment(
                    start=0,
                    end=1,
                    text="hello",
                    speaker="SPEAKER_0",
                )
            ],
            provider="fake",
            duration_seconds=1,
            has_diarization=True,
        )


def test_transcribe_outputs_json(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(
        "speech_transcriber.cli.get_transcriber",
        lambda settings, provider=None: FakeTranscriber(),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["transcribe", str(audio_path), "--provider", "fake", "--output", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["text"] == "transcribed:audio.mp3"
    assert payload["provider"] == "fake"
    assert payload["segments"][0]["speaker"] == "SPEAKER_0"


def test_transcribe_rejects_missing_audio() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["transcribe", "/missing/audio.mp3"])

    assert result.exit_code == 1
    assert "Audio file not found" in result.stderr
