# Speech Transcriber

一个命令行语音转文字工具，对外提供稳定的 CLI 调用方式，内部通过 Provider 抽象隔离具体识别服务。

当前第一版 Provider 是腾讯云录音文件识别：本地音频会先临时上传到腾讯 COS，生成预签名 URL 后提交给腾讯云 ASR，识别完成后清理 COS 临时文件。后续如果要切换本地 Whisper / MLX 模型，只需要实现同一个 `Transcriber` 接口，CLI 输出结构保持不变。

## 安装

```bash
uv sync
cp .env.example .env
```

然后在 `.env` 里填写腾讯云 ASR 和 COS 配置。

## 使用方式

输出 JSON：

```bash
uv run speech-transcriber transcribe /path/to/audio.mp3 --provider tencent_cloud --output json
```

只输出纯文本：

```bash
uv run speech-transcriber transcribe ./audio/audio.mp3 --output text
```

使用 Podlator 里已有的测试音频：

```bash
uv run speech-transcriber transcribe \
  /Users/yangzhuoran/program/podlator/data/audio/0f150b76-3af6-44c2-a1ea-97c64c69f55e/audio.mp3 \
  --provider tencent_cloud \
  --output json
```

JSON 输出结构是统一的 `TranscriptResult`：

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

## 测试

常规测试不会调用真实腾讯云，也不会使用真实业务音频；它们用 fake COS / fake ASR client 和临时音频文件验证逻辑。

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

真实腾讯云 smoke 测试需要显式打开：

```bash
RUN_SMOKE=1 uv run pytest tests/smoke/test_tencent_cli_real.py -v
```

这个 smoke 测试默认使用：

```text
/Users/yangzhuoran/program/podlator/data/audio/0f150b76-3af6-44c2-a1ea-97c64c69f55e/audio.mp3
```

如果没有设置 `RUN_SMOKE=1`，或者腾讯云配置不完整，smoke 测试会跳过。

## 文档

其他项目或 AI 编码助手要集成这个工具时，优先读取：

- [docs/AI_USAGE.md](docs/AI_USAGE.md)
- [docs/PROVIDER_INTERFACE.md](docs/PROVIDER_INTERFACE.md)

约定：消费方项目通过 CLI 调用本工具并解析 stdout JSON，不要直接在消费方项目里调用腾讯云 ASR / COS SDK。
