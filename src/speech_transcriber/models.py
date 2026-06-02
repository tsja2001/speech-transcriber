"""Shared request, result, and job models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    """A timestamped transcript segment."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    speaker: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class TranscriptResult(BaseModel):
    """Provider-neutral transcription result."""

    text: str
    segments: list[TranscriptSegment]
    provider: str
    duration_seconds: float | None = None
    has_diarization: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SpeakerRole(BaseModel):
    """Voice sample used to identify one target speaker role."""

    name: str
    audio_path: Path | None = None
    audio_url: str | None = None


class TranscribeOptions(BaseModel):
    """Provider-neutral transcription options."""

    language: str = "en"
    diarize: bool = True
    provider: str = "tencent_cloud"
    speaker_role: SpeakerRole | None = None
    provider_options: dict[str, Any] = Field(default_factory=dict)


class ErrorInfo(BaseModel):
    """Serializable error details stored on failed jobs."""

    code: str
    message: str
    retryable: bool
