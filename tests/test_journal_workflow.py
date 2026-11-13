import builtins

import pytest

from archivist.cli import main, parse_config
from archivist.core import Config
from archivist.workflow import WorkflowBuilder
from archivist.workflow.journal_export import JournalExportWorkflow


def test_non_journal_builder_does_not_import_optional_exporter(monkeypatch):
    original_import = builtins.__import__

    def reject_exporter(name, *args, **kwargs):
        if name.startswith("toutemonannee"):
            raise AssertionError("the optional exporter must stay unloaded")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_exporter)
    assert WorkflowBuilder(Config()).build().steps


def test_journal_preview_never_opens_browser_or_creates_files(tmp_path, monkeypatch, capsys):
    original_import = builtins.__import__

    def reject_exporter(name, *args, **kwargs):
        if name.startswith("toutemonannee"):
            raise AssertionError("preview must not load the exporter")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_exporter)
    result = main([
        "--export-journal", "--journal-destination", str(tmp_path / "not-created"), "--no-log-file",
    ])

    assert result == 0
    assert not list(tmp_path.iterdir())
    output = capsys.readouterr().out
    assert "Dry run: no browser, network, report, or destination changes" in output


@pytest.mark.parametrize(
    "arguments",
    [
        ["--extract-zip"],
        ["--move-images"],
        ["--destination", "photos"],
        ["--copy"],
        ["--filter", "JPG"],
        ["--leave-zip"],
        ["--leave-appledouble"],
        ["--leave-ds-store"],
        ["--max-size", "4096"],
        ["--leave-macosx"],
        ["--remove-macosx"],
        ["--send-to-bin"],
        ["--force"],
        ["--parent-folder", "photos"],
    ],
)
def test_journal_action_rejects_archive_image_and_cleanup_options(arguments):
    with pytest.raises(SystemExit, match="Invalid action configuration"):
        parse_config(["--export-journal", *arguments], environ={})


@pytest.mark.parametrize("option", ["--journal-destination", "--journal-config"])
def test_journal_settings_require_the_journal_action(option):
    with pytest.raises(SystemExit, match="require --export-journal"):
        parse_config([option, "settings.json"], environ={})


def test_journal_apply_dispatches_only_the_exporter_with_destination_override(
    tmp_path, monkeypatch,
):
    pytest.importorskip("httpx")
    pytest.importorskip("playwright")
    from toutemonannee import workflow as exporter_workflow

    calls = []

    class FakeExport:
        def run(self):
            calls.append("run")
            return 7

    class FakeBuilder:
        def __init__(self, export_config):
            calls.append(export_config)

        def build(self):
            return FakeExport()

    monkeypatch.setattr(exporter_workflow, "WorkflowBuilder", FakeBuilder)
    monkeypatch.setenv("TMA_ScreenshotRestricted", "true")
    archive = tmp_path / "preserved.zip"
    archive.write_bytes(b"synthetic archive")

    workflow = WorkflowBuilder(Config(
        export_journal=True, journal_destination=tmp_path / "export", apply=True, log_file=None,
    )).build()

    assert isinstance(workflow, JournalExportWorkflow)
    assert workflow.run() == 7
    assert len(calls) == 2 and calls[1] == "run"
    assert calls[0].destination == tmp_path / "export"
    assert calls[0].screenshot_restricted is True
    assert archive.read_bytes() == b"synthetic archive"
    assert not (tmp_path / "export").exists()


def test_missing_optional_browser_dependency_is_actionable_without_side_effects(tmp_path, monkeypatch, caplog):
    original_import = builtins.__import__

    def reject_playwright(name, *args, **kwargs):
        if name == "playwright.sync_api":
            raise ModuleNotFoundError("No module named 'playwright'", name="playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_playwright)
    workflow = JournalExportWorkflow(Config(
        export_journal=True, journal_destination=tmp_path / "export", apply=True, log_file=None,
    ))

    assert workflow.run() == 2
    assert "uv sync --extra toutemonannee" in caplog.text
    assert not list(tmp_path.iterdir())
