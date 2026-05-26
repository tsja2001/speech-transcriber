"""Real Tencent Cloud smoke test gated by RUN_SMOKE=1."""

from __future__ import annotations

import os

import pytest

from speech_transcriber.config import Settings
from speech_transcriber.models import TranscribeOptions
from speech_transcriber.providers.factory import get_transcriber


@pytest.mark.smoke
@pytest.mark.asyncio
async def test_tencent_transcribe_real_audio() -> None:
    """Call real Tencent ASR using the configured smoke audio file."""
    if os.getenv("RUN_SMOKE") != "1":
        pytest.skip("Set RUN_SMOKE=1 to call real Tencent Cloud services")

    settings = Settings()
    required = {
        "TENCENT_SECRET_ID": settings.tencent_secret_id,
        "TENCENT_SECRET_KEY": settings.tencent_secret_key,
        "TENCENT_COS_BUCKET": settings.tencent_cos_bucket,
        "TENCENT_COS_REGION": settings.tencent_cos_region,
        "TENCENT_COS_SECRET_ID": settings.tencent_cos_secret_id,
        "TENCENT_COS_SECRET_KEY": settings.tencent_cos_secret_key,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        pytest.skip(f"Missing Tencent configuration: {', '.join(missing)}")
    if not settings.smoke_audio_path.exists():
        pytest.skip(f"Smoke audio not found: {settings.smoke_audio_path}")

    transcriber = get_transcriber(settings, "tencent_cloud")
    result = await transcriber.transcribe(
        settings.smoke_audio_path,
        TranscribeOptions(provider="tencent_cloud"),
    )

    assert result.provider == "tencent_cloud"
    assert result.text.strip()
    assert result.segments
