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
