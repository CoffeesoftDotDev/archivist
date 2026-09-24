from pathlib import Path

import pytest

from archivist.cli.prompts import MergePrompt

ZIP, FOLDER = Path("photos.zip"), Path("photos")


def prompt_with(*answers: str) -> tuple[MergePrompt, list[str], list[str]]:
    """A MergePrompt fed with answers; returns it with the questions asked and the messages shown."""
    questions, messages = [], []
    replies = iter(answers)

    def ask(question: str) -> str:
        questions.append(question)
        try:
            return next(replies)
        except StopIteration:
            raise EOFError from None

    return MergePrompt(ask=ask, say=messages.append), questions, messages


@pytest.mark.parametrize(("answer", "expected"), [("y", True), ("YES", True), ("n", False), ("no", False), ("", False)])
def test_single_answers(answer, expected):
    prompt, questions, _ = prompt_with(answer)
    assert prompt(ZIP, FOLDER) is expected
    assert 'photos.zip: folder "photos" already exists' in questions[0]
    assert "[y]es / [n]o / [a]ll / [s]kip all" in questions[0]


@pytest.mark.parametrize(("answer", "expected"), [("a", True), ("all", True), ("s", False), ("skip all", False)])
def test_all_and_skip_all_answer_every_later_question(answer, expected):
    prompt, questions, _ = prompt_with(answer)
    assert [prompt(ZIP, FOLDER) for _ in range(3)] == [expected] * 3
    assert len(questions) == 1


def test_yes_and_no_are_asked_again_for_the_next_archive():
    prompt, questions, _ = prompt_with("y", "n")
    assert [prompt(ZIP, FOLDER), prompt(ZIP, FOLDER)] == [True, False]
    assert len(questions) == 2


def test_an_unknown_answer_asks_again():
    prompt, questions, messages = prompt_with("maybe", "y")
    assert prompt(ZIP, FOLDER) is True
    assert len(questions) == 2
    assert messages == ["Please answer y, n, a or s."]


def test_closed_input_means_no_for_every_archive():
    prompt, questions, _ = prompt_with()
    assert [prompt(ZIP, FOLDER), prompt(ZIP, FOLDER)] == [False, False]
    assert len(questions) == 1
