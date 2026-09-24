"""Interactive questions asked during a run."""
from collections.abc import Callable
from pathlib import Path

CHOICES = "[y]es / [n]o / [a]ll / [s]kip all"


class MergePrompt:
    """
    Asks whether to extract an archive into its existing folder (a ConfirmMerge callback).
    "all" and "skip all" answer every later question; an empty answer or a closed input means no.
    """

    def __init__(self, ask: Callable[[str], str] | None = None, say: Callable[[str], None] | None = None):
        # Looked up on each call, so input() and print() can be swapped out (tests, other front ends).
        self.ask = ask or (lambda question: input(question))
        self.say = say or (lambda message: print(message))
        self.remembered: bool | None = None

    def __call__(self, zip_path: Path, folder: Path) -> bool:
        if self.remembered is not None:
            return self.remembered
        question = (
            f'{zip_path.name}: folder "{folder.name}" already exists. '
            f"Extract into it and overwrite files with the same name? {CHOICES}: "
        )
        while True:
            try:
                answer = self.ask(question).strip().lower()
            except EOFError:
                self.remembered = False
                return False
            if answer in ("", "n", "no"):
                return False
            if answer in ("y", "yes"):
                return True
            if answer in ("a", "all"):
                self.remembered = True
                return True
            if answer in ("s", "skip all"):
                self.remembered = False
                return False
            self.say("Please answer y, n, a or s.")
