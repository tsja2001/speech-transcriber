# 执行框架（EXECUTION-FRAMEWORK）

> **执行者必读，先读本文件，再读对应里程碑计划书。**
> 你是「执行者 AI」。本文件是你在本仓库工作的全局规则，里程碑计划书（`M0`~`M4`）是具体任务。
> 计划书是合同：写了的做，没写的不做，不自由发挥架构。

---

## 0. 角色与边界

- 你负责：按计划书编码、测试、自愈环境、产出完成报告。
- 你不负责：改变既定架构、扩展腾讯云 CLI、引入 HTTP/FastAPI（`AGENTS.md` 禁止）、提交真实凭据或生成的转写产物。
- 遇到计划书与现有代码冲突：**以现有代码为准**，在完成报告「已知问题」里记录，不要自行扩张接口。
  - 特例：`docs/AI_USAGE.md` 里描述了 `--asr-mode`、`--engine-model-type` 等参数，但 `src/speech_transcriber/cli.py` 实际没有。**不要去补它们，也不要依赖它们**，那是历史文档与代码的偏差，与本任务无关。

## 1. 核心目标：全程自动化、绝不中途阻塞

统筹者（人类）要求：你能自己配置这台 Mac（M4 / 16G / macOS），一口气跑完 M0→M4，**不因环境/下载/授权问题中途停下等人**。为此遵守下列「不阻塞」铁律：

1. **环境自愈优先**：每个里程碑第一步先跑 `uv run speech-transcriber-local doctor`，缺什么自己装/配。
2. **所有下载走镜像 + 重试**：见 §3。国内网络直连 huggingface.co 会失败，必须用镜像。
3. **授权类依赖必须有免授权兜底**：pyannote 需要 HuggingFace token（gated）。**没有 token 时自动降级到 sherpa-onnx 后端**（免登录、从 GitHub release 下载），保证 L2/L3 仍能全自动跑通。见 §4。
4. **大模型一次性预热**：M0 末尾 `warmup` 把所有模型下全，后续阶段不再触发首次下载。
5. **测试夹具自动生成**：不依赖统筹者补音频，用 ffmpeg 从现有长音频切小片段（见 §6）。
6. **超时即降级，不死等**：任何模型推理/下载设合理超时；失败先重试（§3），再降级（§4），仍失败才在报告里标 ❌ 并继续后续不依赖它的步骤。

> 唯一可能需要统筹者线下做的事，已在 `docs/tasks/README.md` 的「统筹者前置清单」列出，且**全部是可选增强**——不做也能自动跑通（用兜底方案），只是精度略低。

## 2. 技术栈与设备

- 包管理：`uv`（Python 3.12）。所有命令用 `uv run ...`。
- 本地重依赖隔离在 optional extra `local` 里：装它用 `uv sync --extra local`。
- 设备策略（写进 `local_device=auto` 的解析逻辑）：
  - 转写（WhisperX/CTranslate2）：**只能 CPU**（CTranslate2 在 Apple Silicon 无 Metal）。用 `compute_type=int8`。
  - diarization / embedding（PyTorch / onnxruntime）：优先 `mps`（`torch.backends.mps.is_available()`），不可用回退 `cpu`。
  - `auto` = 上述自动选择；可被 `LOCAL_DEVICE` 覆盖。

## 3. 网络与下载（镜像配置，必做）

`doctor` 和 `warmup` 必须确保以下环境变量生效（写进 `.env`，并在进程内 `os.environ.setdefault`）：

```bash
# HuggingFace 镜像（whisper / wav2vec2 对齐模型 / pyannote 都走这里）
HF_ENDPOINT=https://hf-mirror.com
# 模型缓存固定目录，避免重复下载（默认 ~/.cache/huggingface）
HF_HOME=<LOCAL_MODEL_CACHE_DIR 或 ~/.cache/huggingface>
```

- PyPI：若 `uv sync` 拉 torch 很慢，配置清华镜像 `UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple`（先尝试默认源，明显慢再切，切换写入完成报告）。
- 下载统一封装重试：**最多 3 次，指数退避（2/4/8s）**，全部失败才算失败。
- sherpa-onnx 模型从 GitHub release 下载；若 GitHub 慢，用镜像前缀 `https://ghproxy.net/` 或 `https://mirror.ghproxy.com/`（任选其一可用的），写进完成报告。

## 4. Diarization / 声纹后端策略（不阻塞的关键）

抽象一个后端开关 `local_diarization_backend`，取值 `auto|pyannote|sherpa`：

| 后端 | 依赖 | 授权 | 何时用 |
|---|---|---|---|
| `pyannote` | pyannote.audio（HF gated） | 需 `HUGGINGFACE_TOKEN` + 网页接受条款 | token 存在时，精度首选 |
| `sherpa` | sherpa-onnx（GitHub release onnx） | **免授权** | token 缺失时自动兜底；CI/快速测试默认 |

- `auto` 解析逻辑：`HUGGINGFACE_TOKEN` 非空 → `pyannote`；否则 → `sherpa`。
- **L3 声纹 embedding 默认始终用 sherpa-onnx 的 3D-Speaker `cam++` onnx 模型**（免授权、中文声纹强），不依赖 HF，从而 L3 全程自动。
- 两后端产出**统一的中间结构**（见 M2 的 `SpeakerTurn`），上层对齐/匹配逻辑后端无关。

> 这样：L1 转写（whisper/对齐模型非 gated，配镜像即可）、L2 分离（sherpa 免授权兜底）、L3 声纹（sherpa cam++ 免授权）——**全链路无需任何人工授权即可自动跑通**。pyannote 只是 token 存在时的精度增强。

## 5. 模块独立 CLI（统筹者强制要求）

除主 CLI `speech-transcriber transcribe`（对外契约，**不得改其输出 schema**）外，新增一个**开发调试 CLI**，每个模块都能单独跑：

入口（`pyproject.toml [project.scripts]`）：`speech-transcriber-local = "speech_transcriber.providers.local.devcli:app"`

| 子命令 | 模块 | 作用 | 出现里程碑 |
|---|---|---|---|
| `doctor` | 环境 | 自检 ffmpeg/torch/mps/镜像/缓存/模型，输出诊断表 | M0 |
| `warmup` | 环境 | 预下载所有模型（whisper/align/分离/embedding） | M0 |
| `clip` | 夹具 | 从现有长音频切测试小片段到 `tests/fixtures/audio/` | M0 |
| `decode` | audio | 解码音频→16k mono wav，打印时长/采样率/声道 | M1 |
| `asr` | asr | 只转写，输出 segments JSON（含词级时间戳统计） | M1 |
| `diarize` | diarization | 只分离，输出说话人时间线（`SpeakerTurn` 列表 + 说话人数） | M2 |
| `embed` | voiceprint | 输出一段音频的声纹向量维度与范数 | M3 |
| `compare` | voiceprint | 两段音频声纹余弦相似度（数值 + 是否≥阈值） | M3 |
| `match` | voiceprint | 注册样本 + 混合音频 → 哪些 speaker 是目标人 | M3 |
| `pipeline` | transcriber | 完整 L1+L2+L3，等价主 CLI 但带详细调试输出与计时 | M3 |

- `doctor` 必须在**未安装 local extra 时也能运行**（lazy import + 捕获 ImportError，把缺失项列为 ❌，给出修复命令）。
- 所有子命令 `--help` 必须可用且参数有 `help` 文本。
- 输出默认 JSON（机器可读），加 `--pretty` 人读。

## 6. 测试夹具：自动切片（不需要统筹者补音频）

现有 `audio/` 全是长音频（最短整段 27 秒，其余 14 分钟~2.7 小时）。直接拿来跑 `large-v3` CPU 太慢，不能当快测试集。`clip` 命令负责自动生成短夹具（输出到 `tests/fixtures/audio/`，加入 `.gitignore`）：

| 夹具文件 | 来源 | 切法 | 用途 |
|---|---|---|---|
| `l1_short_zh.wav` | `audio/短-爱否播客….m4a` | 取 60–90s 段，16k mono | L1 转写快测 |
| `l2_multi.wav` | `audio/彭林5.26直播15分钟.m4a` | 取含多人对话的 90–150s 段 | L2 分离 |
| `enroll_target.wav` | `audio/27秒目标角色音频.m4a` | 前 0–13s，16k mono | L3 注册（同人对照 A） |
| `verify_target.wav` | `audio/27秒目标角色音频.m4a` | 后 14–27s，16k mono | L3 同人对照 B（应高相似度） |
| `other_speaker.wav` | `audio/短-爱否播客….m4a` | 任取 20s 单人段 | L3 异人对照（应低相似度） |
| `l3_mixed.wav` | `audio/彭林5.26直播15分钟.m4a` | 取主播彭林在说话的 120–150s 段 | L3 端到端真实场景 |

- 切片用 ffmpeg：`ffmpeg -ss <start> -t <dur> -i <in> -ac 1 -ar 16000 -c:a pcm_s16le <out>`。
- **目标人身份已确认 = 彭林（直播主播本人）**。`l3_mixed.wav` 从 `彭林5.26直播15分钟.m4a` 取靠中段的 120–150s（如 `-ss 180 -t 140`，避开片头寒暄）；主播几乎全程在说话，故该段含目标人。L3 端到端断言「出现 `TARGET` 段」；若极小概率该段彭林恰未发声导致未命中，报告标注并换一段重切。合成对照（同人/异人）始终独立自动验证声纹逻辑，不依赖此项。

## 7. 测试哲学（测试即规格）

- **单元测试**（`tests/unit/...`）：纯函数、不下载模型、不联网、毫秒级。每个测试名描述具体行为，断言具体值。
- **组件测试**：通过 dev CLI 子命令验证单模块。
- **Smoke 测试**（`tests/smoke/...`）：真跑模型，**必须 gated**：`RUN_SMOKE_LOCAL=1` 才执行，否则 `pytest.skip`。用 §6 的小夹具，单条 < 2 分钟。
- **不阻塞断言策略**：内容未知的真实音频用**弱断言**（非空 / 语言=zh / 字数下限 / 说话人数下限），不写死具体文字；声纹用**合成对照**（同人高分、异人低分）而非依赖身份标注。
- 失败测试必须存在（`_error` / `_timeout` / `_not_found` / `_low_similarity` 后缀），不允许只有正路径。

## 8. 每阶段验证（失败不前进）

每个 Phase 结尾跑该 Phase 的验证命令；不过不进下一 Phase。每个里程碑结尾跑全量三件套（来自 `AGENTS.md`）：

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Smoke（按里程碑）：

```bash
RUN_SMOKE_LOCAL=1 uv run pytest tests/smoke/ -v -m smoke
```

## 9. 错误处理规范

- 所有本地 provider 对外抛出的异常**统一包成** `speech_transcriber.errors.ProviderError`（与腾讯云一致），构造：`ProviderError("local_whisperx", message, retryable=<bool>)`。
  - 文件不存在 / 参数非法 → `retryable=False`。
  - 模型下载失败 / 设备 OOM → `retryable=True`。
- dev CLI 捕获 `SpeechTranscriberError` 打到 stderr 并以非零退出码退出，正路径 JSON 走 stdout（与主 CLI 一致）。
- 禁止裸 `except Exception: pass`；至少 `logging` 记录。

## 10. 日志

- 用标准 `logging`，logger 名 `speech_transcriber.providers.local.*`。
- dev CLI 加 `--verbose` 时设 `DEBUG`，默认 `INFO`。模型下载、设备选择、各阶段耗时打 `INFO`。
- 不得把日志混入 stdout 的 JSON（日志走 stderr）。

## 11. Git 规范

- 在 `main` 上工作前先建分支：`feat/local-whisperx`（若已在该分支则继续）。
- 每个里程碑一个 commit（或每 Phase 一个），message 用中文祈使句，结尾固定：
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- 只有统筹者明确要求才 push。不提交 `.env`、模型缓存、`tests/fixtures/audio/`、`output/`、转写结果。

## 12. 完成报告（每个里程碑结束必交，格式固定）

```
# M<x> 完成报告
## 执行摘要
- 任务 / 状态(✅⚠️❌) / 新增·修改文件数 / 新增测试数 / 总耗时
## 文件变更清单
（表格：文件 | 操作 | 说明）
## 环境与下载
（doctor 输出摘要；用了哪些镜像；模型缓存大小）
## 测试结果
（粘贴 `uv run pytest -v --tb=short` 完整输出）
## 覆盖率
（`uv run pytest --cov=speech_transcriber.providers.local` 输出）
## 代码质量
（`uv run ruff check .` 与 `uv run mypy src` 输出）
## Smoke 结果（如适用）
（表格：测试名 | 结果 | 耗时 | 用的夹具 | 关键观测值如说话人数/相似度）
## 模块 CLI 自测
（每个本里程碑新增的 devcli 子命令，贴一条真实运行命令+输出摘要）
## 已知问题
（无 / 具体列出，标注是否影响后续里程碑）
## DoD 自检
（代码质量 / 测试 / 日志 / 文档 四板块逐项打勾）
```

## 13. 故障排除（先查这里再降级）

| 现象 | 处理 |
|---|---|
| `uv sync --extra local` 下载 torch 极慢/超时 | 配 `UV_DEFAULT_INDEX` 清华源后重试 |
| 模型下载 401/403 | pyannote 未授权 → 切 `sherpa` 后端（§4） |
| 模型下载连接超时 | 确认 `HF_ENDPOINT=https://hf-mirror.com` 已生效；重试 3 次 |
| `ffmpeg: command not found` | `brew install ffmpeg`；无 brew 见 README 前置清单 |
| `torch mps` 报算子不支持 | 该模块 `device=cpu` 回退，记录到报告 |
| sherpa GitHub release 下不动 | 加 ghproxy 镜像前缀（§3） |
| 转写慢到无法接受 | 降模型档（`large-v3`→`medium`），或按 M4 启用 mlx-whisper 退路 |
| mypy 报 whisperx/pyannote 无 stub | 确认 `[[tool.mypy.overrides]]` 已加该模块 `ignore_missing_imports` |
