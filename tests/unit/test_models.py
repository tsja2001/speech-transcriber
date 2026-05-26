"""Tests for public data models."""

from __future__ import annotations

from speech_transcriber.models import (
    ErrorInfo,
    TranscriptResult,
    TranscriptSegment,
)


def test_transcript_result_serializes_segments() -> None:
    segment = TranscriptSegment(
        start=0.0,
        end=1.25,
        text="hello world",
        speaker="SPEAKER_0",
        confidence=None,
    )

    result = TranscriptResult(
        text="hello world",
        segments=[segment],
        provider="tencent_cloud",
        duration_seconds=1.25,
        has_diarization=True,
        metadata={"task_id": 123},
    )

    payload = result.model_dump()
    assert payload["text"] == "hello world"
    assert payload["segments"][0]["speaker"] == "SPEAKER_0"
    assert payload["metadata"] == {"task_id": 123}


def test_error_info_serializes_retryable_flag() -> None:
    error = ErrorInfo(
        code="provider_error",
        message="ASR task failed",
        retryable=False,
    )

    payload = error.model_dump()

    assert payload["code"] == "provider_error"
    assert payload["message"] == "ASR task failed"
    assert payload["retryable"] is False
