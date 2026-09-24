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
    assert config.delete_zip is False
    assert config.eadir is True


def test_every_flag_maps_to_a_config_field():
    argv = [
        "--parent-folder", "photos", "--leave-zip", "--leave-appledouble", "--leave-eadir",
        "--leave-ds-store", "--leave-thumbs-db", "--leave-desktop-ini",
        "--max-size", "10", "--force", "--send-to-bin", "--dry-run",
        "--log-file", "run.log",
    ]
    assert cli.parse_config(argv, environ={}) == Config(
        parent_folder=Path("photos"),
        delete_zip=False,
        appledouble=False,
        eadir=False,
        ds_store=False,
        thumbs_db=False,
        desktop_ini=False,
        appledouble_max_size=10,
        force_readonly=True,
        send_to_bin=True,
        dry_run=True,
        log_file="run.log",
    )


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
    assert cli.main(["--parent-folder", str(tmp_path)]) == 0
    assert (tmp_path / "photos" / "a.jpg").is_file()
    for output in (capsys.readouterr().out, (tmp_path / "report.log").read_text(encoding="utf-8")):
        assert "Operation completed" in output
        assert re.search(r"ZIP files extracted +: 1", output)


def test_no_log_file_writes_no_report_file(tmp_path):
    assert cli.main(["--parent-folder", str(tmp_path), "--no-log-file"]) == 0
    assert not (tmp_path / "report.log").exists()
