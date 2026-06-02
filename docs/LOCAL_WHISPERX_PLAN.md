# 本地语音转写方案：WhisperX + pyannote

> 在现有腾讯云 Provider 之外，新增一个**本地离线** Provider。
> 复用现有 `Transcriber` 接口与 `TranscriptResult` 输出 schema，CLI 下游无感。
> 目标硬件：Mac mini M4 / 16G，原生运行（不进容器，见 §1）。

## 0. 目标与范围

分三层递进，对应同一个 Provider 的能力开关：

| 层 | 能力 | 落在输出模型的哪里 |
|---|---|---|
| L1 | 基础语音转文字（ASR + 词级时间戳） | `segments[].text/start/end`、`text` |
| L2 | 说话人分离（diarization） | `segments[].speaker = "SPEAKER_00"`、`has_diarization=True` |
| L3 | 指定说话人声纹识别 | 命中段 `segments[].speaker = <role.name>`、`metadata.speaker_role` |

非目标：不引入 HTTP/FastAPI（遵守 AGENTS.md，保持 CLI-only）；不改 CLI 输出 schema；不动腾讯云路径行为。

---

## 1. 关键技术现实（必须先知道）

**WhisperX 的转写底层是 faster-whisper / CTranslate2，而 CTranslate2 在 Apple Silicon 上只支持 CPU**（无 Metal/MPS）。所以：

- L1 转写在 M4 上走 **CPU**，用 `compute_type=int8` 量化提速 + WhisperX 的 VAD 切片 + batched 推理来压时间。
- L2 的 pyannote 基于 PyTorch，`device` 可尝试 `mps`（Apple GPU），部分算子可能回退 CPU，但 diarization 通常不是瓶颈。
- **性能预期**（保守，`large-v3` + int8 + batched）：1 小时音频大约 **0.5–1.5× 时长**完成；`audio/彭林5.26直播2小时.m4a` 这种属于压力场景，靠 VAD 切片可分段并行。要更快可降到 `medium` / `distil-large-v3`。
- **退路（性能不达标时）**：把 L1 转写层替换为 **mlx-whisper**（吃 M4 GPU/ANE，明显快），L2 仍用 pyannote、L3 不变。模块边界已按这个退路设计（见 §3），切换只动 `asr.py`。

> 结论：本方案的瓶颈只在“转写速度”，且有明确优化项与退路；功能可行性没有疑点。

---

## 2. 依赖与环境隔离

本地依赖很重（torch 全家桶 + pyannote + ctranslate2），**不能污染核心包**——否则只用腾讯云的人也被迫装几个 GB。用 optional extra 隔离：

```toml
# pyproject.toml
[project.optional-dependencies]
local = [
    "whisperx>=3.1",
    "torch>=2.2",
    "torchaudio>=2.2",
    "pyannote.audio>=3.1",
    "ctranslate2>=4.4",
    "soundfile>=0.12",
]
```

安装：`uv sync --extra local`（核心用户仍 `uv sync`）。

mypy strict 对无 stub 的科学库放行（不降低核心代码的严格度）：

```toml
[[tool.mypy.overrides]]
module = ["whisperx.*", "pyannote.*", "torch.*", "torchaudio.*", "soundfile.*"]
ignore_missing_imports = true
```

系统侧前置（uv 装不了，需线下做一次）：

- **ffmpeg**：解码 `.m4a/.mp3` 必需。`brew install ffmpeg` 或用 mise。
- **HuggingFace token**：pyannote 是 gated 模型，需注册 HF、在网页接受
  `pyannote/segmentation-3.0` 和 `pyannote/speaker-diarization-3.1` 的使用条款，
  生成 read token 填入 `.env`。
- **模型缓存**：首次运行自动下载数 GB 模型到 HF 缓存目录；可用 `local_model_cache_dir` 指定位置，避免反复下载。

---

## 3. 代码结构

新增一个子包（本地三层逻辑比腾讯云复杂，平铺会乱），不动现有文件的对外行为：

```
src/speech_transcriber/providers/local/
    __init__.py
    transcriber.py     # LocalWhisperXTranscriber：实现 Transcriber，编排 L1→L2→L3
    audio.py           # ffmpeg 解码/重采样到 16k 单声道
    asr.py             # L1：WhisperX 转写 + 词级对齐（退路替换点：mlx-whisper）
    diarization.py     # L2：pyannote 分离 + 与 ASR 片段按时间对齐
    voiceprint.py      # L3：enrollment embedding + 余弦匹配 + 改名
    parsing.py         # 原始结果 → TranscriptResult（纯函数，可单测）
```

**重依赖一律延迟导入**：`import whisperx/torch/pyannote` 放在 `local/` 模块内部，且 `factory.py` 只在 `provider == "local_whisperx"` 分支才 import `local.transcriber`。这样腾讯云路径不会被迫加载 torch。

改动点（最小化）：

- `providers/factory.py`：把 [factory.py:18](../src/speech_transcriber/providers/factory.py) 的“非 tencent 即报错”改成按名字 dispatch，新增 `local_whisperx` 分支（lazy import + 从 Settings 读本地配置构造）。
- `config.py`：新增 `local_*` 字段（见 §4）。
- `.env.example`：追加本地配置段（见 §4）。
- `cli.py`：**基本不动**。现有 `--provider`、`--speaker-role-name/-audio` 已够用；本地不需要 `--speaker-role-audio-url`（那是腾讯云 COS 专用），传了就忽略或报错。
- `pyproject.toml`：optional extra + mypy override。

---

## 4. 新增配置（沿用 pydantic-settings 风格）

```python
# config.py，Settings 内新增
local_whisper_model: str = "large-v3"          # 可降级 medium / distil-large-v3
local_device: str = "auto"                     # auto / cpu / mps
local_compute_type: str = "int8"               # int8 / float32
local_batch_size: int = 8
local_language: str | None = None              # None=自动检测；多语言路线保持 None
huggingface_token: str = ""                    # pyannote gated 模型
local_diarization_model: str = "pyannote/speaker-diarization-3.1"
local_embedding_model: str = "pyannote/embedding"   # L3 声纹 embedding
local_voiceprint_threshold: float = 0.5        # 余弦相似度阈值，需用真实样本标定
local_model_cache_dir: Path | None = None      # HF 缓存目录
```

```bash
# .env.example 追加
# Local WhisperX provider
LOCAL_WHISPER_MODEL=large-v3
LOCAL_DEVICE=auto
LOCAL_COMPUTE_TYPE=int8
LOCAL_BATCH_SIZE=8
LOCAL_LANGUAGE=
HUGGINGFACE_TOKEN=
LOCAL_DIARIZATION_MODEL=pyannote/speaker-diarization-3.1
LOCAL_EMBEDDING_MODEL=pyannote/embedding
LOCAL_VOICEPRINT_THRESHOLD=0.5
LOCAL_MODEL_CACHE_DIR=
```

---

## 5. 三层实现细节

### L1 基础 ASR（asr.py）
1. `audio.py` 用 ffmpeg 把输入解码为 16k 单声道 waveform。
2. `whisperx.load_model(model, device, compute_type)` → `transcribe(batch_size)` 得到段级结果。
3. `whisperx.load_align_model` + `align()` 得到**词级时间戳**，聚合回段级。
4. → `TranscriptSegment(text,start,end)`；`text` = 段落拼接。

### L2 说话人分离（diarization.py）
1. `whisperx.DiarizationPipeline(use_auth_token=HF_TOKEN, device)` 跑 pyannote 得到 speaker turns。
2. `whisperx.assign_word_speakers()` 把 speaker 贴回每个词/段。
3. → `segments[].speaker = "SPEAKER_00/01..."`，`has_diarization=True`。
4. 仅当 `options.diarize=True` 时执行（默认 True）。

### L3 指定说话人声纹（voiceprint.py）
1. 对 `options.speaker_role.audio_path`（如 `audio/27秒目标角色音频.m4a`）提 enrollment embedding。
2. 对 L2 得到的每个 `SPEAKER_xx` 簇，取其音频片段求代表 embedding（多段平均更稳）。
3. 余弦相似度 vs enrollment，最高且 `> local_voiceprint_threshold` 的簇 → 全部改名为 `role.name`（如 `TARGET`），其余保留 `SPEAKER_xx`。
4. `metadata["speaker_role"] = {name, enabled: True, matched_speaker, score}`，与腾讯云输出语义对齐（README 已描述按 `speaker == "TARGET"` 过滤的用法）。
5. 复用现有 `SpeakerRole` 模型；本地只用 `audio_path`，不涉及 COS/URL。

---

## 6. 分阶段里程碑

每阶段独立可验收；验收统一过 AGENTS.md 三件套 `uv run pytest && uv run ruff check . && uv run mypy src`。

### M0 环境与骨架
- pyproject optional extra + mypy override；`.env.example`/`config.py` 新增字段；空的 `local/` 子包 + factory dispatch（未实现则抛 `ConfigError`）。
- 线下：装 ffmpeg、配 HF token 并接受条款。
- **验收**：`uv sync --extra local` 成功；`uv run python -c "import whisperx, torch, pyannote.audio"` 通过；三件套绿。

### M1 — L1 基础 ASR 跑通
- `audio.py` + `asr.py` + `transcriber.py`（仅转写）+ factory 接好。
- **验收**：
  `uv run speech-transcriber transcribe "audio/短-爱否播客且看特努斯能否 Make Apple Great Again.m4a" --provider local_whisperx --output json`
  输出与腾讯云同构的 `TranscriptResult`；`parsing.py` 单测（fake whisperx dict）；新增 `tests/smoke/test_local_whisperx_real.py`（`RUN_SMOKE=1` gated）。

### M2 — L2 说话人分离
- `diarization.py` + 对齐逻辑；`has_diarization` 生效。
- **验收**：双人音频 segments 带 `SPEAKER_xx`；单测覆盖“词→speaker 对齐”纯函数。

### M3 — L3 指定声纹
- `voiceprint.py`；复用 `--speaker-role-name/-audio`。
- **验收**：
  `... --provider local_whisperx --speaker-role-name TARGET --speaker-role-audio audio/27秒目标角色音频.m4a`
  目标人片段 `speaker=TARGET`；单测用 fake embedding 覆盖余弦+阈值判定。

### M4 — 打磨
- 长音频（2h 直播）切片与性能；阈值用真实样本标定；异常统一包成 `ProviderError`（对齐腾讯云）；README 更新本地用法；按需实现 mlx-whisper 退路。

---

## 7. 测试策略

- **单元**（不下载模型、不联网）：`parsing.py`（whisperx/pyannote 原始结构 → 模型）、`voiceprint.py`（余弦+阈值）。套路同 [test_tencent_parser.py](../tests/unit/providers/test_tencent_parser.py)。
- **smoke**（gated）：`RUN_SMOKE=1 uv run pytest tests/smoke/test_local_whisperx_real.py -v`，真跑短音频。本地 smoke 不调外部云，但仍 gated（慢、要模型）。
- 保持现有 `conftest.py` 风格。

---

## 8. 风险清单与缓解

| 风险 | 缓解 |
|---|---|
| CTranslate2 Mac 仅 CPU，转写慢 | int8 + batched + VAD 切片；可降级模型；mlx-whisper 退路 |
| pyannote 需 HF token + 网页接受条款 | M0 文档化为一次性前置步骤 |
| whisperx/pyannote/torch/ct2 版本兼容 | optional extra 隔离 + `uv.lock` 锁定；不污染核心 |
| mypy strict 无 stub | per-module `ignore_missing_imports` override |
| 首次下载数 GB 模型 | `local_model_cache_dir` 固定缓存 + 预下载说明 |
| `.m4a` 解码 | 依赖系统 ffmpeg；`audio.py` 统一解码入口 |
| 16G 内存峰值（large-v3+pyannote 同载） | 顺序加载/及时释放；避免同开大型应用 |
| 声纹阈值 / 短样本 / 重叠语音 | 用真实样本标定阈值；多段平均 embedding |

---

## 9. 执行前提醒

动手前按 AGENTS.md 先读 `README.md` 与 `docs/AI_USAGE.md`；每阶段结束跑三件套；不提交真实凭据与生成的转写产物。
