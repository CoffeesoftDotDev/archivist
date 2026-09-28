"""Builds the workflow from the config (Builder pattern)."""
from ..core import Config
from ..services import ConfirmImages, ConfirmMerge, ImageRun, MetadataCleaner, ZipExtractor
from ..utils import make_remover
from .runner import Workflow
from .image_steps import ConfirmImagePlan, ExtractImageArchives, ImageWorkflow, ListImages, TransferImages
from .steps import (
    ExtractArchives,
    RemoveAppleDoubleFiles,
    RemoveAppleDoubleFolders,
    RemoveEaDirFolders,
    RemoveFilesNamed,
    Step,
)


class WorkflowBuilder:
    """Creates the services, then goes through the step sequence and keeps the steps the config enables."""

    def __init__(
        self, config: Config, confirm_merge: ConfirmMerge | None = None,
        *, confirm_images: ConfirmImages | None = None,
    ):
        self.config = config
        self.confirm_merge = confirm_merge  # asked per archive whose folder exists; None never merges
        self.confirm_images = confirm_images

    def build(self) -> Workflow:
        config = self.config
        config.validate_actions()
        if config.image_workflow:
            context = ImageRun(config, self.confirm_images)
            steps: list[Step] = [ListImages(context)]
            if config.apply and (config.move_images or config.extract_zip):
                steps += [ConfirmImagePlan(context), ExtractImageArchives(context), TransferImages(context)]
            return ImageWorkflow(steps, context)
        remover = make_remover(
            dry_run=not config.apply,
            to_trash=config.send_to_bin,
            force_readonly=config.force_readonly,
        )
        extractor = ZipExtractor(
            remover, delete_archive=not config.leave_zip, dry_run=not config.apply, confirm_merge=self.confirm_merge
        )
        cleaner = MetadataCleaner(remover)
        if config.extract_zip:
            return Workflow([ExtractArchives(extractor)], dry_run=not config.apply)

        # (enabled, step) in run order; file steps come first so emptied ._ folders go too
        sequence: list[tuple[bool, Step]] = [
            (True, ExtractArchives(extractor)),
            (not config.leave_appledouble, RemoveAppleDoubleFiles(cleaner, config.appledouble_max_size)),
            (not config.leave_ds_store, RemoveFilesNamed(cleaner, ".DS_Store")),
            (not config.leave_thumbs_db, RemoveFilesNamed(cleaner, "Thumbs.db")),
            (not config.leave_desktop_ini, RemoveFilesNamed(cleaner, "desktop.ini")),
            (not config.leave_appledouble, RemoveAppleDoubleFolders(cleaner)),
            (not config.leave_eadir, RemoveEaDirFolders(cleaner)),
        ]
        return Workflow([step for enabled, step in sequence if enabled], dry_run=not config.apply)
