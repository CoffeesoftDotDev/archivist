"""Synthetic identities and images; no live personal data."""
import io
from datetime import date
from uuid import UUID

import pytest

pytest.importorskip("httpx")
pytest.importorskip("PIL")
pytest.importorskip("playwright")

from PIL import Image

from toutemonannee.core import Photo

JOURNAL = UUID("11111111-1111-4111-8111-111111111111")
PHOTO = UUID("22222222-2222-4222-8222-222222222222")
SOURCE = "https://photos.s3.toutemonannee.com/image.jpg?signature=private"


@pytest.fixture
def photo():
    return Photo(JOURNAL, 42, PHOTO, date(2026, 11, 6), "jpg", SOURCE, True, 1)


@pytest.fixture
def png():
    with io.BytesIO() as output:
        Image.new("RGB", (23, 17), "red").save(output, "PNG")
        return output.getvalue()
