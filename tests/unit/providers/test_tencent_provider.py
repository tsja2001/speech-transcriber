"""Tests for TencentCloudTranscriber."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from speech_transcriber.errors import ProviderError
from speech_transcriber.models import SpeakerRole, TranscribeOptions
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
async def test_transcribe_maps_explicit_tencent_asr_options(
    sample_audio: Path,
) -> None:
    cos = FakeCosStorage()
    client = FakeAsrClient(
        [
            SimpleNamespace(
                Status=2,
                AudioDuration=1.0,
                ResultDetail=[
                    SimpleNamespace(
                        FinalSentence="hello",
                        StartMs=0,
                        EndMs=1000,
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

    await transcriber.transcribe(
        sample_audio,
        TranscribeOptions(
            provider_options={
                "engine_model_type": "16k_zh",
                "channel_num": 1,
                "res_text_format": 3,
                "speaker_diarization": 1,
                "speaker_number": 0,
                "hotword_list": "特努斯|11,Apple|8",
                "filter_modal": 1,
                "sentence_max_length": 20,
            },
        ),
    )

    request = client.create_requests[0]
    assert request.EngineModelType == "16k_zh"
    assert request.ChannelNum == 1
    assert request.ResTextFormat == 3
    assert request.SpeakerDiarization == 1
    assert request.SpeakerNumber == 0
    assert request.HotwordList == "特努斯|11,Apple|8"
    assert request.FilterModal == 1
    assert request.SentenceMaxLength == 20


@pytest.mark.asyncio
async def test_transcribe_asr_mode_diarization_enables_speaker_separation(
    sample_audio: Path,
) -> None:
    cos = FakeCosStorage()
    client = FakeAsrClient(
        [
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

    await transcriber.transcribe(
        sample_audio,
        TranscribeOptions(provider_options={"asr_mode": "diarization"}),
    )

    request = client.create_requests[0]
    assert request.SpeakerDiarization == 1
    assert request.SpeakerNumber == 0


@pytest.mark.asyncio
async def test_transcribe_uploads_role_audio_and_creates_role_separation_task(
    sample_audio: Path,
    tmp_path: Path,
) -> None:
    role_audio = tmp_path / "host.wav"
    role_audio.write_bytes(b"voice")
    cos = FakeCosStorage()
    client = FakeAsrClient(
        [
            SimpleNamespace(
                Status=2,
                AudioDuration=1.0,
                ResultDetail=[
                    SimpleNamespace(
                        FinalSentence="hello",
                        StartMs=0,
                        EndMs=1000,
                        SpeakerId="HOST",
                    )
                ],
            ),
        ]
    )
    transcriber = TencentCloudTranscriber(
        client=client,
        cos_storage=cos,
        engine_model_type="16k_zh_large",
        poll_interval_seconds=0,
    )

    result = await transcriber.transcribe(
        sample_audio,
        TranscribeOptions(
            speaker_role=SpeakerRole(name="HOST", audio_path=role_audio),
        ),
    )

    request = client.create_requests[0]
    assert request.EngineModelType == "16k_zh_en"
    assert request.SpeakerDiarization == 3
    assert request.SpeakerRoles[0].RoleName == "HOST"
    assert request.SpeakerRoles[0].RoleAudioUrl == "https://cos.example.com/audio.mp3"
    assert cos.uploaded == [sample_audio, role_audio]
    assert cos.deleted == ["podlator/audio.mp3", "podlator/audio.mp3"]
    assert result.has_diarization is True
    assert result.segments[0].speaker == "HOST"
    assert result.metadata["speaker_role"]["name"] == "HOST"


@pytest.mark.asyncio
async def test_transcribe_uses_role_audio_url_without_uploading_role_audio(
    sample_audio: Path,
) -> None:
    cos = FakeCosStorage()
    client = FakeAsrClient(
        [
            SimpleNamespace(
                Status=2,
                AudioDuration=1.0,
                ResultDetail=[
                    SimpleNamespace(
                        FinalSentence="hello",
                        StartMs=0,
                        EndMs=1000,
                        SpeakerId="HOST",
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

    await transcriber.transcribe(
        sample_audio,
        TranscribeOptions(
            speaker_role=SpeakerRole(
                name="HOST",
                audio_url="https://example.com/host.wav",
            ),
        ),
    )

    request = client.create_requests[0]
    assert request.SpeakerRoles[0].RoleAudioUrl == "https://example.com/host.wav"
    assert cos.uploaded == [sample_audio]


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
