"""Fetch recent papers from the arXiv API (stdlib only)."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API_URL = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"
# arXiv asks for at most one request every 3 seconds.
REQUEST_INTERVAL = 3.5
PAGE_SIZE = 100


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _get(url: str, attempts: int = 4) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "arxiv-paper-tracker/1.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == attempts:
                raise
            wait = 10 * attempt
            print(f"  arXiv request failed ({error}); retrying in {wait}s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def _parse_entry(entry: ET.Element) -> dict | None:
    raw_id = _clean(entry.findtext(f"{ATOM}id"))
    match = re.search(r"abs/(.+?)(v\d+)?$", raw_id)
    if not match:
        return None
    arxiv_id = match.group(1)
    primary = entry.find(f"{ARXIV}primary_category")
    return {
        "id": arxiv_id,
        "title": _clean(entry.findtext(f"{ATOM}title")),
        "abstract": _clean(entry.findtext(f"{ATOM}summary")),
        "authors": [_clean(a.findtext(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")],
        "published": _clean(entry.findtext(f"{ATOM}published"))[:10],
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "primary_category": primary.get("term") if primary is not None else "",
    }


def fetch_topic(query: str, max_results: int) -> list[dict]:
    """Return the most recently submitted papers matching ``query``."""
    papers: list[dict] = []
    for start in range(0, max_results, PAGE_SIZE):
        params = urllib.parse.urlencode(
            {
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": start,
                "max_results": min(PAGE_SIZE, max_results - start),
            }
        )
        root = ET.fromstring(_get(f"{API_URL}?{params}"))
        entries = root.findall(f"{ATOM}entry")
        papers.extend(p for p in map(_parse_entry, entries) if p)
        time.sleep(REQUEST_INTERVAL)
        if len(entries) < PAGE_SIZE:
            break
    return papers
