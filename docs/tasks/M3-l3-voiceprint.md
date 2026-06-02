# M3 — L3 指定说话人声纹识别

> 目标：给一段目标人的干净样本（enrollment），在分离结果里把「就是这个人」的片段 `speaker` 改成调用方指定的角色名（如 `TARGET`），其余保留 `SPEAKER_xx`。语义与腾讯云角色分离一致。
> 声纹 embedding 用 sherpa-onnx `cam++`（免授权），**全程自动，无需 HF token**。
> 执行前确认 M2 完成报告为 ✅。

## 前置条件
- [ ] M2 ✅
- [ ] 夹具：`enroll_target.wav`、`verify_target.wav`（同一人两段）、`other_speaker.wav`（不同人）、`l2_multi.wav`
- [ ] `l3_mixed.wav` 存在（从彭林直播切，目标人=彭林本人，已确认）

## 预检
```bash
uv run speech-transcriber-local doctor
ls tests/fixtures/audio/{enroll_target,verify_target,other_speaker}.wav
```

---

## Phase 1: 声纹 embedding 与相似度（voiceprint.py）

### 1.1 `embed(wav_path, *, device) -> np.ndarray`
lazy import `sherpa_onnx`；加载 `cam++` speaker embedding extractor（模型路径来自缓存，M0 warmup 已下）。
- 输入需 16k mono（不是则先 `decode_to_wav`）。
- 返回 1D `np.float32` 向量（L2 归一化后返回，便于余弦）。
- 模型缺失 → `ProviderError(retryable=True)`，提示先 `warmup`。

### 1.2 `cosine(a, b) -> float`
标准余弦相似度，纯函数（对已归一化向量即点积）。返回 `[-1, 1]`。

### 1.3 `match_target(turns, wav_path, enroll_wav, *, threshold, device) -> tuple[str|None, float, dict]`
1. `ref = embed(enroll_wav)`。
2. 按 `turns` 把 `wav_path` 切成各 speaker 的音频，对**每个 speaker** 聚合其所有 turn 的音频求一个代表 embedding（拼接片段或多段平均；**实现选「该 speaker 最长的若干 turn 拼接后 embed」并写 docstring**）。
3. 对每个 speaker 算 `cosine(ref, spk_emb)`。
4. 取最高分 speaker；`score >= threshold` → 返回 `(speaker_label, score, all_scores)`；否则 `(None, best_score, all_scores)`。

### 1.4 `parsing.rename_speaker(segments, from_label, to_name) -> list[TranscriptSegment]`
纯函数：把 `speaker==from_label` 的段改名为 `to_name`，其余不变。

### 1.5 devcli 子命令
- `embed <audio> [--pretty]` → `{dim, norm}`。
- `compare <audio_a> <audio_b> [--threshold]` → `{cosine, is_same: bool}`。
- `match <enroll> <mixed> [--backend] [--threshold] [--pretty]` → `{matched_speaker, score, all_scores}`。

### Phase 1 验证（合成对照，不依赖身份）
```bash
# 同一个人：应高相似度（期望 cosine 明显高，is_same True）
uv run speech-transcriber-local compare tests/fixtures/audio/enroll_target.wav tests/fixtures/audio/verify_target.wav --pretty
# 不同人：应低相似度（is_same False）
uv run speech-transcriber-local compare tests/fixtures/audio/enroll_target.wav tests/fixtures/audio/other_speaker.wav --pretty
```

---

## Phase 2: 接入编排 + 主 CLI（transcriber.py）

### 2.1 在 L2 之后插入 L3
```python
if options.diarize and options.speaker_role and options.speaker_role.audio_path:
    enroll = await asyncio.to_thread(decode_to_wav, options.speaker_role.audio_path)
    matched, score, all_scores = await asyncio.to_thread(
        match_target, turns, wav, enroll,
        threshold=self.voiceprint_threshold, device=...)
    if matched is not None:
        segments = rename_speaker(segments, matched, options.speaker_role.name)
    meta["speaker_role"] = {"name": options.speaker_role.name,
        "enabled": True, "matched_speaker": matched, "score": score,
        "all_scores": all_scores}
```
- 本地只用 `speaker_role.audio_path`；若调用方误传 `audio_url`（腾讯云 COS 专用）→ `ProviderError(retryable=False)`，提示本地用 `--speaker-role-audio`。
- `speaker_role.audio_path` 不存在 → `ProviderError(retryable=False)`。

### 2.2 复用现有 CLI 参数
`--speaker-role-name` + `--speaker-role-audio` 已在 `cli.py`，无需改 CLI。

### Phase 2 验证（合成自洽 + 真实可选）
```bash
# 自洽验证：把目标样本本身当混合音频，注册同一个人 → 该(唯一)说话人应被改名为 TARGET
uv run speech-transcriber transcribe tests/fixtures/audio/verify_target.wav \
  --provider local_whisperx \
  --speaker-role-name TARGET \
  --speaker-role-audio tests/fixtures/audio/enroll_target.wav \
  --output json | uv run python -c \
  "import sys,json; r=json.load(sys.stdin); sr=r['metadata']['speaker_role']; \
   assert sr['enabled']; assert sr['matched_speaker'] is not None; \
   assert any(s['speaker']=='TARGET' for s in r['segments']); print('L3 self OK score=',round(sr['score'],3))"

# 真实端到端：彭林直播切段 l3_mixed，注册彭林样本 → 应出现 TARGET 段
uv run speech-transcriber transcribe tests/fixtures/audio/l3_mixed.wav \
  --provider local_whisperx \
  --speaker-role-name TARGET \
  --speaker-role-audio "audio/27秒目标角色音频.m4a" \
  --output json | uv run python -c \
  "import sys,json; r=json.load(sys.stdin); spk={s['speaker'] for s in r['segments'] if s['speaker']}; \
   assert 'TARGET' in spk, spk; print('L3 real OK speakers=',sorted(spk))"
```

---

## Phase 3: 测试

### 3.1 单元测试 `tests/unit/providers/local/test_voiceprint.py`（纯函数，构造 numpy 向量）
- `test_cosine_identical_is_one`：同向量 → 1.0（容差 1e-6）。
- `test_cosine_orthogonal_is_zero`：正交向量 → 0.0。
- `test_match_picks_highest_above_threshold`（monkeypatch `embed` 返回受控向量）：构造目标 speaker emb 与 ref 高相似、其余低 → 返回该 speaker。
- `test_match_returns_none_below_threshold`：全部低于阈值 → matched is None、score 为最高分。
- `test_rename_speaker_only_target_label`：只改指定 label，其余不变、段数不变。
- `test_rename_speaker_absent_label_noop`：目标 label 不存在 → 列表不变。

### 3.2 Smoke `tests/smoke/test_local_l3_real.py`（gated，真实模型）
- `test_same_speaker_high_similarity`：`cosine(enroll, verify) >= 0.5`（同人）。
- `test_different_speaker_low_similarity`：`cosine(enroll, other) < cosine(enroll, verify)`（异人相对更低；用相对断言更稳，避免绝对阈值脆弱）。
- `test_pipeline_self_match_renames`：上面 Phase 2 的自洽场景断言。
- `test_pipeline_mixed_identifies_target`：跑 `l3_mixed.wav`（彭林直播切段）+ 注册 `27秒目标角色音频.m4a`，断言出现 `TARGET` 段。彭林为主播几乎全程发声，必命中；若未命中则报告标注并由统筹者换段（合成对照测试不受影响）。

### Phase 3 / 最终验证
```bash
uv run pytest
uv run ruff check .
uv run mypy src
RUN_SMOKE_LOCAL=1 uv run pytest tests/smoke/test_local_l3_real.py -v
```

## Git 提交
```bash
git add -A && git commit -m "M3: 本地指定说话人声纹识别（cam++ embedding + 匹配改名）

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

## DoD
- [ ] `embed` / `compare` / `match` 三个 devcli 可用
- [ ] 同人 cosine 高、异人低（合成对照 smoke 通过）
- [ ] 端到端自洽：目标段被改名为角色名，`metadata.speaker_role` 完整
- [ ] 声纹纯函数单测覆盖阈值上下/缺失 label
- [ ] 三件套绿，无回归

## ⚠️ 不要做
- 不依赖「知道目标人是谁」来通过自动化测试（用同人/异人合成对照）。
- 不引入 HF 依赖做 embedding（用 sherpa cam++）。
- 不改输出 schema；沿用 `speaker` 字段与 `metadata.speaker_role` 结构。
