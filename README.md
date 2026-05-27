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

写入指定文件：

```bash
uv run speech-transcriber transcribe ./audio/audio.mp3 \
  --output json \
  --output-file ./transcripts/audio.json
```

只指定输出目录时，CLI 会自动创建目录并生成文件名：

```bash
uv run speech-transcriber transcribe ./audio/audio.mp3 \
  --output text \
  --output-file ./transcripts
```

自动文件名格式为：

```text
YYYY-MM-DD-HH:MM:SS-原输入音频文件名.json
YYYY-MM-DD-HH:MM:SS-原输入音频文件名.txt
```

例如 `2026-05-27-15:04:05-audio.mp3.json`。

不开启角色分离时，不传任何 `--speaker-role-*` 参数即可。开启腾讯云角色分离时，给目标说话人的角色名和一段干净声纹样本：

```bash
uv run speech-transcriber transcribe ./audio/podcast.mp3 \
  --provider tencent_cloud \
  --output json \
  --output-file ./output
  --speaker-role-name TARGET \
  --speaker-role-audio ./audio/target-speaker.wav
```

如果声纹样本已经有腾讯云可下载的 URL，也可以直接传 URL：

```bash
uv run speech-transcriber transcribe "./audio/短-爱否播客且看特努斯能否 Make Apple Great Again.m4a" \
    --provider tencent_cloud \
    --output json \
    --output-file ./output \
    --speaker-role-name TARGET \
    --speaker-role-audio-url "https://person-1330315023.cos.ap-beijing.myqcloud.com/podlator/asr-audio/27%E7%A7%92%E7%9B%AE%E6%A0%87%E8%A7%92%E8%89%B2%E9%9F%B3%E9%A2%91.m4a"
```


角色分离结果仍然输出统一的 `TranscriptResult`。匹配成功后，对应片段的 `speaker` 会是你传入的角色名，例如 `TARGET`；未匹配到目标角色的片段仍可能是 `SPEAKER_0`、`SPEAKER_1` 等普通话者标签。只提取目标角色文本时，可以按 `segments[].speaker == "TARGET"` 过滤。

腾讯云角色分离限制：

- 该能力会在内部使用腾讯云 `SpeakerDiarization=3` 和 `SpeakerRoles`。
- 腾讯云只支持 `16k_zh_en` 引擎，CLI 开启角色分离后会自动切换到这个引擎。
- 当前腾讯云接口只支持传入一组声纹信息。
- 声纹样本建议使用目标说话人的纯净人声，建议 30 秒内，最长不超过 45 秒。
- 本地声纹样本会临时上传到配置的 COS，任务结束后按 `TENCENT_COS_DELETE_AFTER_TRANSCRIBE` 清理。

使用 Podlator 里已有的测试音频：

```bash
uv run speech-transcriber transcribe \
  /Users/yangzhuoran/program/podlator/data/audio/0f150b76-3af6-44c2-a1ea-97c64c69f55e/audio.mp3 \
  --provider tencent_cloud \
  --output json
```

```bash
uv run speech-transcriber transcribe \
  /Users/yangzhuoran/program/speech-transcriber/audio/彭林5.26直播15分钟.m4a \
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
