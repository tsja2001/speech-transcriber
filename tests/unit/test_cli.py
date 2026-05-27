"""CLI behavior tests."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from speech_transcriber import cli
from speech_transcriber.cli import app
from speech_transcriber.models import (
    TranscribeOptions,
    TranscriptResult,
    TranscriptSegment,
)


class FakeTranscriber:
    def __init__(self) -> None:
        self.options: TranscribeOptions | None = None

    async def transcribe(
        self,
        audio_path: Path,
        options: TranscribeOptions,
    ) -> TranscriptResult:
        self.options = options
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
    fake_transcriber = FakeTranscriber()
    monkeypatch.setattr(
        "speech_transcriber.cli.get_transcriber",
        lambda settings, provider=None: fake_transcriber,
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
    assert fake_transcriber.options is not None
    assert fake_transcriber.options.speaker_role is None


def test_transcribe_writes_json_to_explicit_output_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "audio.mp3"
    output_path = tmp_path / "transcript.json"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(
        "speech_transcriber.cli.get_transcriber",
        lambda settings, provider=None: FakeTranscriber(),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "transcribe",
            str(audio_path),
            "--provider",
            "fake",
            "--output",
            "json",
            "--output-file",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text())
    assert payload["text"] == "transcribed:audio.mp3"
    assert str(output_path) in result.stdout


def test_transcribe_writes_text_to_generated_output_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "podcast.mp3"
    output_dir = tmp_path / "transcripts"
    audio_path.write_bytes(b"audio")
    monkeypatch.setattr(
        "speech_transcriber.cli.get_transcriber",
        lambda settings, provider=None: FakeTranscriber(),
    )
    monkeypatch.setattr(
        cli,
        "datetime",
        type(
            "FixedDatetime",
            (),
            {"now": staticmethod(lambda: datetime(2026, 5, 27, 15, 4, 5))},
        ),
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "transcribe",
            str(audio_path),
            "--provider",
            "fake",
            "--output",
            "text",
            "--output-file",
            str(output_dir),
        ],
    )

    expected_path = output_dir / "2026-05-27-15:04:05-podcast.mp3.txt"
    assert result.exit_code == 0
    assert expected_path.read_text() == "transcribed:podcast.mp3\n"
    assert str(expected_path) in result.stdout


def test_transcribe_passes_speaker_role_audio_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "audio.mp3"
    role_audio_path = tmp_path / "host.wav"
    audio_path.write_bytes(b"audio")
    role_audio_path.write_bytes(b"voice")
    fake_transcriber = FakeTranscriber()
    monkeypatch.setattr(
        "speech_transcriber.cli.get_transcriber",
        lambda settings, provider=None: fake_transcriber,
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "transcribe",
            str(audio_path),
            "--provider",
            "fake",
            "--speaker-role-name",
            "HOST",
            "--speaker-role-audio",
            str(role_audio_path),
        ],
    )

    assert result.exit_code == 0
    assert fake_transcriber.options is not None
    assert fake_transcriber.options.speaker_role is not None
    assert fake_transcriber.options.speaker_role.name == "HOST"
    assert fake_transcriber.options.speaker_role.audio_path == role_audio_path
    assert fake_transcriber.options.speaker_role.audio_url is None


def test_transcribe_rejects_incomplete_speaker_role(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["transcribe", str(audio_path), "--speaker-role-name", "HOST"],
    )

    assert result.exit_code == 1
    assert "requires --speaker-role-audio or --speaker-role-audio-url" in result.stderr


def test_transcribe_rejects_missing_audio() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["transcribe", "/missing/audio.mp3"])

    assert result.exit_code == 1
    assert "Audio file not found" in result.stderr
