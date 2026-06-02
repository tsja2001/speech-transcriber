# 本地 WhisperX Provider — 委派任务索引

把这台 Mac（M4 / 16G / macOS）上的 `speech-transcriber` 扩展出一个**本地离线** provider：
WhisperX 转写 + 说话人分离 + 指定说话人声纹识别。复用现有 `Transcriber` 接口与 `TranscriptResult` 输出，CLI 下游无感。

> 设计依据：`docs/LOCAL_WHISPERX_PLAN.md`（方案）。本目录是**可执行的委派计划书**。

## 阅读顺序（执行者）
1. `EXECUTION-FRAMEWORK.md` ← 全局规则、自动化/不阻塞铁律、后端策略、测试哲学、完成报告格式
2. `AGENTS.md` / `README.md` / `docs/AI_USAGE.md`（仓库既有约定）
3. 当前里程碑 `M<x>-*.md`

## 里程碑总表

| 里程碑 | 内容 | 关键交付 | 状态 |
|---|---|---|---|
| M0 | 环境自愈 + 骨架 + 调试 CLI | `doctor`/`warmup`/`clip`、依赖隔离、factory dispatch | ⬜ 待执行 |
| M1 | L1 基础转写 | `decode`/`asr`、主 CLI `--provider local_whisperx` 出同构结果 | ⬜ |
| M2 | L2 说话人分离 | `diarize`（pyannote/sherpa 双后端）、`has_diarization` | ⬜ |
| M3 | L3 指定声纹 | `embed`/`compare`/`match`、目标段改名为角色名 | ⬜ |
| M4 | 打磨/长音频/文档 | 性能表、阈值标定、错误统一、文档 | ⬜ |

执行者每完成一个里程碑，提交完成报告（格式见框架 §12），统筹者审核（✅/⚠️/❌）后再开下一个。

## 给执行者的启动指令（统筹者复制给 AI CLI）
```
你是执行者。请先读 docs/tasks/EXECUTION-FRAMEWORK.md，再读 AGENTS.md 与 docs/AI_USAGE.md。
然后执行 docs/tasks/M0-environment-and-skeleton.md：逐 Phase 做，每 Phase 跑验证命令，失败先修不前进。
M0 完成后按框架 §12 格式输出完成报告并停下等待审核。不要自行扩张接口或改输出 schema。
```

---

## 统筹者前置清单（人类做，**全部可选**）

> 关键承诺：**下面没有任何一项是必须的**。执行者用免授权兜底方案能全自动跑通三层。
> 做了这些只是「更顺/精度更好」。**不会因为你没做而阻塞自动化。**

| 项 | 做了的好处 | 不做的后果 | 谁能自动搞定 |
|---|---|---|---|
| 安装 Homebrew | — | 执行者无法 `brew install ffmpeg` | 你只在「没装过 brew」时需要装一次 brew |
| （ffmpeg 本身） | — | — | **执行者自己 `brew install ffmpeg`**，你不用管（前提有 brew） |
| HuggingFace token + 接受 pyannote 条款 | L2 分离用 pyannote，精度更好 | L2 自动降级到 sherpa-onnx，精度略低但可用 | 不可自动（需网页点同意）；**统筹者已决定提供** |
| 确认「目标声纹身份」 | L3 能跑**真实**端到端 demo | L3 仍用同人/异人**合成对照**自动验证逻辑正确性 | 不可自动；**可选** |
| 配 PyPI/镜像偏好 | torch 下载更快 | 执行者自己按需切镜像 | 执行者自动 |

### 弄 HF token（你已决定弄，约 5 分钟）
1. 注册/登录 https://huggingface.co
2. 打开并点「Agree」接受条款：
   - https://huggingface.co/pyannote/segmentation-3.0
   - https://huggingface.co/pyannote/speaker-diarization-3.1
3. https://huggingface.co/settings/tokens 生成 **read** token
4. 填进 `.env` 的 `HUGGINGFACE_TOKEN=`
> 不弄也行——`LOCAL_DIARIZATION_BACKEND=auto` 会自动用 sherpa-onnx。

---

## 测试音频说明（回答「我要提供什么音频」）

**结论：基本不用你额外提供。** 执行者用 `clip` 命令从你**现有**长音频自动切出短夹具，覆盖三层测试。

### 你现有的音频（已探测）
| 文件 | 时长 | 声道/采样率 | 测试角色 |
|---|---|---|---|
| `27秒目标角色音频.m4a` | 27.2s | 2ch/48k | L3 声纹注册样本（目标人干净声音） |
| `audio.mp3` | 14.4 分钟 | 2ch/48k | 备用 |
| `彭林5.26直播15分钟.m4a` | 15.8 分钟 | 2ch/48k | L2 多人分离来源 |
| `彭林5.26直播2小时.m4a` | 2 小时 | 2ch/48k | M4 长音频压力 |
| `爱否播客….m4a` | 2.7 小时 | 2ch/48k | 备用多人 |
| `短-爱否播客….m4a` | 28.3 分钟 | 2ch/48k | L1 转写来源（注意其实不短） |

### 执行者自动切出的夹具（`tests/fixtures/audio/`，不入库）
`l1_short_zh` / `l2_multi` / `enroll_target` / `verify_target` / `other_speaker`（见框架 §6）。

### 仅 2 处「锦上添花」的可选补充
1. **L1 精确断言（可选）**：一条 10–20 秒、**念一段你已知固定文本**的中文音频。
   有它 → L1 能断言「转写命中这几个词」；没有 → 用「非空 + 语言=zh + 字数下限」弱断言，照样过。
2. **L3 真实端到端（已就绪，无需你做）**：目标人已确认 = 彭林（直播主播），执行者直接从 `彭林5.26直播15分钟.m4a` 切 `l3_mixed`，**你什么都不用提供**。L3 另有同人(`enroll`vs`verify`)高相似、异人(`enroll`vs`other`)低相似的**合成对照**独立自动验证声纹逻辑。

> ✅ 已确认：**`27秒目标角色音频.m4a` = 彭林（直播主播本人）**。L3 真实 demo 由执行者从 `彭林5.26直播15分钟.m4a` 切 `l3_mixed`，无需你补充任何音频。

---

## 输出契约（不可破坏）
所有 provider 返回同一个 `TranscriptResult`（见 `docs/AI_USAGE.md`）。本地 provider 的三层效果体现在：
- L1：`segments[].text/start/end`、`text`
- L2：`segments[].speaker="SPEAKER_xx"`、`has_diarization=true`
- L3：命中段 `speaker=<角色名>`、`metadata.speaker_role={name,enabled,matched_speaker,score,all_scores}`
