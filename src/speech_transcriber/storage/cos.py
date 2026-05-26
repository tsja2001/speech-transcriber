"""Tencent COS temporary audio storage."""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from uuid import uuid4

from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import-untyped]


class TencentCosAudioStorage:
    """Upload local audio to COS and create a presigned GET URL for ASR."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        secret_id: str,
        secret_key: str,
        prefix: str = "speech-transcriber/audio",
        token: str = "",
        scheme: str = "https",
        presigned_expires_seconds: int = 21600,
        delete_after_transcribe: bool = True,
        client: CosS3Client | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.presigned_expires_seconds = presigned_expires_seconds
        self.delete_after_transcribe = delete_after_transcribe
        if client is not None:
            self._client = client
            return
        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key,
            Token=token or None,
            Scheme=scheme,
        )
        self._client = CosS3Client(config)

    async def upload_and_presign(self, audio_path: Path) -> tuple[str, str]:
        """Upload audio and return `(object_key, presigned_url)`."""
        object_key = self._build_object_key(audio_path)
        content_type = (
            mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
        )
        await asyncio.to_thread(
            self._client.upload_file,
            Bucket=self.bucket,
            Key=object_key,
            LocalFilePath=str(audio_path),
            ContentType=content_type,
        )
        presigned_url = await asyncio.to_thread(
            self._client.get_presigned_url,
            Bucket=self.bucket,
            Key=object_key,
            Method="GET",
            Expired=self.presigned_expires_seconds,
        )
        return object_key, str(presigned_url)

    async def delete(self, object_key: str) -> None:
        """Delete a temporary COS object."""
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self.bucket,
            Key=object_key,
        )

    def _build_object_key(self, audio_path: Path) -> str:
        namespace = uuid4().hex
        filename = audio_path.name or "audio"
        if not self.prefix:
            return f"{namespace}/{filename}"
        return f"{self.prefix}/{namespace}/{filename}"
