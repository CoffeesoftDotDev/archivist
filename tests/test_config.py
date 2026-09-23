from pathlib import Path

import pytest

from archivist.core import APPLEDOUBLE_MAX_SIZE, Config


def test_defaults_clean_everything_and_delete_permanently():
    config = Config()
    assert (config.delete_zip, config.appledouble, config.eadir) == (True, True, True)
    assert (config.ds_store, config.thumbs_db, config.desktop_ini) == (True, True, True)
    assert (config.force_readonly, config.send_to_bin, config.dry_run) == (False, False, False)
    assert config.appledouble_max_size == APPLEDOUBLE_MAX_SIZE
    assert config.parent_folder is None and config.log_file is None


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
        "ARCHIVIST_MAX_SIZE": "4096",
        "ARCHIVIST_FORCE_READONLY_DELETION": "TRUE",
        "ARCHIVIST_SEND_TO_BIN": "true",
        "ARCHIVIST_DRY_RUN": "true",
        "ARCHIVIST_LOG_FILE": "run.log",
    }
    assert Config.from_env(env) == Config(
        parent_folder=Path("photos"),
        delete_zip=False,
        appledouble=False,
        eadir=False,
        ds_store=False,
        thumbs_db=False,
        desktop_ini=False,
        appledouble_max_size=4096,
        force_readonly=True,
        send_to_bin=True,
        dry_run=True,
        log_file="run.log",
    )


def test_empty_variables_keep_defaults():
    env = {"ARCHIVIST_MAX_SIZE": "", "ARCHIVIST_PARENT_FOLDER": " ", "ARCHIVIST_DRY_RUN": ""}
    assert Config.from_env(env) == Config()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", ""), ("false", None), ("", None), ("logs/run.log", "logs/run.log")],
)
def test_log_file_variable(raw, expected):
    assert Config.from_env({"ARCHIVIST_LOG_FILE": raw}).log_file == expected


@pytest.mark.parametrize(("name", "value"), [("ARCHIVIST_DRY_RUN", "maybe"), ("ARCHIVIST_MAX_SIZE", "big")])
def test_invalid_values_name_the_variable(name, value):
    with pytest.raises(ValueError, match=name):
        Config.from_env({name: value})
