# AI Usage Guide

This project provides a CLI interface for speech-to-text.

Use it when another project needs transcription but should not directly depend
on Tencent Cloud ASR or COS SDK details.

## Command

```bash
uv run speech-transcriber transcribe AUDIO_PATH --provider tencent_cloud --output json
```

For plain text:

```bash
uv run speech-transcriber transcribe AUDIO_PATH --output text
```

To write the result to a file instead of printing the transcript to stdout:

```bash
uv run speech-transcriber transcribe AUDIO_PATH \
  --provider tencent_cloud \
  --output json \
  --output-file /path/to/transcript.json
```

When `--output-file` points to a directory, or to a path without a file
extension, the CLI creates that directory and writes an auto-named file:

```bash
uv run speech-transcriber transcribe AUDIO_PATH \
  --provider tencent_cloud \
  --output text \
  --output-file /path/to/transcripts
```

Auto-generated filenames use:

```text
YYYY-MM-DD-HH:MM:SS-original-audio-filename.json
YYYY-MM-DD-HH:MM:SS-original-audio-filename.txt
```

For example: `2026-05-27-15:04:05-audio.mp3.json`.

## Tencent Cloud ASR Modes and Options

Use `--asr-mode` for the common Tencent Cloud billing/feature paths:

```bash
uv run speech-transcriber transcribe AUDIO_PATH --asr-mode standard --output json
uv run speech-transcriber transcribe AUDIO_PATH --asr-mode large --output json
uv run speech-transcriber transcribe AUDIO_PATH --asr-mode diarization --output json
```

Modes:

- `standard`: uses `16k_zh`, the regular Chinese Mandarin engine.
- `large`: uses `16k_zh_large`, the large Chinese dialect/English engine.
- `diarization`: enables normal speaker separation with
  `SpeakerDiarization=1` and `SpeakerNumber=0`.
- `role`: role voiceprint separation. This also requires the
  `--speaker-role-*` arguments below.

You can override mode defaults with Tencent Cloud request options:

```bash
uv run speech-transcriber transcribe AUDIO_PATH \
  --provider tencent_cloud \
  --engine-model-type 16k_zh_en \
  --res-text-format 3 \
  --hotword-list "特努斯|11,Apple|8" \
  --filter-modal 1 \
  --output json
```

Supported Tencent Cloud option flags:

```text
--engine-model-type, --channel-num, --res-text-format
--speaker-diarization, --speaker-number
--hotword-id, --hotword-list, --customization-id
--emotion-recognition, --emotional-energy
--convert-num-mode, --filter-dirty, --filter-punc, --filter-modal
--sentence-max-length, --keyword-lib-id, --replace-text-id
```

Important Tencent Cloud constraints from the 2026-02-06 API document:

- `16k_zh`, `8k_zh`, and `8k_en` are regular engines; `16k_zh_large`,
  `16k_zh_en`, `16k_multi_lang`, `16k_en_large`, and `8k_zh_large` are large
  model engines.
- Normal speaker separation uses `SpeakerDiarization=1`. Role voiceprint
  separation uses `SpeakerDiarization=3` plus `SpeakerRoles`.
- Role voiceprint separation only supports `16k_zh_en`; this provider forces
  that engine when `--speaker-role-*` is used.
- `ResTextFormat=4`, `ResTextFormat=5`, emotion recognition, and role
  voiceprint separation are value-added features that may consume add-on
  packages or trigger postpaid billing.
- `hotword-list` takes precedence over `hotword-id` when both are supplied.
- For COS URL submission, Tencent Cloud documents a maximum audio duration of
  5 hours and file size of 1GB.

## Tencent Cloud Speaker Role Separation

Speaker role separation is optional. Omit `--speaker-role-*` arguments to keep
the normal transcription behavior.

To identify one target speaker in a multi-speaker recording, pass a stable role
name and a clean voice sample for that speaker:

```bash
uv run speech-transcriber transcribe AUDIO_PATH \
  --provider tencent_cloud \
  --output json \
  --speaker-role-name TARGET \
  --speaker-role-audio /path/to/target-speaker.wav
```

If the voice sample is already available as a URL Tencent Cloud can download:

```bash
uv run speech-transcriber transcribe AUDIO_PATH \
  --provider tencent_cloud \
  --output json \
  --speaker-role-name TARGET \
  --speaker-role-audio-url "https://example.com/target-speaker.wav"
```

Matched target-speaker segments return `speaker: "TARGET"`. Other speaker
segments may still return generic labels such as `SPEAKER_0` or `SPEAKER_1`.
Consumer projects can isolate the target speaker by filtering:

```python
target_text = " ".join(
    segment["text"]
    for segment in result["segments"]
    if segment.get("speaker") == "TARGET"
)
```

Tencent Cloud constraints handled by this CLI:

- Role separation uses Tencent Cloud `SpeakerDiarization=3` and `SpeakerRoles`
  inside the provider implementation.
- The request engine is automatically switched to `16k_zh_en`, which Tencent
  Cloud requires for role separation.
- Tencent Cloud currently accepts only one speaker role voice sample for this
  API.
- Local role voice samples are uploaded to the configured temporary COS bucket
  and cleaned up according to `TENCENT_COS_DELETE_AFTER_TRANSCRIBE`.
- Use clean single-speaker role audio, preferably within 30 seconds and no more
  than 45 seconds.

The JSON output is a `TranscriptResult`:

```json
{
  "text": "...",
  "segments": [
    {
      "start": 0.0,
      "end": 1.0,
      "text": "...",
      "speaker": "SPEAKER_0",
      "confidence": null
    }
  ],
  "provider": "tencent_cloud",
  "duration_seconds": 1.0,
  "has_diarization": true,
  "metadata": {}
}
```

## Integration Pattern

From another program, call the CLI as a subprocess and parse stdout JSON.

Do not call Tencent Cloud directly from consumer projects. Tencent ASR and COS
logic belongs inside this project.

Python example:

```python
import json
import subprocess

completed = subprocess.run(
    [
        "uv",
        "run",
        "speech-transcriber",
        "transcribe",
        "/path/to/audio.mp3",
        "--provider",
        "tencent_cloud",
        "--output",
        "json",
    ],
    cwd="/Users/yangzhuoran/program/speech-transcriber",
    check=True,
    capture_output=True,
    text=True,
)
result = json.loads(completed.stdout)
print(result["text"])
```

Node.js example:

```js
import { spawnSync } from "node:child_process";

const child = spawnSync(
  "uv",
  [
    "run",
    "speech-transcriber",
    "transcribe",
    "/path/to/audio.mp3",
    "--provider",
    "tencent_cloud",
    "--output",
    "json",
  ],
  {
    cwd: "/Users/yangzhuoran/program/speech-transcriber",
    encoding: "utf8",
  },
);

if (child.status !== 0) {
  throw new Error(child.stderr);
}

const result = JSON.parse(child.stdout);
console.log(result.text);
```

## Configuration

Copy `.env.example` to `.env` and fill:

- `TENCENT_SECRET_ID`
- `TENCENT_SECRET_KEY`
- `TENCENT_COS_BUCKET`
- `TENCENT_COS_REGION`
- `TENCENT_COS_SECRET_ID`
- `TENCENT_COS_SECRET_KEY`

The default smoke audio path is:

```text
/Users/yangzhuoran/program/podlator/data/audio/0f150b76-3af6-44c2-a1ea-97c64c69f55e/audio.mp3
```

## Provider Contract

All providers implement:

```python
async def transcribe(audio_path: Path, options: TranscribeOptions) -> TranscriptResult:
    ...
```

Future local providers should return the same `TranscriptResult` model.

## Tests

Run normal tests:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Run real Tencent smoke test only when credentials are configured:

```bash
RUN_SMOKE=1 uv run pytest tests/smoke/test_tencent_cli_real.py -v
```
