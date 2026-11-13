"""Pagination, strict schemas, dates and restricted viewer source observations."""
from dataclasses import replace
from datetime import date
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from tma_test_fixtures import JOURNAL, PHOTO, SOURCE
from toutemonannee.core import ExportError
from toutemonannee.services.journal import JournalClient, parse_activity_date, validate_source


class Transport:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, path):
        key = ("posts" if "/posts/list?" in path else "photos", int(parse_qs(urlsplit(path).query)["page"][0]))
        self.calls.append(key)
        return self.pages[key]


def post(count=1):
    return {"model": "post", "id": 42, "images_count": count,
            "activity_date_detailed": {"day": "6", "month": "nov.", "year": 2026}}


def image(photo_id=PHOTO, *, allowed=True, source=SOURCE):
    return {"type": "image", "uuid": str(photo_id), "post_id": 42,
            "can_download": allowed, "src": source, "extension": "jpg"}


def pages(items, *, count=None):
    return {
        ("posts", 1): {"current_page": 1, "next_page": None, "data": [post(len(items) if count is None else count)]},
        ("photos", 1): {"current_page": 1, "last_page": 1, "data": items},
    }


@pytest.mark.parametrize("month,number", [("févr.", 2), ("août", 8), ("décembre", 12), ("11", 11), ("juill.", 7)])
def test_french_activity_dates(month, number):
    assert parse_activity_date({"day": "6", "month": month, "year": 2026}) == date(2026, number, 6)


@pytest.mark.parametrize("data", [
    {"day": "31", "month": "févr.", "year": 2026},
    {"day": "6", "month": "unknown", "year": 2026},
    {"day": 6, "month": "nov", "year": 2026},
    {"day": "6", "month": "nov", "year": True},
])
def test_no_upload_date_fallback(data):
    with pytest.raises(ExportError):
        parse_activity_date(data)


def test_both_pagination_levels_and_deduplication():
    second = uuid4()
    data = pages([image()])
    data[("posts", 1)]["next_page"] = 2
    data[("posts", 2)] = {"current_page": 2, "next_page": None, "data": [post(2)]}
    data[("posts", 1)]["data"][0]["images_count"] = 2
    data[("photos", 1)]["last_page"] = 2
    data[("photos", 2)] = {"current_page": 2, "last_page": 2, "data": [image(), image(second, allowed=False, source="untrusted")]}
    transport = Transport(data)
    result = list(JournalClient(transport, JOURNAL).photos())
    assert [p.id for p in result] == [PHOTO, second]
    assert result[1].source is None
    assert transport.calls == [("posts", 1), ("photos", 1), ("photos", 2), ("posts", 2)]


@pytest.mark.parametrize("mutation", ["page", "next", "last", "count", "post", "permission", "missing", "array"])
def test_malformed_api_never_becomes_empty_success(mutation):
    data = pages([image()])
    if mutation == "page":
        data[("posts", 1)]["current_page"] = 2
    elif mutation == "next":
        data[("posts", 1)]["next_page"] = 1
    elif mutation == "last":
        data[("photos", 1)]["last_page"] = 0
    elif mutation == "count":
        data[("posts", 1)]["data"][0]["images_count"] = 2
    elif mutation == "post":
        data[("photos", 1)]["data"][0]["post_id"] = 99
    elif mutation == "permission":
        data[("photos", 1)]["data"][0]["can_download"] = "true"
    elif mutation == "missing":
        del data[("posts", 1)]["next_page"]
    else:
        data[("photos", 1)]["data"] = {}
    with pytest.raises(ExportError):
        list(JournalClient(Transport(data), JOURNAL).photos())


@pytest.mark.parametrize("source", [
    "http://photos.s3.toutemonannee.com/private", "https://evil.com/private",
    "https://photos.s3.toutemonannee.com.evil.com/private",
    "https://user:private@photos.s3.toutemonannee.com/x",
    "https://photos.s3.toutemonannee.com:444/private",
])
def test_untrusted_media_urls_are_not_echoed(source):
    with pytest.raises(ExportError) as error:
        validate_source(source)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("repeated_source", [SOURCE, SOURCE + "&other", None, "https://evil.com/private"])
def test_conflicting_guid_observations_and_shared_sources(repeated_source):
    second = uuid4()
    data = pages([image(allowed=False), image(second, allowed=False), image(allowed=False, source=repeated_source)], count=2)
    result = list(JournalClient(Transport(data), JOURNAL, capture_restricted=True).photos())
    assert len(result) == 2 and all(p.source_ambiguous for p in result)


def test_identical_repeated_guid_is_not_ambiguous():
    data = pages([image(allowed=False), image(allowed=False)], count=1)
    result = list(JournalClient(Transport(data), JOURNAL, capture_restricted=True).photos())
    assert len(result) == 1 and not result[0].source_ambiguous
