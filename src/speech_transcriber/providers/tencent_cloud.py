"""Tencent Cloud ASR provider and response parsing."""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from typing import Any, Protocol

from tencentcloud.asr.v20190614 import models  # type: ignore[import-untyped]

from speech_transcriber.errors import ProviderError
from speech_transcriber.models import (
    TranscribeOptions,
    TranscriptResult,
    TranscriptSegment,
)

TENCENT_PROVIDER_NAME = "tencent_cloud"
PENDING_STATUSES = {0, 1}
SUCCESS_STATUS = 2
FAILED_STATUS = 3
RESULT_LINE_PATTERN = re.compile(
    r"^\[(?P<start>[^,\]]+),(?P<end>[^\]]+)\]\s*(?P<text>.+)$"
)


class TencentAsrClient(Protocol):
    """Small protocol matching the Tencent ASR SDK methods we use."""

    def CreateRecTask(self, request: Any) -> Any: ...  # noqa: N802

    def DescribeTaskStatus(self, request: Any) -> Any: ...  # noqa: N802


class TencentCosStorage(Protocol):
    """COS storage protocol used by the provider."""

    delete_after_transcribe: bool

    async def upload_and_presign(self, audio_path: Path) -> tuple[str, str]: ...

    async def delete(self, object_key: str) -> None: ...


class TencentCloudTranscriber:
    """Transcribe audio through Tencent Cloud recording-file ASR."""

    def __init__(
        self,
        *,
        client: TencentAsrClient,
        cos_storage: TencentCosStorage,
        engine_model_type: str = "16k_zh_large",
        res_text_format: int = 2,
        speaker_diarization: int = 0,
        poll_interval_seconds: float = 3.0,
        timeout_seconds: float = 10800.0,
    ) -> None:
        self.client = client
        self.cos_storage = cos_storage
        self.engine_model_type = engine_model_type
        self.res_text_format = res_text_format
        self.speaker_diarization = speaker_diarization
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds

    async def transcribe(
        self,
        audio_path: Path,
        options: TranscribeOptions,
    ) -> TranscriptResult:
        """Upload audio to COS, run Tencent ASR, and parse the completed result."""
        del options
        if not await asyncio.to_thread(audio_path.exists):
            raise ProviderError(
                TENCENT_PROVIDER_NAME,
                f"Audio file not found: {audio_path}",
                retryable=False,
            )

        object_key: str | None = None
        try:
            object_key, audio_url = await self.cos_storage.upload_and_presign(
                audio_path
            )
            task_id = await self._create_task(audio_url)
            task_status = await self._poll_until_finished(task_id)
            return parse_task_status(task_status, provider=TENCENT_PROVIDER_NAME)
        finally:
            if object_key and self.cos_storage.delete_after_transcribe:
                await self.cos_storage.delete(object_key)

    async def _create_task(self, audio_url: str) -> int:
        request = models.CreateRecTaskRequest()
        request.EngineModelType = self.engine_model_type
        request.ChannelNum = 1
        request.ResTextFormat = self.res_text_format
        request.SourceType = 0
        request.Url = audio_url
        request.SpeakerDiarization = self.speaker_diarization
        request.EmotionRecognition = 0
        request.EmotionalEnergy = 0
        request.FilterDirty = 0
        request.FilterPunc = 0
        request.FilterModal = 0
        request.ConvertNumMode = 1

        response = await asyncio.to_thread(self.client.CreateRecTask, request)
        task = _get_value(response, "Data", None)
        task_id = _get_value(task, "TaskId", None)
        if task_id is None:
            raise ProviderError(
                TENCENT_PROVIDER_NAME,
                "CreateRecTask response missing Data.TaskId",
                retryable=True,
            )
        return int(task_id)

    async def _poll_until_finished(self, task_id: int) -> Any:
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            request = models.DescribeTaskStatusRequest()
            request.TaskId = task_id
            response = await asyncio.to_thread(self.client.DescribeTaskStatus, request)
            task_status = _get_value(response, "Data", None)
            status = int(_get_value(task_status, "Status", -1))

            if status == SUCCESS_STATUS:
                return task_status
            if status == FAILED_STATUS:
                message = str(
                    _get_value(task_status, "ErrorMsg", "") or "ASR task failed"
                )
                raise ProviderError(TENCENT_PROVIDER_NAME, message, retryable=False)
            if status not in PENDING_STATUSES:
                raise ProviderError(
                    TENCENT_PROVIDER_NAME,
                    f"Unknown ASR task status: {status}",
                    retryable=True,
                )
            if time.monotonic() >= deadline:
                raise ProviderError(
                    TENCENT_PROVIDER_NAME,
                    f"ASR task timed out after {self.timeout_seconds} seconds",
                    retryable=True,
                )
            await asyncio.sleep(self.poll_interval_seconds)

def parse_task_status(
    task_status: Any,
    *,
    provider: str = TENCENT_PROVIDER_NAME,
) -> TranscriptResult:
    """Parse Tencent DescribeTaskStatus.Data into the public result model."""
    result_detail = _get_value(task_status, "ResultDetail", None) or []
    segments = _parse_result_detail(list(result_detail))
    if not segments:
        result = str(_get_value(task_status, "Result", "") or "")
        segments = _parse_result_fallback(result)

    text = " ".join(segment.text for segment in segments)
    return TranscriptResult(
        text=text,
        segments=segments,
        provider=provider,
        duration_seconds=_duration_or_none(
            _get_value(task_status, "AudioDuration", None)
        ),
        has_diarization=any(segment.speaker is not None for segment in segments),
    )


def _parse_result_detail(result_detail: list[Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for item in result_detail:
        text = str(
            _get_value(item, "FinalSentence", None)
            or _get_value(item, "WrittenText", None)
            or _get_value(item, "SliceSentence", None)
            or ""
        ).strip()
        if not text:
            continue

        start_ms = float(_get_value(item, "StartMs", 0) or 0)
        end_ms = float(_get_value(item, "EndMs", start_ms) or start_ms)
        speaker_id = _get_value(item, "SpeakerId", None)
        speaker = (
            f"SPEAKER_{speaker_id}"
            if speaker_id is not None and int(speaker_id) >= 0
            else None
        )
        segments.append(
            TranscriptSegment(
                text=text,
                start=start_ms / 1000.0,
                end=end_ms / 1000.0,
                speaker=speaker,
                confidence=None,
            )
        )
    return segments


def _parse_result_fallback(result: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    plain_lines: list[str] = []

    for line in result.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = RESULT_LINE_PATTERN.match(stripped)
        if match is None:
            plain_lines.append(stripped)
            continue
        segments.append(
            TranscriptSegment(
                text=match.group("text").strip(),
                start=_parse_timestamp(match.group("start")),
                end=_parse_timestamp(match.group("end")),
            )
        )

    if segments:
        return segments
    if plain_lines:
        return [
            TranscriptSegment(
                text=" ".join(plain_lines),
                start=0.0,
                end=0.0,
            )
        ]
    return []


def _parse_timestamp(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    return float(value)


def _duration_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _get_value(obj: Any, name: str, default: Any) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
