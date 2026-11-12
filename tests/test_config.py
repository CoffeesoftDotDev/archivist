from pathlib import Path

import pytest

from archivist.core import APPLEDOUBLE_MAX_SIZE, Config
from archivist.core.config import parse_log_file


def summary_value(config: Config, label: str) -> str:
    """Find a grouped summary value independently of column padding."""
    for line in config.summary().splitlines():
        if line.startswith("|- "):
            name, value = line[3:].split(" : ", 1)
            if name.strip() == label:
                return value
    raise AssertionError(f"Missing summary label: {label}")


def test_defaults_clean_everything_and_delete_permanently():
    config = Config()
    assert (config.leave_zip, config.leave_appledouble, config.leave_eadir) == (False, False, False)
    assert (config.leave_ds_store, config.leave_thumbs_db, config.leave_desktop_ini) == (False, False, False)
    assert (config.force_readonly, config.send_to_bin, config.apply) == (False, False, False)
    assert config.remove_macosx is False
    assert config.appledouble_max_size == APPLEDOUBLE_MAX_SIZE
    assert config.parent_folder is None and config.log_file == ""


def test_from_env_without_variables_keeps_defaults():
    assert Config.from_env({}) == Config()


def test_from_env_reads_every_variable():
    env = {
        "ARCHIVIST_PARENT_FOLDER": "photos",
        "ARCHIVIST_LEAVE_ZIP": "yes",
        "ARCHIVIST_LEAVE_APPLEDOUBLE": "1",
        "ARCHIVIST_LEAVE_EADIR": "on",
        "ARCHIVIST_LEAVE_DS_STORE": "true",
        "ARCHIVIST_LEAVE_THUMBS_DB": "true",
        "ARCHIVIST_LEAVE_DESKTOP_INI": "true",
        "ARCHIVIST_REMOVE_MACOSX": "true",
        "ARCHIVIST_MAX_SIZE": "4096",
        "ARCHIVIST_FORCE_READONLY_DELETION": "TRUE",
        "ARCHIVIST_SEND_TO_BIN": "true",
        "ARCHIVIST_APPLY": "true",
        "ARCHIVIST_LOG_FILE": "run.log",
    }
    assert Config.from_env(env) == Config(
        parent_folder=Path("photos"),
        leave_zip=True,
        leave_appledouble=True,
        leave_eadir=True,
        leave_ds_store=True,
        leave_thumbs_db=True,
        leave_desktop_ini=True,
        remove_macosx=True,
        appledouble_max_size=4096,
        force_readonly=True,
        send_to_bin=True,
        apply=True,
        log_file="run.log",
    )


def test_dry_run_variable_is_ignored():
    assert Config.from_env({"ARCHIVIST_DRY_RUN": "false"}) == Config()


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize(
    "actions",
    [{}, {"extract_zip": True}, {"list_images": True}, {"move_images": True}, {"move_images": True, "copy": True}],
)
def test_summary_places_mode_immediately_after_parent_folder(apply, actions):
    lines = Config(parent_folder=Path("photos"), apply=apply, **actions).summary().splitlines()
    assert lines[0] == "Current Config"
    assert lines[1].startswith("|- Parent Folder") and lines[1].endswith(" : photos")
    assert lines[2].startswith("|- Mode ")
    assert lines[2].split(" : ", 1)[1].startswith("APPLY" if apply else "DRY-RUN")
    assert sum(line.startswith("|- Mode ") for line in lines) == 1


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (Config(), "DRY-RUN (read-only)"),
        (Config(apply=True), "APPLY (write)"),
        (Config(list_images=True, apply=True), "APPLY (read-only; inventory only)"),
        (Config(list_images=True, extract_zip=True, apply=True), "APPLY (write; approval required)"),
        (Config(move_images=True, apply=True), "APPLY (write; approval required)"),
    ],
)
def test_summary_describes_the_effective_mode(config, expected):
    assert summary_value(config, "Mode") == expected


@pytest.mark.parametrize("apply", [False, True])
def test_summary_separates_current_settings_from_apply_only_actions(apply):
    current, actions = Config(apply=apply).summary().split("\n\n")

    assert current.startswith("Current Config\n|- Parent Folder")
    assert "|- Log to File" in current
    assert "|- AppleDouble Rules" in current
    assert "Force-Delete" not in current
    assert "Send to Bin" not in current
    assert actions.startswith("Only with --apply\n|- Extract ZIPs")
    assert "Read-only deletion" not in actions
    assert "|- Send to Bin" in actions.splitlines()[-2]
    assert "|- Force-Delete (including Read-Only)" in actions.splitlines()[-1]
    for section in (current, actions):
        assert len({line.index(" : ") for line in section.splitlines()[1:]}) == 1


def test_summary_accepts_resolved_parent_and_report_paths(tmp_path):
    root = tmp_path / "photos"
    report_file = root / "report.log"
    summary = Config().summary(parent_folder=root, report_file=report_file)
    current, actions = summary.split("\n\n")

    assert f" : {root}" in current
    assert "(prompt)" not in summary
    assert "|- Report File" in current and f" : {report_file}" in current
    assert "Report File" not in actions
    assert "Report File" not in Config(log_file=None).summary()


def test_summary_keeps_appledouble_rules_separate_from_action_status():
    config = Config(appledouble_max_size=4096)
    assert summary_value(config, "AppleDouble Rules") == "._ files <= 4096 bytes; ._ folders without visible files"
    assert summary_value(config, "Remove AppleDouble") == "ENABLED (dry-run : read-only)"


def test_summary_shows_opt_in_macosx_cleanup():
    assert "|- Remove _MACOSX / __MACOSX" in Config().summary()
    assert summary_value(Config(), "Remove _MACOSX / __MACOSX") == "DISABLED"
    assert summary_value(Config(remove_macosx=True), "Remove _MACOSX / __MACOSX") == "ENABLED (dry-run : read-only)"


def test_summary_uses_consistent_disabled_label_for_file_logging():
    assert summary_value(Config(log_file=None), "Log to File") == "DISABLED"


def test_empty_variables_keep_defaults():
    env = {"ARCHIVIST_MAX_SIZE": "", "ARCHIVIST_PARENT_FOLDER": " ", "ARCHIVIST_APPLY": ""}
    assert Config.from_env(env) == Config()


@pytest.mark.parametrize(("apply", "mode"), [(False, "dry-run : read-only"), (True, "apply : write")])
@pytest.mark.parametrize(
    ("field", "label", "default_enabled"),
    [
        ("leave_zip", "Delete ZIPs", True),
        ("force_readonly", "Force-Delete (including Read-Only)", False),
        ("send_to_bin", "Send to Bin", False),
        ("leave_appledouble", "Remove AppleDouble", True),
        ("leave_ds_store", "Remove .DS_Store", True),
        ("leave_thumbs_db", "Remove Thumbs.db", True),
        ("leave_desktop_ini", "Remove desktop.ini", True),
        ("leave_eadir", "Remove @eaDir", True),
        ("remove_macosx", "Remove _MACOSX / __MACOSX", False),
    ],
)
def test_summary_labels_each_enabled_action_with_its_mode(apply, mode, field, label, default_enabled):
    for selected in (False, True):
        config = Config(apply=apply, **{field: selected})
        enabled = not selected if default_enabled else selected
        status = f"ENABLED ({mode})" if enabled else "DISABLED"
        assert summary_value(config, label) == status


@pytest.mark.parametrize("apply", [False, True])
def test_extraction_only_summary_does_not_claim_standard_cleanup_is_enabled(apply):
    config = Config(extract_zip=True, remove_macosx=True, apply=apply)
    lines = config.summary().splitlines()
    standard_cleanup = [
        line for line in lines if line.startswith("|- Remove ") and not line.startswith("|- Remove _MACOSX")
    ]
    assert len(standard_cleanup) == 5
    assert all(": DISABLED" in line for line in standard_cleanup)
    assert summary_value(config, "Remove _MACOSX / __MACOSX").startswith("ENABLED")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", ""), ("false", None), ("off", None), ("", ""), ("logs/run.log", "logs/run.log")],
)
def test_log_file_variable(raw, expected):
    assert Config.from_env({"ARCHIVIST_LOG_FILE": raw}).log_file == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("TRUE", ""), (" yes ", ""), ("1", ""), ("", ""), ("  ", ""), ("No", None), ("0", None), (" D:\\logs\\ ", "D:\\logs\\")],
)
def test_parse_log_file(raw, expected):
    assert parse_log_file(raw) == expected


@pytest.mark.parametrize(("name", "value"), [("ARCHIVIST_APPLY", "maybe"), ("ARCHIVIST_MAX_SIZE", "big")])
def test_invalid_values_name_the_variable(name, value):
    with pytest.raises(ValueError, match=name):
        Config.from_env({name: value})
