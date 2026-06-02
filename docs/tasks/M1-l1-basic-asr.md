# M1 — L1 基础语音转写（WhisperX）

> 目标：本地把一条音频转成与腾讯云**同构**的 `TranscriptResult`（带词级时间戳聚合的段落），主 CLI `--provider local_whisperx` 可用。
> 不做说话人分离（M2）与声纹（M3）。
> 执行前先读 `EXECUTION-FRAMEWORK.md`，并确认 M0 完成报告为 ✅。

## 前置条件
- [ ] M0 ✅（依赖、镜像、warmup、夹具、骨架就绪）
- [ ] `tests/fixtures/audio/l1_short_zh.wav` 存在（M0 `clip` 生成）

## 预检
```bash
uv run speech-transcriber-local doctor          # 退出码 0
ls tests/fixtures/audio/l1_short_zh.wav
```

---

## Phase 1: 音频解码（audio.py）

### 1.1 实现 `decode_to_wav` / `probe`
- `decode_to_wav`：用 ffmpeg 把任意输入转 16k 单声道 `pcm_s16le` wav。`out_path=None` 时写到系统临时目录并返回路径。命令：
  `ffmpeg -y -i <in> -ac 1 -ar 16000 -c:a pcm_s16le <out>`，`subprocess.run(check=True, capture_output=True)`。
- 文件不存在 → `ProviderError("local_whisperx", ..., retryable=False)`。
- ffmpeg 非零退出 → `ProviderError(..., retryable=False)`，message 含 stderr 末尾。
- `probe`：用 `soundfile.info` 返回 `{"duration": float, "sample_rate": int, "channels": int}`。

### 1.2 `devcli decode`
`decode <audio> [--out PATH] [--pretty]`：解码并打印 `probe` 结果 JSON。

### Phase 1 验证
```bash
uv run speech-transcriber-local decode "audio/27秒目标角色音频.m4a" --pretty
# 期望 JSON: duration≈27.2, sample_rate=16000, channels=1
```

### Phase 1 单元测试 `tests/unit/providers/local/test_audio.py`
- `test_decode_missing_file_raises_provider_error`：不存在路径 → `ProviderError`、`retryable is False`。
- `test_decode_builds_expected_ffmpeg_args`（monkeypatch `subprocess.run`）：断言 args 含 `-ac 1 -ar 16000 -c:a pcm_s16le`。
- `test_probe_returns_mono_16k`（用一个生成的 0.5s 静音 wav fixture，由测试内 `soundfile.write` 造）：channels==1、sample_rate==16000。

---

## Phase 2: 转写 + 词级对齐（asr.py + parsing.py）

### 2.1 `asr.transcribe_words`
lazy import `whisperx`。流程：
1. `model = whisperx.load_model(model, device="cpu", compute_type=compute_type, language=language)`。
2. `audio = whisperx.load_audio(str(wav_path))`；`result = model.transcribe(audio, batch_size=batch_size)`。
3. 对齐：`align_model, meta = whisperx.load_align_model(language_code=result["language"], device=align_device)`；`aligned = whisperx.align(result["segments"], align_model, meta, audio, align_device, return_char_alignments=False)`。
4. 返回 `aligned["segments"]`（每段含 `start/end/text/words`），并把检测到的 `language` 透传（放进每段或单独返回元信息）。
- `align_device`：mps 可用则 mps，否则 cpu（对齐模型是 torch，可吃 mps）。
- 任意模型异常 → `ProviderError(..., retryable=True)`。

### 2.2 `parsing.words_to_segments` / `build_result`
- `words_to_segments(words_segments)`：把 whisperx 段 → `list[TranscriptSegment]`（`start/end/text`，speaker 暂 None，confidence 用 word score 平均或 None）。空文本段跳过。**纯函数，吃 dict 列表，不碰模型**（便于单测）。
- `build_result(segments, duration, has_diar, meta)`：拼 `text=" ".join(seg.text)`，返回 `TranscriptResult(provider="local_whisperx", ...)`。

### 2.3 `devcli asr`
`asr <audio> [--model] [--device] [--language] [--pretty]`：跑 decode→transcribe_words→words_to_segments，输出 `{language, segment_count, word_count, segments:[...]}`。

### Phase 2 验证
```bash
uv run speech-transcriber-local asr tests/fixtures/audio/l1_short_zh.wav --pretty
# 期望：language=="zh"，segment_count>0，segments[].text 非空、start<end
```

### Phase 2 单元测试 `tests/unit/providers/local/test_parsing.py`
用**伪造的 whisperx 输出 dict**（不下载模型）：
- `test_words_to_segments_basic`：给 2 段 dict → 2 个 `TranscriptSegment`，文本/时间正确，speaker is None。
- `test_words_to_segments_skips_empty_text`：空/纯空白文本段被跳过。
- `test_words_to_segments_handles_missing_word_scores`：words 无 score → confidence is None，不抛异常。
- `test_build_result_joins_text`：`text` 等于各段文本空格拼接，`provider=="local_whisperx"`、`has_diarization is False`。

---

## Phase 3: 编排 + factory 接入（transcriber.py）

### 3.1 `LocalWhisperXTranscriber.transcribe`（仅 L1）
```python
async def transcribe(self, audio_path, options) -> TranscriptResult:
    # 1. 校验存在（asyncio.to_thread）
    # 2. wav = await asyncio.to_thread(decode_to_wav, audio_path)
    # 3. info = probe(wav)
    # 4. words = await asyncio.to_thread(transcribe_words, wav, ...config...)
    # 5. segments = words_to_segments(words)
    # 6. return build_result(segments, duration=info["duration"], has_diar=False, meta={...})
```
- 模型推理是阻塞调用，全部包 `asyncio.to_thread`（与腾讯云 provider 风格一致）。
- M2/M3 会在第 5 步后插入分离与声纹；本里程碑只到 L1。

### 3.2 factory 用 Settings 字段构造（替换 M0 stub 构造）
把 `local_whisper_model/local_device/local_compute_type/local_batch_size/local_language` 传入。

### Phase 3 验证（主 CLI 端到端，弱断言）
```bash
uv run speech-transcriber transcribe tests/fixtures/audio/l1_short_zh.wav \
  --provider local_whisperx --output json | uv run python -c \
  "import sys,json; r=json.load(sys.stdin); assert r['provider']=='local_whisperx'; \
   assert r['text'].strip(); assert r['segments']; assert r['has_diarization'] is False; print('L1 OK', len(r['segments']),'segs')"
```

---

## Phase 4: Smoke 测试（gated）

### 4.1 `tests/smoke/test_local_l1_real.py`
```python
@pytest.mark.smoke_local
@pytest.mark.skipif(os.environ.get("RUN_SMOKE_LOCAL") != "1", reason="gated")
async def test_local_l1_transcribes_short_clip():
    # 跑 fixtures/audio/l1_short_zh.wav
    # 断言：result.text 非空；len(segments)>0；每段 start<=end；
    #       result.provider=="local_whisperx"；result.has_diarization is False；
    #       检测语言为 zh（从 metadata 读）
```
- 单条应 < 2 分钟（60–90s 音频，CPU int8）。超时则在报告记录实际耗时并建议降档。

### Phase 4 验证
```bash
RUN_SMOKE_LOCAL=1 uv run pytest tests/smoke/test_local_l1_real.py -v
```

---

## 最终验证
```bash
uv run pytest
uv run ruff check .
uv run mypy src
RUN_SMOKE_LOCAL=1 uv run pytest tests/smoke/test_local_l1_real.py -v
```

## Git 提交
```bash
git add -A && git commit -m "M1: 本地 WhisperX L1 基础转写（解码+转写+对齐+编排）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## DoD
- [ ] `devcli decode` / `asr` 可用并通过 Phase 验证
- [ ] 主 CLI `--provider local_whisperx` 输出同构 `TranscriptResult`
- [ ] parsing 纯函数单测齐全（含空文本、缺 score 失败场景）
- [ ] L1 smoke gated 通过，记录真实耗时
- [ ] 三件套绿，无回归
- [ ] 完成报告含「模块 CLI 自测」与真实耗时

## ⚠️ 不要做
- 不做分离/声纹（speaker 恒为 None，has_diarization=False）。
- 不改 `TranscriptResult` / `TranscriptSegment` 模型字段。
- 不把 whisperx 写进模块顶层 import。
