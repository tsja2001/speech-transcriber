"""Command line interface."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from speech_transcriber import __version__
from speech_transcriber.config import Settings
from speech_transcriber.errors import SpeechTranscriberError
from speech_transcriber.models import SpeakerRole, TranscribeOptions, TranscriptResult
from speech_transcriber.providers.factory import get_transcriber

app = typer.Typer(help="Speech Transcriber CLI")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(f"speech-transcriber {__version__}")


@app.command()
def transcribe(
    audio_path: Annotated[Path, typer.Argument(help="Local audio file path")],
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="Provider name, default from .env"),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", help="Output format: json or text"),
    ] = "json",
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output-file",
            help=(
                "Write output to a file path, or to a directory with an "
                "auto-generated filename."
            ),
        ),
    ] = None,
    speaker_role_name: Annotated[
        str | None,
        typer.Option(
            "--speaker-role-name",
            help="Target speaker role name for role separation.",
        ),
    ] = None,
    speaker_role_audio: Annotated[
        Path | None,
        typer.Option(
            "--speaker-role-audio",
            help="Local clean voice sample for the target speaker.",
        ),
    ] = None,
    speaker_role_audio_url: Annotated[
        str | None,
        typer.Option(
            "--speaker-role-audio-url",
            help="Public URL for the target speaker voice sample.",
        ),
    ] = None,
    asr_mode: Annotated[
        str | None,
        typer.Option(
            "--asr-mode",
            help=(
                "Tencent ASR shortcut: standard, large, diarization, or role. "
                "Explicit low-level options override mode defaults."
            ),
        ),
    ] = None,
    engine_model_type: Annotated[
        str | None,
        typer.Option("--engine-model-type", help="Tencent ASR EngineModelType."),
    ] = None,
    channel_num: Annotated[
        int | None,
        typer.Option("--channel-num", help="Tencent ASR ChannelNum."),
    ] = None,
    res_text_format: Annotated[
        int | None,
        typer.Option("--res-text-format", help="Tencent ASR ResTextFormat."),
    ] = None,
    speaker_diarization: Annotated[
        int | None,
        typer.Option(
            "--speaker-diarization",
            help=(
                "Tencent ASR SpeakerDiarization: "
                "0 off, 1 speaker split, 3 role split."
            ),
        ),
    ] = None,
    speaker_number: Annotated[
        int | None,
        typer.Option("--speaker-number", help="Tencent ASR SpeakerNumber."),
    ] = None,
    hotword_id: Annotated[
        str | None,
        typer.Option("--hotword-id", help="Tencent ASR HotwordId."),
    ] = None,
    hotword_list: Annotated[
        str | None,
        typer.Option(
            "--hotword-list",
            help='Tencent ASR temporary HotwordList, for example "腾讯云|10,ASR|11".',
        ),
    ] = None,
    customization_id: Annotated[
        str | None,
        typer.Option("--customization-id", help="Tencent ASR CustomizationId."),
    ] = None,
    emotion_recognition: Annotated[
        int | None,
        typer.Option("--emotion-recognition", help="Tencent ASR EmotionRecognition."),
    ] = None,
    emotional_energy: Annotated[
        int | None,
        typer.Option("--emotional-energy", help="Tencent ASR EmotionalEnergy."),
    ] = None,
    convert_num_mode: Annotated[
        int | None,
        typer.Option("--convert-num-mode", help="Tencent ASR ConvertNumMode."),
    ] = None,
    filter_dirty: Annotated[
        int | None,
        typer.Option("--filter-dirty", help="Tencent ASR FilterDirty."),
    ] = None,
    filter_punc: Annotated[
        int | None,
        typer.Option("--filter-punc", help="Tencent ASR FilterPunc."),
    ] = None,
    filter_modal: Annotated[
        int | None,
        typer.Option("--filter-modal", help="Tencent ASR FilterModal."),
    ] = None,
    sentence_max_length: Annotated[
        int | None,
        typer.Option("--sentence-max-length", help="Tencent ASR SentenceMaxLength."),
    ] = None,
    keyword_lib_id: Annotated[
        list[str] | None,
        typer.Option(
            "--keyword-lib-id",
            help="Tencent ASR KeyWordLibIdList entry. Repeat for multiple IDs.",
        ),
    ] = None,
    replace_text_id: Annotated[
        str | None,
        typer.Option("--replace-text-id", help="Tencent ASR ReplaceTextId."),
    ] = None,
) -> None:
    """Transcribe a local audio file and print the result."""
    if not audio_path.exists():
        typer.echo(f"Audio file not found: {audio_path}", err=True)
        raise typer.Exit(code=1)
    speaker_role = _build_speaker_role(
        speaker_role_name,
        speaker_role_audio,
        speaker_role_audio_url,
    )
    if speaker_role_audio and not speaker_role_audio.exists():
        typer.echo(f"Speaker role audio file not found: {speaker_role_audio}", err=True)
        raise typer.Exit(code=1)
    try:
        provider_options = _build_provider_options(
            asr_mode=asr_mode,
            engine_model_type=engine_model_type,
            channel_num=channel_num,
            res_text_format=res_text_format,
            speaker_diarization=speaker_diarization,
            speaker_number=speaker_number,
            hotword_id=hotword_id,
            hotword_list=hotword_list,
            customization_id=customization_id,
            emotion_recognition=emotion_recognition,
            emotional_energy=emotional_energy,
            convert_num_mode=convert_num_mode,
            filter_dirty=filter_dirty,
            filter_punc=filter_punc,
            filter_modal=filter_modal,
            sentence_max_length=sentence_max_length,
            keyword_lib_id=keyword_lib_id,
            replace_text_id=replace_text_id,
        )
        result = asyncio.run(
            _transcribe(audio_path, provider, speaker_role, provider_options)
        )
    except SpeechTranscriberError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    rendered = _render_result(result, output)
    if output_file:
        written_path = _write_output_file(
            output_file,
            audio_path=audio_path,
            output_format=output,
            content=rendered,
        )
        typer.echo(f"Wrote transcript to: {written_path}")
        return

    typer.echo(rendered)


def _render_result(result: TranscriptResult, output: str) -> str:
    if output == "text":
        return result.text
    if output != "json":
        typer.echo(f"Unsupported output format: {output}", err=True)
        raise typer.Exit(code=1)
    return result.model_dump_json()


def _write_output_file(
    output_file: Path,
    *,
    audio_path: Path,
    output_format: str,
    content: str,
) -> Path:
    output_path = _resolve_output_path(output_file, audio_path, output_format)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{content}\n", encoding="utf-8")
    return output_path


def _resolve_output_path(
    output_file: Path,
    audio_path: Path,
    output_format: str,
) -> Path:
    if output_file.is_dir() or not output_file.suffix:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
        extension = "txt" if output_format == "text" else output_format
        return output_file / f"{timestamp}-{audio_path.name}.{extension}"
    return output_file


def _build_speaker_role(
    name: str | None,
    audio_path: Path | None,
    audio_url: str | None,
) -> SpeakerRole | None:
    if not any([name, audio_path, audio_url]):
        return None
    if not name:
        typer.echo(
            "--speaker-role-name is required for speaker role separation",
            err=True,
        )
        raise typer.Exit(code=1)
    if bool(audio_path) == bool(audio_url):
        typer.echo(
            "--speaker-role-name requires --speaker-role-audio or "
            "--speaker-role-audio-url, but not both",
            err=True,
        )
        raise typer.Exit(code=1)
    return SpeakerRole(name=name, audio_path=audio_path, audio_url=audio_url)


def _build_provider_options(**values: Any) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        options[key] = value
    return options


async def _transcribe(
    audio_path: Path,
    provider: str | None,
    speaker_role: SpeakerRole | None,
    provider_options: dict[str, Any] | None = None,
) -> TranscriptResult:
    settings = Settings()
    transcriber = get_transcriber(settings, provider)
    provider_name = provider or settings.default_provider
    return await transcriber.transcribe(
        audio_path,
        TranscribeOptions(
            provider=provider_name,
            speaker_role=speaker_role,
            provider_options=provider_options or {},
        ),
    )
