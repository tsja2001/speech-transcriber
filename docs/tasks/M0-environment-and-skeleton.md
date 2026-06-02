# M0 — 环境自愈与骨架

> 目标：把这台 Mac 配置到「能全自动跑后续里程碑」，并搭好本地 provider 的空骨架与调试 CLI。
> **本里程碑不做真实推理**，只验证：依赖装好、镜像配好、模型能下载（warmup）、骨架可导入、夹具能生成、三件套绿。
> 执行前先读 `docs/tasks/EXECUTION-FRAMEWORK.md`。

## 前置条件
- [ ] 已读 `EXECUTION-FRAMEWORK.md`、`AGENTS.md`、`README.md`、`docs/AI_USAGE.md`
- [x] 仓库可用，`uv` 可用，Python 3.12
- [ ] 已建/切到分支 `feat/local-whisperx`

## 预检命令（任一失败则停止并先修）
```bash
uv --version
python3 --version          # 期望 3.12.x
git rev-parse --abbrev-ref HEAD
ls audio/                  # 现有长音频在
```

---

## Phase 1: 依赖隔离与入口

### 1.1 `pyproject.toml`：新增 optional extra、dev 入口、mypy override
在 `[project]` 后新增：
```toml
[project.optional-dependencies]
local = [
    "whisperx>=3.1",
    "torch>=2.2",
    "torchaudio>=2.2",
    "pyannote.audio>=3.1",
    "ctranslate2>=4.4",
    "sherpa-onnx>=1.10",
    "soundfile>=0.12",
    "numpy>=1.26",
]
```
在 `[project.scripts]` 增加（保留现有 `speech-transcriber`）：
```toml
speech-transcriber-local = "speech_transcriber.providers.local.devcli:app"
```
在 `[tool.mypy]` 后追加：
```toml
[[tool.mypy.overrides]]
module = ["whisperx.*", "pyannote.*", "torch.*", "torchaudio.*", "sherpa_onnx.*", "soundfile.*"]
ignore_missing_imports = true
```
在 `[tool.pytest.ini_options].markers` 增加：`"smoke_local: local model smoke tests"`（保留现有 `smoke`）。

### 1.2 安装
```bash
uv sync --extra local
```
torch 很大；慢则按框架 §3 配 `UV_DEFAULT_INDEX` 清华源重试。

### Phase 1 验证
```bash
uv run python -c "import whisperx, torch, torchaudio, pyannote.audio, sherpa_onnx, soundfile, numpy; print('local deps ok')"
uv run python -c "import torch; print('mps', torch.backends.mps.is_available())"
```

---

## Phase 2: 包骨架 + 配置

### 2.1 新建包 `src/speech_transcriber/providers/local/`
建空实现骨架（stub 抛 `NotImplementedError`，签名先定死，后续里程碑填实现）：

- `__init__.py`：空。
- `audio.py`
  ```python
  def decode_to_wav(audio_path: Path, out_path: Path | None = None,
                    sample_rate: int = 16000) -> Path: ...
  def probe(audio_path: Path) -> dict[str, float | int]: ...  # duration/sr/channels
  ```
- `asr.py`
  ```python
  def transcribe_words(wav_path: Path, *, model: str, device: str,
                       compute_type: str, batch_size: int,
                       language: str | None) -> list[dict]: ...  # M1 填
  ```
- `diarization.py`
  ```python
  @dataclass
  class SpeakerTurn:
      start: float; end: float; speaker: str
  def diarize(wav_path: Path, *, backend: str, device: str,
              hf_token: str | None) -> list[SpeakerTurn]: ...  # M2 填
  ```
- `voiceprint.py`
  ```python
  def embed(wav_path: Path, *, device: str) -> "np.ndarray": ...          # M3
  def cosine(a: "np.ndarray", b: "np.ndarray") -> float: ...              # M3
  def match_target(turns, wav_path, enroll_wav, *, threshold, device): ...# M3
  ```
- `parsing.py`
  ```python
  def words_to_segments(words: list[dict]) -> list[TranscriptSegment]: ...        # M1
  def assign_speakers(segments, turns) -> list[TranscriptSegment]: ...            # M2
  def build_result(segments, *, duration, has_diar, meta) -> TranscriptResult:... # M1
  ```
- `transcriber.py`
  ```python
  class LocalWhisperXTranscriber:  # 实现 Transcriber 协议
      def __init__(self, *, settings_fields...): ...
      async def transcribe(self, audio_path: Path,
                           options: TranscribeOptions) -> TranscriptResult: ...  # M1 起逐步填
  ```
  **重依赖（whisperx/torch/pyannote/sherpa_onnx）一律在函数体内 lazy import，不在模块顶层。**

### 2.2 `config.py`：`Settings` 新增字段
```python
local_whisper_model: str = "large-v3"
local_device: str = "auto"               # auto/cpu/mps
local_compute_type: str = "int8"
local_batch_size: int = 8
local_language: str | None = None
huggingface_token: str = ""
local_diarization_backend: str = "auto"  # auto/pyannote/sherpa
local_voiceprint_threshold: float = 0.5
local_model_cache_dir: Path | None = None
hf_endpoint: str = "https://hf-mirror.com"
```

### 2.3 `.env.example` 追加（沿用大写下划线风格）
```bash
# Local WhisperX provider
LOCAL_WHISPER_MODEL=large-v3
LOCAL_DEVICE=auto
LOCAL_COMPUTE_TYPE=int8
LOCAL_BATCH_SIZE=8
LOCAL_LANGUAGE=
HUGGINGFACE_TOKEN=
LOCAL_DIARIZATION_BACKEND=auto
LOCAL_VOICEPRINT_THRESHOLD=0.5
LOCAL_MODEL_CACHE_DIR=
HF_ENDPOINT=https://hf-mirror.com
```

### 2.4 `providers/factory.py`：dispatch
把现有「非 tencent 即报错」改为分发；本地分支 **lazy import**：
```python
if provider_name == "tencent_cloud":
    ...  # 现有逻辑原样保留
if provider_name == "local_whisperx":
    from speech_transcriber.providers.local.transcriber import LocalWhisperXTranscriber
    return LocalWhisperXTranscriber(...from settings...)
raise ConfigError(f"Unsupported provider: {provider_name}")
```

### Phase 2 验证
```bash
uv run python -c "from speech_transcriber.config import Settings; Settings()"
uv run python -c "from speech_transcriber.providers.factory import get_transcriber; from speech_transcriber.config import Settings; \
  import asyncio; t=get_transcriber(Settings(), 'local_whisperx'); print(type(t).__name__)"
uv run mypy src   # 骨架必须类型干净
```

---

## Phase 3: 调试 CLI（devcli）骨架 + doctor

### 3.1 `src/speech_transcriber/providers/local/devcli.py`
`typer.Typer()` app，先实现 `doctor`，其余子命令建出来（stub 打印「pending Mx」）。
`doctor` **必须在未装 local extra 时也能跑**（每项 lazy import + try/except，缺失标 ❌）。

`doctor` 输出一张诊断表，至少检查：
| 检查项 | 方法 | 期望 |
|---|---|---|
| ffmpeg | `shutil.which("ffmpeg")` | 有；无则尝试 `brew install ffmpeg` |
| torch | import + `torch.__version__` | 有 |
| mps 可用 | `torch.backends.mps.is_available()` | True/False（仅提示） |
| whisperx | import | 有 |
| sherpa_onnx | import | 有 |
| HF_ENDPOINT | env | = hf-mirror.com |
| 缓存目录 | `HF_HOME`/`local_model_cache_dir` | 存在可写 |
| 现有音频 | `audio/` 列表 | 非空 |

`doctor --fix`：允许自动执行修复（装 ffmpeg、建缓存目录、写镜像 env 到 `.env`）。

### Phase 3 验证
```bash
uv run speech-transcriber-local --help
uv run speech-transcriber-local doctor
uv run speech-transcriber-local doctor --fix
```
`doctor` 退出码：全部关键项 OK → 0；有 ❌ → 非 0（但已打印修复建议）。

---

## Phase 4: 测试夹具自动生成（clip）

### 4.1 `devcli.py` 增加 `clip` 子命令
按框架 §6 表格，从 `audio/` 现有文件切出 `tests/fixtures/audio/*.wav`（16k mono pcm_s16le）。
- 用 `subprocess` 调 ffmpeg；起止时间写成常量字典，便于调整。
- `l3_mixed.wav`：从 `audio/彭林5.26直播15分钟.m4a` 切 120–150s 段（目标人=主播彭林，已确认）。默认取靠中段区间（如 `-ss 180 -t 140`）避开片头；主播全程在说话，故含目标人。
- 幂等：已存在则跳过，`--force` 重切。

### 4.2 `.gitignore` 追加
```
tests/fixtures/audio/
.cache/
*.wav
```
（注意：别忽略源码里可能存在的合法 wav；这里仅忽略夹具目录与根级缓存。若过宽，改为只忽略 `tests/fixtures/audio/` 与 `.cache/`。）

### Phase 4 验证
```bash
uv run speech-transcriber-local clip
ls -la tests/fixtures/audio/   # 期望 l1_short_zh / l2_multi / enroll_target / verify_target / other_speaker / l3_mixed 共 6 个 .wav
uv run speech-transcriber-local decode tests/fixtures/audio/l1_short_zh.wav  # 注意 decode 此刻仍是 stub，可只验证 --help；真实现在 M1
```

---

## Phase 5: 模型预热（warmup）

### 5.1 `devcli.py` 增加 `warmup` 子命令
确保镜像 env 生效后，**预下载**全部模型到缓存（带 §3 重试）：
- WhisperX 转写模型（`LOCAL_WHISPER_MODEL`，CPU/int8 加载一次）
- WhisperX 对齐模型（中文 wav2vec2）
- sherpa-onnx 分离 segmentation + 说话人 embedding(cam++) onnx（从 GitHub release）
- 若 `HUGGINGFACE_TOKEN` 存在：pyannote `speaker-diarization-3.1`
- 打印每个模型缓存路径与大小；任一失败按「重试→降级→标记」处理，不中断其余下载。

### Phase 5 验证
```bash
uv run speech-transcriber-local warmup
# 期望：whisper/align/sherpa 模型就绪；pyannote 视 token 而定（无 token 打印 "skip pyannote, will use sherpa"）
du -sh "${HF_HOME:-$HOME/.cache/huggingface}" 2>/dev/null || true
```

---

## 最终验证（全绿才算 M0 完成）
```bash
uv run ruff check .
uv run mypy src
uv run pytest                 # 现有测试不得回归；新增的骨架单测通过
uv run speech-transcriber-local doctor   # 退出码 0
ls tests/fixtures/audio/*.wav            # ≥5 个夹具
```

## 本里程碑要写的单元测试（测试即规格）
`tests/unit/providers/local/test_skeleton.py`
- `test_factory_returns_local_transcriber`：`get_transcriber(Settings(), "local_whisperx")` 返回 `LocalWhisperXTranscriber` 实例。
- `test_factory_unknown_provider_raises`：未知 provider 抛 `ConfigError`。
- `test_settings_local_defaults`：`Settings()` 的 `local_whisper_model=="large-v3"`、`local_device=="auto"`、`local_diarization_backend=="auto"`。
- `test_device_auto_resolves_cpu_for_asr`（若已抽出设备解析函数）：asr 设备恒为 `cpu`。
- `test_doctor_runs_without_local_extra`（用 monkeypatch 模拟 import 失败）：`doctor` 不抛异常、缺失项标 ❌。

## Git 提交
```bash
git add -A && git commit -m "M0: 本地 provider 环境自愈、骨架与调试 CLI

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## DoD
- [ ] `uv sync --extra local` 成功，依赖可导入
- [ ] `doctor` 通过且能 `--fix`
- [ ] `warmup` 把 whisper/align/sherpa 模型下全（pyannote 视 token）
- [ ] `clip` 生成 ≥6 个夹具（含 l3_mixed，从彭林直播切）
- [ ] factory 能返回本地 transcriber（实现仍 stub）
- [ ] 三件套绿，现有测试无回归
- [ ] 完成报告按标准格式提交

## ⚠️ 不要做
- 不在本里程碑实现任何真实转写/分离/声纹逻辑（那是 M1–M3）。
- 不改主 CLI `transcribe` 的输出 schema。
- 不在模块顶层 import 重依赖。
- 不提交夹具音频与模型缓存。
