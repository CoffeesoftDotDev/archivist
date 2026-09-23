import pytest

from archivist.core import Config
from archivist.workflow import RemoveAppleDoubleFiles, Step, Workflow, WorkflowBuilder

EVERY_STEP = [
    "ExtractArchives",
    "RemoveAppleDoubleFiles",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "RemoveAppleDoubleFolders",
    "RemoveEaDirFolders",
]


def run(config: Config, root):
    return WorkflowBuilder(config).build().run(root)


def step_names(config: Config) -> list[str]:
    """Class names, or the file name for RemoveFilesNamed steps."""
    return [getattr(step, "filename", type(step).__name__) for step in WorkflowBuilder(config).build().steps]


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (Config(), EVERY_STEP),
        (Config(appledouble=False), ["ExtractArchives", ".DS_Store", "Thumbs.db", "desktop.ini", "RemoveEaDirFolders"]),
        (
            Config(eadir=False, thumbs_db=False),
            ["ExtractArchives", "RemoveAppleDoubleFiles", ".DS_Store", "desktop.ini", "RemoveAppleDoubleFolders"],
        ),
        (
            Config(appledouble=False, eadir=False, ds_store=False, thumbs_db=False, desktop_ini=False),
            ["ExtractArchives"],
        ),
    ],
)
def test_builder_keeps_the_steps_the_config_enables_in_order(config, expected):
    assert step_names(config) == expected


def test_builder_gives_the_size_limit_to_the_appledouble_files_step():
    steps = WorkflowBuilder(Config(appledouble_max_size=4096)).build().steps
    files_step = next(step for step in steps if isinstance(step, RemoveAppleDoubleFiles))
    assert files_step.max_size == 4096
    assert "4096 bytes" in files_step.title


class Recorder(Step):
    def __init__(self, name: str, calls: list[str]):
        self.title = f"step {name}"
        self.name = name
        self.calls = calls

    def run(self, root):
        self.calls.append(self.name)
        return {f"{self.name} count": len(self.calls)}


def test_workflow_runs_steps_in_order_and_merges_their_report_lines(tmp_path, logs):
    calls = []
    report = Workflow([Recorder("a", calls), Recorder("b", calls)]).run(tmp_path)
    assert calls == ["a", "b"]
    assert report == {"a count": 1, "b count": 2}
    assert logs.text.index("step a") < logs.text.index("step b")


@pytest.fixture
def photos(tmp_path, make_zip, write_file):
    make_zip(
        tmp_path / "album.zip",
        {"a.jpg": "x", "._a.jpg": "meta", ".DS_Store": "ds", "inner.zip": {"b.jpg": "y"}},
    )
    write_file(tmp_path / "@eaDir" / "thumb.jpg")
    write_file(tmp_path / "._empty" / ".x")
    write_file(tmp_path / "._empty" / "Thumbs.db")
    write_file(tmp_path / "desktop.ini")
    return tmp_path


def test_run_extracts_nested_zips_and_cleans_metadata(photos, listing):
    assert run(Config(), photos) == {
        "ZIP files found": 2,
        "ZIP files extracted": 2,
        "._ files removed": 1,
        ".DS_Store files removed": 1,
        "Thumbs.db files removed": 1,
        "desktop.ini files removed": 1,
        "._ folders removed": 1,
        "@eaDir folders removed": 1,
    }
    assert listing(photos) == ["album", "album/a.jpg", "album/inner", "album/inner/b.jpg"]


def test_dry_run_changes_nothing(photos, listing, logs):
    before = listing(photos)
    report = run(Config(dry_run=True), photos)
    assert listing(photos) == before
    # Nothing is removed, so files inside album.zip are not counted and ._empty still holds its Thumbs.db.
    assert report == {
        "ZIP files found": 1,
        "ZIP files extracted": 1,
        "._ files removed": 0,
        ".DS_Store files removed": 0,
        "Thumbs.db files removed": 1,
        "desktop.ini files removed": 1,
        "._ folders removed": 0,
        "@eaDir folders removed": 1,
    }
    assert "Dry run completed: nothing was changed" in logs.text


def test_disabled_steps_leave_files_alone_and_stay_out_of_the_report(photos, listing):
    config = Config(
        delete_zip=False, appledouble=False, eadir=False, ds_store=False, thumbs_db=False, desktop_ini=False
    )
    report = run(config, photos)
    assert report == {"ZIP files found": 2, "ZIP files extracted": 2}
    kept = {"album.zip", "@eaDir", "._empty/Thumbs.db", "desktop.ini", "album/._a.jpg", "album/.DS_Store"}
    assert kept <= set(listing(photos))
