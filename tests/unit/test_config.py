"""Settings configuration tests."""

from __future__ import annotations

from pathlib import Path

from speech_transcriber.config import Settings


def test_settings_default_env_files_include_project_env_before_cwd_env() -> None:
    env_file = Settings.model_config["env_file"]

    assert isinstance(env_file, tuple)
    assert Path(env_file[0]).name == ".env"
    assert Path(env_file[0]).parent == Path(__file__).resolve().parents[2]
    assert env_file[1] == ".env"


def test_settings_load_project_env_when_cwd_is_elsewhere(
    tmp_path: Path, monkeypatch
) -> None:
    project_env = tmp_path / "project" / ".env"
    project_env.parent.mkdir()
    project_env.write_text("TENCENT_SECRET_ID=from_project_env\n", encoding="utf-8")

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", (project_env, ".env"))

    settings = Settings()

    assert settings.tencent_secret_id == "from_project_env"
