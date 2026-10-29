"""Tìm kiếm web: Serper nếu có key, không thì DuckDuckGo (ddgs). Có cache SQLite 24h."""
from datetime import timedelta

import httpx

from .. import config, db


def _serper(query: str, language: str, num: int) -> list[dict]:
    r = httpx.post(
        "https://google.serper.dev/search",
        headers={"X-API-KEY": config.SERPER_API_KEY},
        json={"q": query, "num": num, "hl": language, "gl": "vn" if language == "vi" else "us"},
        timeout=20,
    )
    r.raise_for_status()
    return [{"title": o["title"], "url": o["link"], "snippet": o.get("snippet", "")} for o in r.json().get("organic", [])]


def _ddg(query: str, language: str, num: int) -> list[dict]:
    from ddgs import DDGS

    hits = DDGS().text(query, region="vn-vi" if language == "vi" else "us-en", max_results=num)
    return [{"title": h["title"], "url": h["href"], "snippet": h.get("body", "")} for h in hits]


def search(query: str, language: str = "vi", num: int = 5) -> list[dict]:
    with db.session() as s:
        hit = s.get(db.SearchCache, (query, language))
        if hit and db.now() - hit.created_at < timedelta(hours=24):
            return hit.result[:num]
    try:
        results = (_serper if config.SERPER_API_KEY else _ddg)(query, language, num)
    except Exception:
        return []  # không có kết quả search thì pipeline vẫn chạy, chỉ thiếu nguồn
    if results:
        with db.session() as s:
            s.merge(db.SearchCache(query=query, language=language, result=results))
            s.commit()
    return results


def fetch_page(url: str, max_chars: int = 3000) -> str:
    import trafilatura

    try:
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        return (trafilatura.extract(r.text) or "")[:max_chars]
    except Exception:
        return ""
