"""Capture only a verified loaded visible viewer image, never its original."""
from uuid import UUID

from playwright.sync_api import BrowserContext, Error as BrowserError, Locator, Page

from ..core import ExportError, Photo
from .browser import SITE
from .journal import validate_source

IMAGE_SELECTOR = "div[style*='-33.333%'] > div:nth-child(2):nth-last-child(2) > img"
COUNTER_SELECTOR = "[aria-live='polite'][aria-atomic='true'] > span:first-child"
LOADED = """({imageSelector, counterSelector, source, index}) => {
    const images = document.querySelectorAll(imageSelector);
    const counters = document.querySelectorAll(counterSelector);
    if (images.length !== 1 || counters.length !== 1 || Number(counters[0].textContent) !== index) return false;
    const image = images[0];
    return image.complete && image.naturalWidth > 0 && image.naturalHeight > 0
        && image.src === source && image.currentSrc === source;
}"""


class PhotoScreenshotter:
    """Navigate the site's bounded viewer, rejecting ambiguous or changed matches."""

    def __init__(self, context: BrowserContext, journal_id: UUID, *, timeout: int):
        self.context = context
        self.journal_id = journal_id
        self.timeout = timeout
        self.page: Page | None = None
        self.open_post: int | None = None

    def capture(self, photo: Photo) -> bytes:
        """Return PNG pixels only when identity is stable before and after capture."""
        try:
            if (photo.can_download or photo.journal_id != self.journal_id
                    or photo.post_id <= 0 or photo.post_image_count <= 0):
                raise ExportError("Photo viewer metadata does not match the selected journal.")
            if photo.source is None or photo.source_ambiguous:
                raise ExportError("Photo viewer source is missing, invalid or ambiguous; no screenshot was saved.")
            source = validate_source(photo.source)
            if self.page is None or self.page.is_closed() or self.open_post != photo.post_id:
                self._open_post(photo)
            page = self.page
            if page is None:
                raise ExportError("Photo viewer is unavailable.")
            self._ensure_post(photo)
            dialog = page.locator("[role='dialog']")
            visited: set[int] = set()
            direction = 1
            for _ in range(photo.post_image_count * 2):
                self._ensure_post(photo)
                index = self._current_index(dialog, photo.post_image_count)
                visited.add(index)
                image = dialog.locator(IMAGE_SELECTOR)
                image.first.wait_for(state="visible", timeout=self.timeout)
                if image.count() != 1:
                    raise ExportError("Photo viewer image is missing or ambiguous; no screenshot was saved.")
                if image.evaluate("image => image.src") == source:
                    arguments = {
                        "imageSelector": "[role='dialog'] " + IMAGE_SELECTOR,
                        "counterSelector": "[role='dialog'] " + COUNTER_SELECTOR,
                        "source": source, "index": index,
                    }
                    page.wait_for_function(LOADED, arg=arguments, timeout=self.timeout)
                    self._ensure_post(photo)
                    png = image.screenshot(
                        type="png", animations="disabled", timeout=self.timeout,
                        style="[role='dialog'] * { visibility: hidden !important; } "
                              + "[role='dialog'] " + IMAGE_SELECTOR + " { visibility: visible !important; }",
                    )
                    self._ensure_post(photo)
                    if not page.evaluate(LOADED, arguments):
                        raise ExportError("Photo viewer changed during capture; no screenshot was saved.")
                    return png
                if len(visited) == photo.post_image_count:
                    break
                if index == photo.post_image_count:
                    direction = -1
                elif index == 1:
                    direction = 1
                dialog.get_by_role("button", name="Next item" if direction > 0 else "Previous item", exact=True).click(timeout=self.timeout)
                page.wait_for_function(
                    "({selector, index}) => { const n = document.querySelectorAll(selector); "
                    "return n.length === 1 && Number(n[0].textContent) === index; }",
                    arg={"selector": "[role='dialog'] " + COUNTER_SELECTOR, "index": index + direction},
                    timeout=self.timeout,
                )
            raise ExportError("The matching photo was not found in the website viewer; no screenshot was saved.")
        except BrowserError:
            self.close()
            raise ExportError("The website photo viewer failed or changed; no screenshot was saved.") from None
        except (ExportError, KeyboardInterrupt):
            self.close()
            raise

    def _open_post(self, photo: Photo) -> None:
        self.close()
        self.page = self.context.new_page()
        self.page.goto(f"{SITE}/journal/{photo.journal_id}/posts/{photo.post_id}",
                       wait_until="domcontentloaded", timeout=self.timeout)
        self._ensure_post(photo)
        self.page.locator(".files .file.cursor-zoomin").first.click(timeout=self.timeout)
        dialog = self.page.locator("[role='dialog']")
        dialog.first.wait_for(state="visible", timeout=self.timeout)
        if dialog.count() != 1:
            raise ExportError("Photo viewer is missing or ambiguous; no screenshot was saved.")
        self._ensure_post(photo)
        self.open_post = photo.post_id

    def _ensure_post(self, photo: Photo) -> None:
        if (self.page is None or self.page.is_closed()
                or self.page.url.split("?")[0].split("#")[0].rstrip("/") != f"{SITE}/journal/{photo.journal_id}/posts/{photo.post_id}"):
            raise ExportError("Photo viewer left the selected post; no screenshot was saved.")

    def _current_index(self, dialog: Locator, total: int) -> int:
        counter = dialog.locator(COUNTER_SELECTOR)
        counter.first.wait_for(state="visible", timeout=self.timeout)
        value = (counter.text_content() or "").strip() if counter.count() == 1 else ""
        if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= total:
            raise ExportError("Photo viewer position is missing or invalid; no screenshot was saved.")
        return int(value)

    def close(self) -> None:
        """Close the controlled viewer tab and discard its post identity."""
        try:
            if self.page is not None and not self.page.is_closed():
                self.page.close()
        finally:
            self.page = None
            self.open_post = None
