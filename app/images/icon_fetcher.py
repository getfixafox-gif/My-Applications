"""Icon downloading from a website (explicit user action only).

The application is offline-first: nothing here ever runs on startup or in the
background. A user clicks "Download icon" in the entry dialog, and only then a
single HTTPS request is made to the site's own ``/favicon.ico`` (followed by the
``<link rel="icon">`` declarations when that is missing).

Only the standard library is used, so there is no extra dependency and no
telemetry. Every failure mode raises :class:`IconFetchError` with a message that
can be shown to the user directly.
"""

from __future__ import annotations

import html
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.utils.logger import get_logger
from app.utils.validators import ValidationError, normalize_url

logger = get_logger("icons")

#: Hard limits so a hostile or broken server cannot exhaust memory.
MAX_ICON_BYTES = 5 * 1024 * 1024
MAX_HTML_BYTES = 512 * 1024
SOCKET_TIMEOUT = 8.0
#: Upper bound on network round-trips per fetch.
MAX_ATTEMPTS = 6

USER_AGENT = "Mozilla/5.0 (compatible; MyApplications/3.0; +offline-icon-fetch)"

_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r"""([a-zA-Z:-]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""")
#: Preferred ``rel`` values, best first.
_REL_PRIORITY = (
    "apple-touch-icon-precomposed",
    "apple-touch-icon",
    "icon",
    "shortcut icon",
    "mask-icon",
)


class IconFetchError(RuntimeError):
    """Raised when an icon cannot be downloaded."""


@dataclass(slots=True)
class FetchedIcon:
    data: bytes
    url: str


def normalize_site_url(raw: str) -> str:
    """Turn any stored link into a browsable http(s) site URL.

    ``mailto:`` / ``ftp:`` targets have no icon, so they are rejected early with
    a readable message.
    """
    try:
        url = normalize_url(raw)
    except ValidationError as exc:
        raise IconFetchError(str(exc)) from exc
    scheme = url.split(":", 1)[0].lower()
    if scheme not in {"http", "https"}:
        raise IconFetchError("Иконку можно скачать только с сайта http или https")
    return url


def _open(url: str, *, accept: str, limit: int) -> tuple[bytes, str, str]:
    """Fetch ``url`` with redirects, a timeout and a hard size limit.

    Returns ``(body, content_type, final_url)``.
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
        method="GET",
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=SOCKET_TIMEOUT, context=context) as response:
            final_url = response.geturl()
            content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            body = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        raise IconFetchError(f"Сервер ответил ошибкой {exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLError):
            raise IconFetchError("Не удалось установить защищённое соединение (SSL)") from exc
        raise IconFetchError("Нет подключения к интернету или сайт недоступен") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise IconFetchError("Сайт не ответил вовремя") from exc
    except ValueError as exc:  # malformed URL
        raise IconFetchError(f"Некорректный адрес: {exc}") from exc
    except OSError as exc:
        raise IconFetchError(f"Ошибка сети: {exc}") from exc
    if len(body) > limit:
        raise IconFetchError("Ответ сайта слишком большой")
    return body, content_type, final_url


def _looks_like_image(body: bytes) -> bool:
    """Cheap magic-number sniffing: never hand junk to Pillow."""
    if len(body) < 12:
        return False
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if body.startswith(b"\xff\xd8\xff"):
        return True
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return True
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if body[:2] == b"BM":
        return True
    if body[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"):
        return True
    if body[:4] == b"II*\x00" or body[:4] == b"MM\x00*":
        return True
    return False


def _declared_icons(page: str, base_url: str) -> list[str]:
    """Extract candidate icon URLs, best first, without duplicates."""
    found: dict[str, tuple[int, str]] = {}
    for tag in _LINK_TAG_RE.findall(page):
        attributes = {
            match.group(1).lower(): html.unescape(
                match.group(3) or match.group(4) or match.group(5) or ""
            )
            for match in _ATTR_RE.finditer(tag)
        }
        rel = " ".join(attributes.get("rel", "").lower().split())
        href = attributes.get("href", "").strip()
        if not href:
            continue
        priority = None
        for index, value in enumerate(_REL_PRIORITY):
            if rel == value or rel.split() == value.split():
                priority = index
                break
        if priority is None:
            continue
        try:
            absolute = urllib.parse.urljoin(base_url, href)
        except ValueError:
            continue
        if not absolute.lower().startswith(("http://", "https://")):
            continue
        # Prefer larger declared sizes when everything else is equal.
        size_hint = 0
        sizes = attributes.get("sizes", "")
        if isinstance(sizes, str) and "x" in sizes.lower():
            digits = sizes.lower().split("x")[0].strip()
            if digits.isdigit():
                size_hint = int(digits)
        current = found.get(absolute)
        if current is None or (priority, -size_hint) < current:
            found[absolute] = (priority, -size_hint)
    return [url for url, _ in sorted(found.items(), key=lambda item: item[1])]


def fetch_icon(site_url: str) -> FetchedIcon:
    """Download the best icon for ``site_url``.

    Tries the page's declared icons first, then ``/favicon.ico``. Raises
    :class:`IconFetchError` when every candidate fails.
    """
    url = normalize_site_url(site_url)
    parsed = urllib.parse.urlsplit(url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    candidates: list[str] = []
    if parsed.path not in ("", "/") or parsed.query:
        # Record links often point at a deep page: read it for icon hints.
        candidates.extend(_page_icon_candidates(url))
    candidates.extend(_page_icon_candidates(root))
    candidates.append(urllib.parse.urljoin(root, "/favicon.ico"))

    seen: set[str] = set()
    attempts = 0
    last_error: str | None = None
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if attempts >= MAX_ATTEMPTS:
            break
        attempts += 1
        try:
            body, content_type, final_url = _open(
                candidate, accept="image/*,*/*;q=0.8", limit=MAX_ICON_BYTES
            )
        except IconFetchError as exc:
            last_error = str(exc)
            continue
        if not _looks_like_image(body):
            last_error = "Сайт вернул файл, не похожий на изображение"
            continue
        logger.info("Icon downloaded from %s (%s bytes)", final_url, len(body))
        return FetchedIcon(data=body, url=final_url)

    raise IconFetchError(
        last_error or "На сайте не найден подходящий файл иконки"
    )


def _page_icon_candidates(page_url: str) -> list[str]:
    """Read an HTML page and return its declared icon URLs (may be empty)."""
    try:
        body, content_type, final_url = _open(
            page_url, accept="text/html,*/*;q=0.8", limit=MAX_HTML_BYTES
        )
    except IconFetchError as exc:
        logger.debug("Cannot read %s for icon hints: %s", page_url, exc)
        return []
    if content_type and not content_type.startswith("text/") and "html" not in content_type:
        return []
    try:
        page = body.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - decoding is best effort
        return []
    return _declared_icons(page, final_url)
