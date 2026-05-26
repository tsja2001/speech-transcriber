"""Provider interface for speech-to-text implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from speech_transcriber.models import TranscribeOptions, TranscriptResult


class Transcriber(Protocol):
    """Common interface implemented by all speech-to-text providers."""

    async def transcribe(
        self,
        audio_path: Path,
        options: TranscribeOptions,
    ) -> TranscriptResult: ...
