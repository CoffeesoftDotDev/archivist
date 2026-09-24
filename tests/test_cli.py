import io
import re
import sys
from pathlib import Path

import pytest

from archivist import cli
from archivist.core import Config


def test_flag_beats_env_variable_which_beats_default():
    env = {"ARCHIVIST_MAX_SIZE": "4096", "ARCHIVIST_LEAVE_ZIP": "true"}
    config = cli.parse_config(["--max-size", "100"], environ=env)
    assert config.appledouble_max_size == 100
    assert config.leave_zip is True
    assert config.leave_eadir is False


def test_every_flag_maps_to_a_config_field():
    argv = [
        "--parent-folder", "photos", "--leave-zip", "--leave-appledouble", "--leave-eadir",
        "--leave-ds-store", "--leave-thumbs-db", "--leave-desktop-ini",
        "--max-size", "10", "--force", "--send-to-bin", "--apply",
        "--log-file", "run.log",
    ]
    assert cli.parse_config(argv, environ={}) == Config(
        parent_folder=Path("photos"),
        leave_zip=True,
        leave_appledouble=True,
        leave_eadir=True,
        leave_ds_store=True,
        leave_thumbs_db=True,
        leave_desktop_ini=True,
        appledouble_max_size=10,
        force_readonly=True,
        send_to_bin=True,
        apply=True,
        log_file="run.log",
    )


def test_apply_comes_from_the_flag_or_the_variable():
    assert cli.parse_config([], environ={}).apply is False
    assert cli.parse_config(["--apply"], environ={}).apply is True
    assert cli.parse_config([], environ={"ARCHIVIST_APPLY": "true"}).apply is True


def test_old_dry_run_flag_still_works_and_beats_the_apply_variable():
    assert cli.parse_config(["--dry-run"], environ={}).apply is False
    assert cli.parse_config(["--dry-run"], environ={"ARCHIVIST_APPLY": "true"}).apply is False


def test_apply_and_dry_run_cannot_be_combined(capsys):
    for environ in ({}, {"ARCHIVIST_APPLY": "true"}):  # the variable makes --apply look like its default
        for argv in (["--apply", "--dry-run"], ["--dry-run", "--apply"]):
            with pytest.raises(SystemExit) as exit_info:
                cli.parse_config(argv, environ=environ)
            assert exit_info.value.code == 2
            assert "not allowed with argument" in capsys.readouterr().err


def test_dry_run_is_hidden_from_help(capsys):
    with pytest.raises(SystemExit):
        cli.parse_config(["--help"], environ={})
    help_text = capsys.readouterr().out
    assert "--apply" in help_text and "--dry-run" not in help_text


@pytest.mark.parametrize(
    ("argv", "environ", "expected"),
    [
        ([], {}, []),
        (["--apply"], {"ARCHIVIST_APPLY": "true"}, []),
        (["--dry-run"], {}, ["--dry-run is no longer needed"]),
        ([], {"ARCHIVIST_DRY_RUN": "false"}, ["ARCHIVIST_DRY_RUN is no longer used and was ignored"]),
    ],
)
def test_legacy_notes(argv, environ, expected):
    notes = cli.parser.legacy_notes(argv, environ)
    assert len(notes) == len(expected)
    for note, start in zip(notes, expected):
        assert note.startswith(start)


def test_log_file_without_path_means_default_report():
    assert cli.parse_config([], environ={}).log_file == ""
    assert cli.parse_config(["--log-file"], environ={}).log_file == ""


def test_no_log_file_disables_the_report_file():
    assert cli.parse_config(["--no-log-file"], environ={}).log_file is None
    env = {"ARCHIVIST_LOG_FILE": "run.log"}
    assert cli.parse_config(["--no-log-file"], environ=env).log_file is None
    assert cli.parse_config(["--log-file"], environ={"ARCHIVIST_LOG_FILE": "false"}).log_file == ""


def test_empty_parent_folder_means_not_given():
    assert cli.parse_config(["--parent-folder", ""], environ={}).parent_folder is None
    env = {"ARCHIVIST_PARENT_FOLDER": "photos"}
    assert cli.parse_config(["--parent-folder", " "], environ=env).parent_folder == Path("photos")


def test_invalid_env_variable_exits_with_its_name():
    with pytest.raises(SystemExit, match="ARCHIVIST_LEAVE_ZIP"):
        cli.parse_config([], environ={"ARCHIVIST_LEAVE_ZIP": "maybe"})


def test_missing_folder_exits_with_code_2(tmp_path):
    assert cli.main(["--parent-folder", str(tmp_path / "missing")]) == 2


def test_no_folder_and_no_terminal_exits_with_code_2(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    assert cli.main([]) == 2


def test_report_goes_to_the_console_and_the_report_file_by_default(tmp_path, make_zip, capsys):
    make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    assert cli.main(["--parent-folder", str(tmp_path), "--apply"]) == 0
    assert (tmp_path / "photos" / "a.jpg").is_file()
    for output in (capsys.readouterr().out, (tmp_path / "report.log").read_text(encoding="utf-8")):
        assert "Operation completed" in output
        assert re.search(r"ZIP files extracted +: 1", output)


def test_a_run_without_apply_changes_nothing(tmp_path, make_zip, listing, capsys):
    make_zip(tmp_path / "photos.zip", {"a.jpg": "x", ".DS_Store": "ds"})
    (tmp_path / "Thumbs.db").write_text("thumbs")
    before = listing(tmp_path)
    assert cli.main(["--parent-folder", str(tmp_path), "--no-log-file"]) == 0
    assert listing(tmp_path) == before
    output = capsys.readouterr().out
    assert "Dry run completed: nothing was changed" in output
    assert "Run again with --apply to make these changes." in output


def test_leftover_dry_run_variable_is_ignored_with_a_warning(tmp_path, make_zip, monkeypatch, capsys):
    zip_path = make_zip(tmp_path / "photos.zip", {"a.jpg": "x"})
    monkeypatch.setenv("ARCHIVIST_DRY_RUN", "false")  # used to mean "change files"
    assert cli.main(["--parent-folder", str(tmp_path), "--no-log-file"]) == 0
    assert zip_path.exists() and not (tmp_path / "photos").exists()
    assert "ARCHIVIST_DRY_RUN is no longer used and was ignored" in capsys.readouterr().out


def test_no_log_file_writes_no_report_file(tmp_path):
    assert cli.main(["--parent-folder", str(tmp_path), "--no-log-file"]) == 0
    assert not (tmp_path / "report.log").exists()


# Where the report ends up, for each state of the log file option, set by flag or by variable (#3).
LOG_FILE_CASES = {
    "default": ([], None, "root/report.log"),
    "--log-file without a path": (["--log-file"], "true", "root/report.log"),
    "custom file": (["--log-file", "{tmp}/logs/run.log"], "{tmp}/logs/run.log", "logs/run.log"),
    "existing folder": (["--log-file", "{tmp}/existing"], "{tmp}/existing", "existing/report.log"),
    "folder by trailing separator": (["--log-file", "{tmp}/new/"], "{tmp}/new/", "new/report.log"),
    "turned off": (["--no-log-file"], "false", None),
}


@pytest.mark.parametrize("source", ["flag", "variable"])
@pytest.mark.parametrize("case", LOG_FILE_CASES)
def test_report_file_location(tmp_path, monkeypatch, case, source):
    flags, variable, expected = LOG_FILE_CASES[case]
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "existing").mkdir()
    fill = lambda value: value.replace("{tmp}", str(tmp_path))
    argv = ["--parent-folder", str(root)]
    if source == "flag":
        argv += [fill(flag) for flag in flags]
    elif variable is not None:
        monkeypatch.setenv("ARCHIVIST_LOG_FILE", fill(variable))

    assert cli.main(argv) == 0

    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.log"))
    assert written == ([expected] if expected else [])
    if expected:
        assert "Archivist run started" in (tmp_path / expected).read_text(encoding="utf-8")


def test_flag_beats_the_log_file_variable_in_both_directions(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVIST_LOG_FILE", "false")
    assert cli.main(["--parent-folder", str(tmp_path), "--log-file"]) == 0
    assert (tmp_path / "report.log").is_file()

    monkeypatch.setenv("ARCHIVIST_LOG_FILE", str(tmp_path / "elsewhere.log"))
    assert cli.main(["--parent-folder", str(tmp_path), "--no-log-file"]) == 0
    assert not (tmp_path / "elsewhere.log").exists()


def test_log_file_and_no_log_file_cannot_be_combined(capsys):
    # A bare --log-file gives "", the same value as the default: the case older argparse missed.
    for argv in (["--log-file", "--no-log-file"], ["--no-log-file", "--log-file"], ["--log-file", "x.log", "--no-log-file"]):
        with pytest.raises(SystemExit) as exit_info:
            cli.parse_config(argv, environ={})
        assert exit_info.value.code == 2
        assert "not allowed with argument" in capsys.readouterr().err


@pytest.fixture
def existing_folder(tmp_path, make_zip, write_file):
    make_zip(tmp_path / "photos.zip", {"a.jpg": "new"})
    write_file(tmp_path / "photos" / "a.jpg", "old")
    return tmp_path


def test_terminal_run_asks_before_extracting_into_an_existing_folder(existing_folder, monkeypatch):
    questions = []
    monkeypatch.setattr("archivist.cli.entrypoint.is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda question: questions.append(question) or "y")
    assert cli.main(["--parent-folder", str(existing_folder), "--no-log-file", "--apply"]) == 0
    assert len(questions) == 1
    assert (existing_folder / "photos" / "a.jpg").read_text() == "new"


@pytest.mark.parametrize(
    ("interactive", "extra"),
    [(False, ["--apply"]), (True, [])],
    ids=["applied without a terminal", "dry run in a terminal"],
)
def test_no_question_without_a_terminal_or_in_a_dry_run(existing_folder, monkeypatch, interactive, extra):
    monkeypatch.setattr("archivist.cli.entrypoint.is_interactive", lambda: interactive)
    monkeypatch.setattr("builtins.input", lambda question: pytest.fail(f"unexpected question: {question}"))
    assert cli.main(["--parent-folder", str(existing_folder), "--no-log-file", *extra]) == 0
    assert (existing_folder / "photos" / "a.jpg").read_text() == "old"
