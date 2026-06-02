# M2 — L2 说话人分离（pyannote / sherpa 双后端）

> 目标：在 L1 之上给每个片段打 `speaker`（`SPEAKER_00/01...`），`has_diarization=True`。
> 双后端：有 HF token 用 pyannote（精度优先）；否则自动用 sherpa-onnx（免授权兜底）。**不阻塞**。
> 执行前确认 M1 完成报告为 ✅。

## 前置条件
- [ ] M1 ✅
- [ ] `tests/fixtures/audio/l2_multi.wav` 存在（多人对话片段）
- [ ] M0 warmup 已下载 sherpa 分离模型；若有 token，pyannote 也已就绪

## 预检
```bash
uv run speech-transcriber-local doctor
uv run speech-transcriber-local asr tests/fixtures/audio/l2_multi.wav --pretty   # L1 仍工作
```

---

## Phase 1: 后端抽象 + 统一中间结构（diarization.py）

### 1.1 `SpeakerTurn` 与 `diarize` 分发
```python
@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str   # 规范化为 "SPEAKER_00" 形式

def diarize(wav_path, *, backend: str, device: str, hf_token: str | None) -> list[SpeakerTurn]:
    resolved = _resolve_backend(backend, hf_token)   # auto→pyannote(if token) else sherpa
    if resolved == "pyannote": return _diarize_pyannote(...)
    return _diarize_sherpa(...)
```
- `_resolve_backend`：`backend=="auto"` 且 `hf_token` 非空 → `"pyannote"`，否则 `"sherpa"`；显式值直接用（显式 pyannote 但无 token → 抛 `ProviderError(retryable=False)` 提示缺 token，或按框架降级——**默认降级并 WARNING**）。
- 两后端都输出**按 start 升序、speaker 标签规范化**的 `list[SpeakerTurn]`。

### 1.2 `_diarize_pyannote`
lazy import；用 `whisperx.DiarizationPipeline(use_auth_token=hf_token, device=device)` 或直接 `pyannote.audio.Pipeline`。把结果转成 `SpeakerTurn`，speaker 文本规范化为 `SPEAKER_%02d`。

### 1.3 `_diarize_sherpa`
lazy import `sherpa_onnx`；用 `OfflineSpeakerDiarization`（segmentation 模型 + speaker embedding 模型，路径来自缓存）。把 segments 转 `SpeakerTurn`，标签规范化。

### 1.4 `devcli diarize`
`diarize <audio> [--backend auto|pyannote|sherpa] [--pretty]`：输出 `{backend, num_speakers, turns:[{start,end,speaker}]}`。

### Phase 1 验证
```bash
uv run speech-transcriber-local diarize tests/fixtures/audio/l2_multi.wav --backend sherpa --pretty
# 期望：num_speakers>=2，turns 非空、按时间升序、speaker 形如 SPEAKER_00
```

---

## Phase 2: 片段与说话人对齐（parsing.assign_speakers）

### 2.1 `assign_speakers(segments, turns) -> list[TranscriptSegment]`
**纯函数**。对每个 segment，按与各 `SpeakerTurn` 的**时间重叠最大**原则分配 speaker：
- 计算 `overlap = max(0, min(seg.end, turn.end) - max(seg.start, turn.start))`，取 overlap 最大的 turn 的 speaker。
- 无任何重叠 → speaker 保持 None（或最近邻 turn，二选一，**实现选「最大重叠，无重叠则 None」并写进 docstring**）。
- 返回新的 segment 列表（不可变更新）。

### 2.2 接入 `transcriber.py`
在 L1 的 `words_to_segments` 之后、`build_result` 之前插入：
```python
if options.diarize:
    turns = await asyncio.to_thread(diarize, wav, backend=..., device=..., hf_token=...)
    segments = assign_speakers(segments, turns)
    has_diar = any(s.speaker for s in segments)
```
`build_result(..., has_diar=has_diar, meta={..., "diarization_backend": resolved})`。

### Phase 2 验证（主 CLI 端到端）
```bash
uv run speech-transcriber transcribe tests/fixtures/audio/l2_multi.wav \
  --provider local_whisperx --output json | uv run python -c \
  "import sys,json; r=json.load(sys.stdin); spk={s['speaker'] for s in r['segments'] if s['speaker']}; \
   assert r['has_diarization'] is True; assert len(spk)>=2, spk; print('L2 OK speakers=',sorted(spk))"
```

---

## Phase 3: 测试

### 3.1 单元测试 `tests/unit/providers/local/test_assign_speakers.py`（纯函数，无模型）
- `test_assign_picks_max_overlap`：1 段落在 SPEAKER_01 的 turn 内 → 该段 speaker=="SPEAKER_01"。
- `test_assign_partial_overlap_picks_larger`：段跨两 turn，重叠多的胜出。
- `test_assign_no_overlap_keeps_none`：段与所有 turn 不重叠 → speaker is None。
- `test_assign_empty_turns_returns_unchanged`：turns 空 → 所有 speaker None，不抛异常。

### 3.2 后端解析单元测试 `tests/unit/providers/local/test_diar_backend.py`
- `test_resolve_auto_with_token_picks_pyannote`。
- `test_resolve_auto_without_token_picks_sherpa`。
- `test_resolve_explicit_pyannote_without_token_warns_and_falls_back`（捕获 WARNING / 或断言降级行为，与实现一致）。
- `test_speaker_label_normalized`：原始 `0`/`"spk_1"` → `"SPEAKER_00"`/`"SPEAKER_01"`。

### 3.3 Smoke `tests/smoke/test_local_l2_real.py`（gated）
- `test_sherpa_diarization_finds_multiple_speakers`：跑 `l2_multi.wav`，断言 `num_speakers>=2`、turns 时间有序。
- `test_pipeline_assigns_speakers`：端到端，断言 `has_diarization is True` 且不同段出现 ≥2 个 speaker 标签。
- pyannote 后端：仅当 `HUGGINGFACE_TOKEN` 设置时跑（否则 `skip`）。

### Phase 3 / 最终验证
```bash
uv run pytest
uv run ruff check .
uv run mypy src
RUN_SMOKE_LOCAL=1 uv run pytest tests/smoke/test_local_l2_real.py -v
```

## Git 提交
```bash
git add -A && git commit -m "M2: 本地说话人分离（pyannote/sherpa 双后端 + 片段对齐）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## DoD
- [ ] `devcli diarize` 两后端可用（无 token 时 sherpa 自动生效）
- [ ] `assign_speakers` 纯函数单测覆盖重叠/无重叠/空
- [ ] 端到端 `has_diarization=True` 且 ≥2 speaker
- [ ] L2 smoke gated 通过
- [ ] 三件套绿，无回归

## ⚠️ 不要做
- 不做声纹/指定说话人（M3）；speaker 仍是匿名 `SPEAKER_xx`。
- 不因缺 HF token 而失败——必须自动走 sherpa。
- 不改输出 schema。
