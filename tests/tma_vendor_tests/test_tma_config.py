"""Public settings and CLI failure contracts."""
import json
from dataclasses import replace

import pytest

from toutemonannee.cli import main
from toutemonannee.cli.parser import parse_config
from toutemonannee.core import Config, ExportError
from toutemonannee.core.logger import setup_logging
from toutemonannee.workflow import WorkflowBuilder


def test_precedence_and_additive_destinations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "appsettings.json").write_text(json.dumps({
        "Destination": "json", "Resolution": "1280x720", "ReuseSession": False,
        "Immich": {"Url": "https://photos.example", "ApiKey": "private", "Album": "School"},
    }))
    config = parse_config(["--destination", "cli", "--res", "3440x1440", "--immich", "--no-local"],
                          environ={"TMA_Destination": "env", "TMA_Resolution": "3840x2160"})
    assert str(config.destination) == "cli"
    assert config.viewport == {"width": 3440, "height": 1440}
    assert config.immich_enabled and config.no_local and not config.reuse_session
    assert not parse_config([], environ={}).immich_enabled
    assert "private" not in repr(config)


@pytest.mark.parametrize("argv", [
    ["--no-local"], ["--res", "1080p"], ["--page-size", "0"], ["--page-size", "1.5"],
    ["--request-timeout-seconds", "3601"], ["--reuse-session", "maybe"],
    ["--immich"], ["--destination", ""], ["--log-level", "bad"],
    ["--journal-id", "bad"], ["--local-only"], ["--unknown=private"],
    ["--config", "missing.json"], ["--immich=false", "--no-local=true"],
])
def test_invalid_cli_is_sanitized_before_browser(argv, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(WorkflowBuilder, "build", lambda self: pytest.fail("browser workflow must not start"))
    assert main(argv) == 2
    output = capsys.readouterr()
    assert "private" not in output.out + output.err


@pytest.mark.parametrize("url", [
    "http://photos.example", "https://user:private@example.com", "https://example.com?key=private",
    "https://example.com#private", "https://example.com:invalid", "https://example.com\\@evil.com",
])
def test_rejects_insecure_immich_without_echoing_url(url):
    with pytest.raises(ExportError) as error:
        replace(Config(), immich_enabled=True, immich_url=url, immich_api_key="key", immich_album="School").validate()
    assert url not in str(error.value)


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080", "2560x1080", "3440x1440", "3840x2160"])
def test_viewport_presets(resolution):
    config = replace(Config(), resolution=resolution)
    config.validate()
    assert "x".join(str(v) for v in config.viewport.values()) == resolution


def test_json_types_legacy_key_and_explicit_boolean_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert not parse_config(["--screenshot-restricted=false"], environ={"TMA_ScreenshotRestricted": "true"}).screenshot_restricted
    with pytest.raises(ExportError, match="LocalOnly"):
        parse_config([], environ={"TMA_LocalOnly": "true"})
    for data in ({"PageSize": True}, {"PageSize": 1.5}, {"Destination": True}, [], {"Resolution": []}):
        (tmp_path / "appsettings.json").write_text(json.dumps(data))
        with pytest.raises(ExportError):
            parse_config([], environ={})


def test_module_help_and_build_have_no_operational_effects(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["--help"]) == 0
    assert "Python/uv" in capsys.readouterr().out
    workflow = WorkflowBuilder(Config(destination=tmp_path / "not-created")).build()
    assert not list(tmp_path.iterdir())
    assert workflow.config.destination == tmp_path / "not-created"


def test_daily_logs_retain_fourteen_across_new_process_invocations(tmp_path):
    for day in range(1, 21):
        (tmp_path / f"export-202601{day:02d}.log").touch()
    unrelated = tmp_path / "export-important.log"
    unrelated.write_text("keep")
    logger = setup_logging(Config(log_path=tmp_path / "export-.log", log_level="Fatal"))
    try:
        files = [p for p in tmp_path.glob("export-*.log") if p.name != unrelated.name]
        assert len(files) == 14
        assert any("Initializing export operation logging." in p.read_text() for p in files)
        assert unrelated.read_text() == "keep"
    finally:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
