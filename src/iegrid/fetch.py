"""HTTP: read a page, list its PDF links, download a file with its headers."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin

USER_AGENT = "ie-grid-pipeline/0.1 (public-data research; github.com/rikokardamow)"
TIMEOUT_S = 60

PDF_HREF = re.compile(r"""href=["']([^"']+?\.pdf(?:\?[^"']*)?)["']""", re.IGNORECASE)


@dataclass(frozen=True)
class Download:
    url: str
    content: bytes
    last_modified: datetime | None


def _get(url: str) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.read(), {k.lower(): v for k, v in resp.headers.items()}


def pdf_links(page_url: str, html: str) -> list[str]:
    """Absolute PDF links on the page, in page order, without repeats."""
    seen: dict[str, None] = {}
    for href in PDF_HREF.findall(html):
        seen.setdefault(urljoin(page_url, unescape(href)), None)
    return list(seen)


def page_links(page_url: str) -> list[str]:
    body, _ = _get(page_url)
    return pdf_links(page_url, body.decode("utf-8", errors="replace"))


def parse_last_modified(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def download(url: str) -> Download:
    body, headers = _get(url)
    return Download(url, body, parse_last_modified(headers.get("last-modified")))
