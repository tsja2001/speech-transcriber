# Provider Interface

Provider implementations live under `src/speech_transcriber/providers/`.

Each provider implements `Transcriber` from `providers/base.py`:

```python
async def transcribe(
    audio_path: Path,
    options: TranscribeOptions,
) -> TranscriptResult:
    ...
```

Consumers should depend on CLI output, not provider internals.

To add a local model later:

1. Create `providers/local_whisper.py`.
2. Implement `Transcriber`.
3. Register it in `providers/factory.py`.
4. Add unit tests with fake model output.
5. Keep CLI output schema unchanged.
