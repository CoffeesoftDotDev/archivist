"""Real Chromium with synthetic routes; never contacts live accounts."""
import io
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from PIL import Image
from playwright.sync_api import Error as BrowserError, sync_playwright

from tma_test_fixtures import JOURNAL, SOURCE
from toutemonannee.core import Config, ExportError
from toutemonannee.services.browser import BrowserSession, SITE, journal_from_url, launch_context
from toutemonannee.services.screenshot import PhotoScreenshotter

pytestmark = pytest.mark.browser


@pytest.fixture
def context(tmp_path):
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except BrowserError as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Install Chromium with uv run playwright install chromium")
            raise
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        try:
            yield context
        finally:
            context.close()
            browser.close()


def test_controlled_sign_in_captures_csrf_and_closes_restored_tabs(context):
    old = context.new_page()
    observed = []
    def route_handler(route):
        request = route.request
        if "/posts/list" in request.url:
            observed.append(request.headers)
            route.fulfill(status=200, content_type="application/json",
                          body='{"current_page":1,"next_page":null,"data":[]}')
        else:
            route.fulfill(content_type="text/html", body=f"""
                <script>fetch('/journal/{JOURNAL}/posts/list?page=1',
                  {{headers: {{'x-csrf-token':'synthetic-csrf'}}}})</script>""")
    context.route("**/*", route_handler)
    session = BrowserSession.sign_in(context, Config(journal_id=JOURNAL, login_timeout_seconds=3))
    assert old.is_closed() and len(context.pages) == 1
    assert session.journal_id == JOURNAL
    assert session.headers["X-CSRF-TOKEN"] == "synthetic-csrf"
    assert observed
    with pytest.raises(ExportError, match="outside"):
        session.get("/journal/another/posts/list")


@pytest.mark.parametrize("suffix", ["?page=1", "?published_date_order=1"])
def test_journal_detection_is_site_bound(suffix):
    assert journal_from_url(f"{SITE}/journal/{JOURNAL}/posts/list{suffix}") == JOURNAL
    assert journal_from_url(f"https://evil.com/journal/{JOURNAL}/posts/list") is None


def viewer_html(source, *, duplicate=False):
    image = "<img src='" + source + "' style='width:80vw;height:auto'>"
    return f"""
        <div class="files"><div class="file cursor-zoomin" onclick="document.querySelector('[role=dialog]').hidden=false">Open</div></div>
        <div role="dialog" hidden>
          <div aria-live="polite" aria-atomic="true"><span>1</span></div>
          <div style="transform:translateX(-33.333%)"><div></div><div>
          {image}{image if duplicate else ''}</div><div></div></div>
        </div>"""


def test_loaded_visible_image_capture_and_ambiguity_failure(context, photo, png):
    state = {"duplicate": False}
    def handler(route):
        if ".s3.toutemonannee.com" in route.request.url:
            route.fulfill(content_type="image/png", body=png)
        else:
            route.fulfill(content_type="text/html", body=viewer_html(SOURCE, duplicate=state["duplicate"]))
    context.route("**/*", handler)
    screenshotter = PhotoScreenshotter(context, JOURNAL, timeout=1000)
    restricted = replace(photo, can_download=False)
    try:
        captured = screenshotter.capture(restricted)
        with Image.open(io.BytesIO(captured)) as image:
            assert image.width > 1000 and image.height > 0
        screenshotter.close()
        state["duplicate"] = True
        with pytest.raises(ExportError, match="ambiguous"):
            screenshotter.capture(restricted)
        assert screenshotter.page is None
        with pytest.raises(ExportError, match="ambiguous"):
            screenshotter.capture(replace(restricted, source_ambiguous=True))
    finally:
        screenshotter.close()


def test_viewer_rejects_unloaded_and_navigation_away(context, photo):
    def handler(route):
        if ".s3.toutemonannee.com" in route.request.url:
            route.fulfill(status=404, content_type="text/plain", body="missing")
        else:
            route.fulfill(content_type="text/html", body=viewer_html(SOURCE))
    context.route("**/*", handler)
    capture = PhotoScreenshotter(context, JOURNAL, timeout=300)
    with pytest.raises(ExportError, match="viewer failed"):
        capture.capture(replace(photo, can_download=False))
    assert capture.page is None


def test_viewer_navigates_to_the_matching_photo_not_the_first(context, photo, png):
    second = SOURCE + "&second"
    html = viewer_html(SOURCE).replace(
        "</div>\n        </div>",
        """</div>
        <button onclick="document.querySelector('[aria-live] span').textContent='2';
          document.querySelector('[role=dialog] img').src=this.dataset.source"
          data-source='""" + second + """'>Next item</button></div>""",
    )
    def handler(route):
        if ".s3.toutemonannee.com" in route.request.url:
            route.fulfill(content_type="image/png", body=png)
        else:
            route.fulfill(content_type="text/html", body=html)
    context.route("**/*", handler)
    capture = PhotoScreenshotter(context, JOURNAL, timeout=1000)
    try:
        result = capture.capture(replace(photo, can_download=False, source=second, post_image_count=2))
        assert result.startswith(b"\x89PNG")
        assert capture.page.locator("[aria-live] span").text_content() == "2"
    finally:
        capture.close()
    capture.page = context.new_page()
    capture.page.goto(SITE + "/connect")
    capture.open_post = photo.post_id
    with pytest.raises(ExportError, match="left the selected"):
        capture.capture(replace(photo, can_download=False))
    assert capture.page is None


@pytest.mark.parametrize("resolution", ["1280x720", "1920x1080", "2560x1080", "3440x1440", "3840x2160"])
def test_persistent_session_and_viewport(tmp_path, resolution):
    with sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
        if not executable.exists():
            pytest.skip("Install Chromium with uv run playwright install chromium")
        profile = tmp_path / "profile"
        config = Config(browser_channel="chromium", resolution=resolution)
        context = launch_context(playwright, config, profile, headless=True)
        try:
            context.add_cookies([{"name": "synthetic", "value": "session", "url": SITE, "expires": 2_000_000_000}])
            page = context.new_page()
            assert page.viewport_size == config.viewport
            assert page.evaluate("({width:screen.width,height:screen.height})") == config.viewport
        finally:
            context.close()
        context = launch_context(playwright, config, profile, headless=True)
        try:
            assert any(c["name"] == "synthetic" for c in context.cookies())
        finally:
            context.close()
