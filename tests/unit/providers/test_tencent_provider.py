"""Tests for TencentCloudTranscriber."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from speech_transcriber.errors import ProviderError
from speech_transcriber.models import TranscribeOptions
from speech_transcriber.providers.tencent_cloud import TencentCloudTranscriber


class FakeCosStorage:
    """Fake COS storage with the same async surface as production storage."""

    def __init__(self) -> None:
        self.uploaded: list[Path] = []
        self.deleted: list[str] = []
        self.delete_after_transcribe = True

    async def upload_and_presign(self, audio_path: Path) -> tuple[str, str]:
        self.uploaded.append(audio_path)
        return "podlator/audio.mp3", "https://cos.example.com/audio.mp3"

    async def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)


class FakeAsrClient:
    def __init__(self, statuses: list[SimpleNamespace]) -> None:
        self.statuses = statuses
        self.create_requests: list[SimpleNamespace] = []
        self.describe_task_ids: list[int] = []

    def CreateRecTask(self, request: SimpleNamespace) -> SimpleNamespace:  # noqa: N802
        self.create_requests.append(request)
        return SimpleNamespace(Data=SimpleNamespace(TaskId=123))

    def DescribeTaskStatus(self, request: SimpleNamespace) -> SimpleNamespace:  # noqa: N802
        self.describe_task_ids.append(request.TaskId)
        return SimpleNamespace(Data=self.statuses.pop(0))


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"fake audio")
    return audio_path


@pytest.mark.asyncio
async def test_transcribe_uploads_creates_polls_and_cleans_up(
    sample_audio: Path,
) -> None:
    cos = FakeCosStorage()
    client = FakeAsrClient(
        [
            SimpleNamespace(Status=0),
            SimpleNamespace(
                Status=2,
                AudioDuration=1.0,
                ResultDetail=[
                    SimpleNamespace(
                        FinalSentence="hello",
                        StartMs=0,
                        EndMs=1000,
                        SpeakerId=0,
                    )
                ],
            ),
        ]
    )
    transcriber = TencentCloudTranscriber(
        client=client,
        cos_storage=cos,
        poll_interval_seconds=0,
    )

    result = await transcriber.transcribe(sample_audio, TranscribeOptions())

    assert result.text == "hello"
    assert result.provider == "tencent_cloud"
    assert cos.uploaded == [sample_audio]
    assert cos.deleted == ["podlator/audio.mp3"]
    assert client.create_requests[0].Url == "https://cos.example.com/audio.mp3"
    assert client.describe_task_ids == [123, 123]


@pytest.mark.asyncio
async def test_transcribe_raises_non_retryable_on_failed_task(
    sample_audio: Path,
) -> None:
    cos = FakeCosStorage()
    client = FakeAsrClient(
        [SimpleNamespace(Status=3, ErrorMsg="audio url cannot be downloaded")]
    )
    transcriber = TencentCloudTranscriber(
        client=client,
        cos_storage=cos,
        poll_interval_seconds=0,
    )

    with pytest.raises(ProviderError) as exc_info:
        await transcriber.transcribe(sample_audio, TranscribeOptions())

    assert exc_info.value.retryable is False
    assert "audio url cannot be downloaded" in str(exc_info.value)
    assert cos.deleted == ["podlator/audio.mp3"]


@pytest.mark.asyncio
async def test_transcribe_times_out_and_cleans_up(sample_audio: Path) -> None:
    cos = FakeCosStorage()
    client = FakeAsrClient([SimpleNamespace(Status=0), SimpleNamespace(Status=0)])
    transcriber = TencentCloudTranscriber(
        client=client,
        cos_storage=cos,
        poll_interval_seconds=0,
        timeout_seconds=0,
    )

    with pytest.raises(ProviderError) as exc_info:
        await transcriber.transcribe(sample_audio, TranscribeOptions())

    assert exc_info.value.retryable is True
    assert "timed out" in str(exc_info.value)
    assert cos.deleted == ["podlator/audio.mp3"]
