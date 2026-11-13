"""Dedicated interactive browser session; authentication never leaves its context."""
import os
import re
import tempfile
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from playwright.sync_api import BrowserContext, Playwright, sync_playwright

from ..core import Config, ExportError
from ..utils.files import safe_path

SITE = "https://www.toutemonannee.com"


def journal_from_url(url: str) -> UUID | None:
    """Recognize only this site's successful posts-list route."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "www.toutemonannee.com":
        return None
    match = re.fullmatch(r"/journal/([0-9a-fA-F-]{36})/posts/list", parsed.path)
    try:
        return UUID(match[1]) if match else None
    except ValueError:
        return None


def prepare_profile(channel: str) -> Path:
    """Use only the dedicated legacy-compatible private profile, never a user's default."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            raise ExportError("A user-local browser directory is unavailable; use --reuse-session false.")
        base = Path(local)
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    root = safe_path(base / "TouteMonAnnee.Cli")
    profile = root / "browser" / channel
    for path in (root, root / "browser", profile):
        safe_path(path)
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ExportError("The browser profile is accessible to other users; restrict permissions or use --reuse-session false.")
    return profile


def launch_context(playwright: Playwright, config: Config, profile: Path, *, headless: bool = False) -> BrowserContext:
    """Launch a dedicated context with matching viewport, screen and window."""
    dimensions = config.viewport
    args = [f"--window-size={dimensions['width']},{dimensions['height']}"]
    if config.reuse_session:
        args.append("--restore-last-session")
    return playwright.chromium.launch_persistent_context(
        str(profile), channel="msedge" if config.browser_channel == "msedge" else None,
        headless=headless, accept_downloads=False, viewport=dimensions, screen=dimensions,
        device_scale_factor=1, args=args,
    )


class BrowserSession:
    """Cookie-bound API transport owned by an authenticated browser context."""

    def __init__(self, context: BrowserContext, journal_id: UUID, headers: dict[str, str], timeout: int):
        self.context = context
        self.journal_id = journal_id
        self.headers = headers
        self.timeout = timeout

    @classmethod
    def sign_in(cls, context: BrowserContext, config: Config) -> "BrowserSession":
        """Select a journal only from a successful posts response on a new controlled tab."""
        page = context.new_page()
        for restored in context.pages:
            if restored != page:
                restored.close()
        def matches(response) -> bool:
            selected = journal_from_url(response.url)
            return response.status == 200 and selected is not None and (config.journal_id is None or selected == config.journal_id)
        with page.expect_response(matches, timeout=config.login_timeout_seconds * 1000) as pending:
            path = f"/journal/{config.journal_id}" if config.journal_id else "/connect"
            page.goto(SITE + path, wait_until="domcontentloaded", timeout=config.request_timeout_seconds * 1000)
        response = pending.value
        selected = journal_from_url(response.url)
        if selected is None:
            raise ExportError("No matching journal was selected.")
        headers = {
            "X-Requested-With": "XMLHttpRequest", "X-Requested-From": "Reactor",
            "Accept": "application/json", "Referer": f"{SITE}/journal/{selected}",
        }
        csrf = response.request.all_headers().get("x-csrf-token")
        if csrf:
            headers["X-CSRF-TOKEN"] = csrf
        return cls(context, selected, headers, config.request_timeout_seconds * 1000)

    def get(self, relative_path: str) -> object:
        """Request only this journal's API, refusing redirects and non-JSON responses."""
        prefix = f"/journal/{self.journal_id}/posts/"
        if not relative_path.startswith(prefix) or urlsplit(relative_path).netloc or ".." in urlsplit(relative_path).path:
            raise ExportError("Refusing an API request outside the selected journal.")
        response = self.context.request.get(SITE + relative_path, headers=self.headers, timeout=self.timeout, max_redirects=0)
        try:
            if response.status in (401, 403):
                raise ExportError("Website session expired or access was denied. Sign in again and check permissions.")
            if response.status != 200:
                raise ExportError(f"Journal API returned HTTP {response.status}; no response body is logged.")
            if "application/json" not in response.headers.get("content-type", "").lower():
                raise ExportError("Journal API returned non-JSON data; sign-in may have expired or the API changed.")
            try:
                return response.json()
            except ValueError:
                raise ExportError("Journal API returned malformed JSON.") from None
        finally:
            response.dispose()


@contextmanager
def open_session(config: Config) -> Iterator[BrowserSession]:
    """Own and close the context/profile on success, failure and cancellation."""
    with sync_playwright() as playwright:
        with tempfile.TemporaryDirectory(prefix="tma-browser-") as fresh:
            profile = prepare_profile(config.browser_channel) if config.reuse_session else Path(fresh)
            context = launch_context(playwright, config, profile)
            try:
                yield BrowserSession.sign_in(context, config)
            finally:
                context.close()
