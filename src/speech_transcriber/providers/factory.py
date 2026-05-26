"""Provider factory."""

from __future__ import annotations

from tencentcloud.asr.v20190614 import asr_client  # type: ignore[import-untyped]
from tencentcloud.common import credential  # type: ignore[import-untyped]

from speech_transcriber.config import Settings
from speech_transcriber.errors import ConfigError
from speech_transcriber.providers.base import Transcriber
from speech_transcriber.providers.tencent_cloud import TencentCloudTranscriber
from speech_transcriber.storage.cos import TencentCosAudioStorage


def get_transcriber(settings: Settings, provider: str | None = None) -> Transcriber:
    """Return the configured transcriber implementation."""
    provider_name = provider or settings.default_provider
    if provider_name != "tencent_cloud":
        raise ConfigError(f"Unsupported provider: {provider_name}")

    cred = credential.Credential(
        settings.tencent_secret_id,
        settings.tencent_secret_key,
    )
    client = asr_client.AsrClient(cred, settings.tencent_asr_region)
    cos_storage = TencentCosAudioStorage(
        bucket=settings.tencent_cos_bucket,
        region=settings.tencent_cos_region,
        secret_id=settings.tencent_cos_secret_id,
        secret_key=settings.tencent_cos_secret_key,
        token=settings.tencent_cos_token,
        prefix=settings.tencent_cos_prefix,
        scheme=settings.tencent_cos_scheme,
        presigned_expires_seconds=settings.tencent_cos_presigned_expires_seconds,
        delete_after_transcribe=settings.tencent_cos_delete_after_transcribe,
    )
    return TencentCloudTranscriber(
        client=client,
        cos_storage=cos_storage,
        engine_model_type=settings.tencent_asr_engine_model_type,
        res_text_format=settings.tencent_asr_res_text_format,
        speaker_diarization=settings.tencent_asr_speaker_diarization,
        poll_interval_seconds=settings.tencent_asr_poll_interval_seconds,
        timeout_seconds=settings.tencent_asr_timeout_seconds,
    )
