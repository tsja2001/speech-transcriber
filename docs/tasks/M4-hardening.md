# M4 — 打磨、长音频与收尾

> 目标：把 M1–M3 的能力做稳、做快、写清文档。本里程碑按**目标**描述，执行者开工时先把每个目标拆成 Phase 再做（拆解结果写进完成报告开头）。
> 执行前确认 M3 ✅。

## 前置条件
- [ ] M1–M3 全部 ✅，三层 smoke 通过

## 目标 1：长音频与性能
- 用 `audio/彭林5.26直播2小时.m4a`（7204s）验证不 OOM、不崩。
- 实现/确认 WhisperX VAD 切片 + batched 推理；如转写过慢，提供 `LOCAL_WHISPER_MODEL` 降档（`large-v3`→`medium`/`distil-large-v3`）的实测对比。
- 顺序加载/释放模型，控制 16G 内存峰值（转写、分离、embedding 不必同时常驻）。
- **验收**：在 2 小时音频上 `pipeline` 跑通并产出完整 `TranscriptResult`；完成报告给出「时长→耗时→峰值内存」表（至少 large-v3 与一个降档模型各一行）。

## 目标 2：声纹阈值标定
- 用同人/异人多对样本，给出 `LOCAL_VOICEPRINT_THRESHOLD` 的推荐值与依据（同人分布 vs 异人分布）。
- 提供一个 `devcli calibrate <enroll> <same...> <diff...>` 辅助命令，输出建议阈值。
- **验收**：完成报告给出阈值标定表与推荐默认值；更新 `.env.example` 注释。

## 目标 3：错误处理统一与健壮性
- 全链路异常统一为 `ProviderError("local_whisperx", msg, retryable)`，对照框架 §9 逐项检查。
- 覆盖失败场景测试：损坏音频、空音频、ffmpeg 缺失、模型缺失、enroll 文件缺失、`audio_url` 误用。
- **验收**：新增失败场景单测全过；无裸 `except`。

## 目标 4：mlx-whisper 可选退路（仅当 L1 转写速度不满足时）
- 抽象 ASR 后端 `local_asr_backend = whisperx|mlx`；`mlx` 用 `mlx-whisper`（吃 M4 GPU/ANE），输出对齐到同一 `words` 结构，下游不变。
- mlx 作为 `local` extra 之外的**额外 optional extra**（如 `local-mlx`），避免强依赖。
- **验收**：`asr --backend mlx` 可用且与 whisperx 输出同构；完成报告给出两后端速度对比。**若目标 1 的 whisperx 速度已可接受，本目标可标记「按需，未实现」并说明理由。**

## 目标 5：文档更新
- `README.md`：新增「本地 WhisperX provider」用法段（安装 `uv sync --extra local`、三层用法、devcli 速查、HF token 可选说明）。
- `docs/AI_USAGE.md`：补本地 provider 调用示例（保持 `TranscriptResult` 契约说明）。
- `docs/LOCAL_WHISPERX_PLAN.md`：与最终实现校对，标注与原方案的偏差。
- **验收**：文档与实际 CLI 一致；`speech-transcriber-local --help` 列出的子命令在 README 有对应说明。

## 最终验证（全量）
```bash
uv run pytest
uv run ruff check .
uv run mypy src
RUN_SMOKE_LOCAL=1 uv run pytest tests/smoke/ -v
uv run speech-transcriber-local doctor
```

## Git 提交
```bash
git add -A && git commit -m "M4: 长音频性能、阈值标定、错误健壮性与文档

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## DoD
- [ ] 2 小时音频跑通，给出性能/内存表
- [ ] 阈值标定表与推荐默认值
- [ ] 失败场景测试齐全，错误统一 ProviderError
- [ ] mlx 退路实现或明确「按需未实现」并说明
- [ ] README / AI_USAGE / PLAN 文档更新且与实现一致
- [ ] 全量三件套 + 全部 smoke 通过

## ⚠️ 不要做
- 不为追求性能牺牲输出 schema 兼容。
- 不把 mlx 设成强依赖（必须是可选 extra）。
- 不引入 HTTP/FastAPI 服务（AGENTS.md 禁止）。
