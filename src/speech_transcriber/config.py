"""Application settings loaded from environment and .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the CLI and providers."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    default_provider: str = "tencent_cloud"

    tencent_secret_id: str = ""
    tencent_secret_key: str = ""
    tencent_asr_region: str = "ap-shanghai"
    tencent_asr_engine_model_type: str = "16k_zh_large"
    tencent_asr_res_text_format: int = 2
    tencent_asr_speaker_diarization: int = 0
    tencent_asr_poll_interval_seconds: float = 3.0
    tencent_asr_timeout_seconds: float = 10800.0

    tencent_cos_bucket: str = ""
    tencent_cos_region: str = ""
    tencent_cos_secret_id: str = ""
    tencent_cos_secret_key: str = ""
    tencent_cos_token: str = ""
    tencent_cos_prefix: str = "speech-transcriber/audio"
    tencent_cos_scheme: str = "https"
    tencent_cos_presigned_expires_seconds: int = 21600
    tencent_cos_delete_after_transcribe: bool = True

    smoke_audio_path: Path = Field(
        default=Path(
            "/Users/yangzhuoran/program/podlator/data/audio/"
            "0f150b76-3af6-44c2-a1ea-97c64c69f55e/audio.mp3"
        )
    )
