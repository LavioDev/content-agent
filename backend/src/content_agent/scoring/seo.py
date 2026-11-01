import re

from .readability import score_readability
from .text import fold, headings, slugify, strip_markdown, words


def score_seo(
    markdown: str,
    focus_keyword: str,
    meta_title: str = "",
    meta_description: str = "",
    slug: str = "",
    image_prompts: list[dict] | None = None,
    language: str = "vi",
) -> dict:
    """Điểm SEO 0-100 theo checklist kiểu Yoast (12 tiêu chí, tổng 100 điểm; liệt kê trong docs/report/README.md mục 2)."""
    kw = fold(focus_keyword).strip()
    plain = strip_markdown(markdown)
    n_words = len(words(plain))
    h1 = headings(markdown, 1)
    h2 = headings(markdown, 2)
    body = re.sub(r"^#\s+.*$", "", markdown, count=1, flags=re.M)
    first100 = fold(" ".join(words(strip_markdown(body))[:100]))
    kw_count = len(re.findall(re.escape(kw), fold(plain))) if kw else 0
    density = kw_count * len(kw.split()) / n_words * 100 if n_words else 0.0
    readability = score_readability(markdown, language)
    images = image_prompts or []
    ext_links = re.findall(r"\]\(https?://[^)\s]+\)", markdown)

    checks = [
        ("kw_h1", "Từ khoá chính trong H1", 10, bool(h1 and kw in fold(h1[0])), h1[0] if h1 else "không có H1"),
        ("kw_first100", "Từ khoá trong 100 từ đầu", 10, kw in first100, ""),
        ("kw_h2", "Từ khoá trong ít nhất 1 H2", 10, any(kw in fold(h) for h in h2), f"{len(h2)} H2"),
        ("density", "Mật độ từ khoá 0.5–2.5%", 10, 0.5 <= density <= 2.5, f"{density:.2f}%"),
        (
            "meta_desc",
            "Meta description 120–160 ký tự, có từ khoá",
            10,
            120 <= len(meta_description) <= 160 and kw in fold(meta_description),
            f"{len(meta_description)} ký tự",
        ),
        ("meta_title", "Meta title ≤ 60 ký tự", 5, 0 < len(meta_title) <= 60, f"{len(meta_title)} ký tự"),
        (
            "slug",
            "Slug ngắn, có từ khoá, không dấu",
            5,
            bool(slug) and len(slug) <= 60 and slugify(focus_keyword) in slug and slug == slugify(slug),
            slug,
        ),
        ("length", "Độ dài ≥ 1200 từ", 10, n_words >= 1200, f"{n_words} từ"),
        ("h2_count", "Ít nhất 3 heading H2", 10, len(h2) >= 3, f"{len(h2)} H2"),
        ("ext_links", "Có link nguồn ngoài", 10, bool(ext_links), f"{len(ext_links)} link"),
        ("image_alt", "Image prompt có alt text", 5, bool(images) and all(i.get("alt") for i in images), f"{len(images)} ảnh"),
        ("readability", "Độ dễ đọc đạt ngưỡng", 5, readability["passed"], f"{readability['score']}"),
    ]
    items = [
        {"id": i, "label": label, "max": mx, "points": mx if ok else 0, "passed": ok, "detail": detail}
        for i, label, mx, ok, detail in checks
    ]
    return {
        "score": sum(i["points"] for i in items),
        "items": items,
        "word_count": n_words,
        "density": round(density, 2),
        "readability": readability,
    }
