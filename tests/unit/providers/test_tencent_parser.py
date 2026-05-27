"""Tests for Tencent ASR result parsing."""

from __future__ import annotations

from types import SimpleNamespace

from speech_transcriber.providers.tencent_cloud import parse_task_status


def test_parse_result_detail_uses_final_sentence_and_speaker() -> None:
    task_status = SimpleNamespace(
        AudioDuration=2.5,
        ResultDetail=[
            SimpleNamespace(
                FinalSentence="hello there",
                StartMs=1000,
                EndMs=2500,
                SpeakerId=0,
            )
        ],
    )

    result = parse_task_status(task_status, provider="tencent_cloud")

    assert result.text == "hello there"
    assert result.duration_seconds == 2.5
    assert result.has_diarization is True
    assert result.segments[0].start == 1.0
    assert result.segments[0].end == 2.5
    assert result.segments[0].speaker == "SPEAKER_0"


def test_parse_result_detail_uses_role_name_speaker_id() -> None:
    task_status = SimpleNamespace(
        AudioDuration=2.5,
        ResultDetail=[
            SimpleNamespace(
                FinalSentence="hello there",
                StartMs=1000,
                EndMs=2500,
                SpeakerId="HOST",
            )
        ],
    )

    result = parse_task_status(task_status, provider="tencent_cloud")

    assert result.has_diarization is True
    assert result.segments[0].speaker == "HOST"


def test_parse_result_detail_prefers_speaker_role_name() -> None:
    task_status = SimpleNamespace(
        ResultDetail=[
            SimpleNamespace(
                FinalSentence="hello there",
                StartMs=1000,
                EndMs=2500,
                SpeakerId=0,
                SpeakerRoleName="HOST",
            )
        ],
    )

    result = parse_task_status(task_status, provider="tencent_cloud")

    assert result.segments[0].speaker == "HOST"


def test_parse_timestamped_result_fallback() -> None:
    task_status = {
        "AudioDuration": 65.0,
        "Result": (
            "[00:00:01.000,00:00:03.500] first line\n"
            "[00:01:00,00:01:05] second line"
        ),
    }

    result = parse_task_status(task_status, provider="tencent_cloud")

    assert result.text == "first line second line"
    assert [segment.start for segment in result.segments] == [1.0, 60.0]
    assert [segment.end for segment in result.segments] == [3.5, 65.0]


def test_parse_plain_result_fallback() -> None:
    task_status = {"Result": "one plain transcript\ncontinued here"}

    result = parse_task_status(task_status, provider="tencent_cloud")

    assert result.text == "one plain transcript continued here"
    assert len(result.segments) == 1
    assert result.segments[0].start == 0.0
    assert result.segments[0].end == 0.0


def test_parse_empty_result_returns_empty_transcript() -> None:
    result = parse_task_status({}, provider="tencent_cloud")

    assert result.text == ""
    assert result.segments == []
    assert result.has_diarization is False
