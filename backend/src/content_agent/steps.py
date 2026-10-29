"""Từng bước của pipeline. Mỗi hàm đồng bộ, trả (kết quả, Usage). Tool MCP lẻ và pipeline đều gọi lại các hàm này."""
from concurrent.futures import ThreadPoolExecutor

from . import config, llm
from .scoring.text import slugify
from .tools.search import fetch_page, search

LANG = {"vi": "Vietnamese", "en": "English"}
_GUIDES = config.ROOT / "backend" / "prompts" / "style_guides"


def style_guide(name: str) -> str:
    return (_GUIDES / f"{name}.md").read_text(encoding="utf-8")


def research(topic: str, audience: str, language: str, num_sources: int = 5):
    # Bước 1: người dùng hay gõ câu lệnh ("tìm hiểu về X và viết tôi bài...") -> tách chủ đề + từ khoá trước khi search
    plan, usage = llm.run_json(
        "researcher",
        f"User request: {topic}\nAudience: {audience}\nLanguage: {LANG[language]}\n\n"
        "Return a JSON object with keys: "
        '"subject" (the real subject of the article, without instruction words like "write me", "viết tôi bài", "tìm hiểu về"), '
        '"focus_keyword" (2-4 words in the article language that people actually type into Google; it must read naturally '
        'inside a sentence and a heading without inserting extra words, e.g. "lịch sử ESP32" not "lịch sử hình thành ESP32"), '
        '"search_query" (the best web search query for this subject).',
        "A single JSON object",
        temperature=0.2,
    )
    subject = str(plan.get("subject") or topic)
    keyword = str(plan.get("focus_keyword") or subject)
    hits = search(str(plan.get("search_query") or subject), language, num_sources)
    with ThreadPoolExecutor(max_workers=5) as ex:
        pages = list(ex.map(lambda h: fetch_page(h["url"]), hits))
    material = "\n\n".join(
        f"[{i + 1}] {h['title']} ({h['url']})\n{h['snippet']}\n{p[:1500]}" for i, (h, p) in enumerate(zip(hits, pages))
    ) or "(no search results available — rely on general knowledge and say so in the outline notes)"
    data, u = llm.run_json(
        "researcher",
        f"Subject: {subject}\nFocus keyword: {keyword}\nAudience: {audience}\nWrite the outline in {LANG[language]}.\n\n"
        f"Search material:\n{material}\n\n"
        "Return a JSON object with keys: "
        '"keywords" (3-6 secondary keywords), '
        '"outline" (list of 5-7 section headings; the first is the intro, the last the conclusion; '
        "one of the middle headings contains the exact focus keyword), "
        '"sources" (list of {"title","url","summary"} chosen ONLY from the material above; summary = 1-2 sentences of usable facts).',
        "A single JSON object",
    )
    usage += u
    # chỉ giữ nguồn có URL thật nằm trong kết quả search -> không bịa link
    real = {h["url"] for h in hits}
    data["sources"] = [s for s in data.get("sources", []) if s.get("url") in real]
    data["subject"], data["focus_keyword"] = subject, keyword
    data["outline"] = [str(x) for x in data.get("outline", [])] or [subject]
    return data, usage


def write(research_data: dict, topic: str, audience: str, tone: str, language: str, word_count: int):
    sources = "\n".join(f"- {s['title']} ({s['url']}): {s.get('summary', '')}" for s in research_data["sources"]) or "(none)"
    return llm.run(
        "writer",
        f"Write a blog post in {LANG[language]} about: {research_data.get('subject', topic)}\nAudience: {audience}\nTone: {tone}\n"
        f"Focus keyword: \"{research_data['focus_keyword']}\" (secondary: {', '.join(research_data.get('keywords', []))})\n"
        "Use the focus keyword EXACTLY (same words, same order, nothing inserted) in the H1, in the first sentence "
        "and in one H2, then 3-6 more times in the body.\n"
        "Whatever the tone, keep sentences short: under 20 words on average and never over 30 words. "
        "Tone changes word choice, not sentence length.\n"
        f"Length: AT LEAST {int(word_count * 1.1)} words. Do not stop early.\n"
        "Outline (use as H2 sections, in order):\n"
        + "\n".join(f"{i + 1}. {h}" for i, h in enumerate(research_data["outline"]))
        + f"\n\nSources you may cite with Markdown links [text](url):\n{sources}\n\n"
        f"Follow this style guide:\n{style_guide('blog')}\n"
        "Output only the article in Markdown, starting with the H1 title.",
        "A complete Markdown article",
        temperature=0.7,
    )


def edit(blog_md: str, language: str, tone: str, feedback: str = "", focus_keyword: str = ""):
    return llm.run(
        "editor",
        (f"REQUIRED CHANGES — apply every one of these, they override the rules below:\n{feedback}\n\n" if feedback else "")
        + f"Edit this {LANG[language]} article. Fix grammar, spelling, missing spaces, awkward phrasing and flow; keep tone: {tone}. "
        "Split any sentence longer than 30 words. Keep the section structure, every link and every fact; "
        "you may rewrite a heading when a required change asks for it. Do NOT shorten the article.\n"
        + (f"Focus keyword: \"{focus_keyword}\" — keep it exactly (same words, same order) wherever it appears.\n" if focus_keyword else "")
        + f"\nArticle:\n{blog_md}\n\nOutput only the full edited article in Markdown.",
        "The full edited article in Markdown",
        temperature=0.3,
    )


def social(blog_md: str, platforms: list[str], language: str, tone: str, audience: str):
    guides = "\n".join(f"## {p}\n{style_guide(p)}" for p in platforms)
    data, usage = llm.run_json(
        "social",
        f"Adapt the article below into social posts in {LANG[language]} for: {', '.join(platforms)}.\nTone: {tone}. Audience: {audience}.\n"
        f"Style guides:\n{guides}\n\nArticle:\n{blog_md}\n\n"
        f"Return a JSON object whose keys are exactly {platforms} and whose values are the post text.",
        "A single JSON object platform -> post text",
        temperature=0.7,
    )
    return {p: str(data.get(p, "")).strip() for p in platforms}, usage


def seo(blog_md: str, focus_keyword: str, keywords: list[str], language: str):
    data, usage = llm.run_json(
        "seo",
        f"Optimise this {LANG[language]} article for the focus keyword \"{focus_keyword}\" (secondary: {', '.join(keywords)}).\n"
        "Rules: the H1 contains the exact focus keyword; it appears in the first 100 words and in at least one H2; "
        "overall density 0.5–2.5%; keep all links; do not shorten the article or change facts.\n"
        f"Also write meta_title (max 60 characters) and meta_description (130–155 characters, contains the keyword).\n\nArticle:\n{blog_md}\n\n"
        'Return a JSON object with keys "meta_title", "meta_description", "blog_md" (the full optimised Markdown).',
        "A single JSON object",
        temperature=0.3,
    )
    out = {
        "meta_title": str(data.get("meta_title", ""))[:60],
        "meta_description": str(data.get("meta_description", "")),
        "blog_md": str(data.get("blog_md") or blog_md),
        "slug": slugify(focus_keyword),
    }
    if len(out["blog_md"]) < 0.7 * len(blog_md):  # model cắt cụt bài -> giữ bản gốc
        out["blog_md"] = blog_md
    return out, usage


def images(blog_md: str, language: str, count: int = 4):
    data, usage = llm.run_json(
        "images",
        f"Write {count} image prompts (English, concrete visual descriptions, style hints) for this article: one cover image and the rest section illustrations. "
        f"Each also needs alt text in {LANG[language]}.\n\nArticle:\n{blog_md}\n\n"
        'Return a JSON list of {"prompt","alt"}.',
        "A JSON list",
        temperature=0.8,
    )
    items = data if isinstance(data, list) else data.get("images", [])
    return [{"prompt": str(i.get("prompt", "")), "alt": str(i.get("alt", ""))} for i in items if isinstance(i, dict)][:count], usage


def qa(report: dict, blog_md: str, language: str):
    """LLM chỉ cho nhận xét định tính; pass/fail do luật cứng ở pipeline quyết định."""
    data, usage = llm.run_json(
        "qa",
        f"Review this {LANG[language]} article against the automatic checks.\nChecks: {report}\n\nArticle:\n{blog_md}\n\n"
        'Return JSON {"issues": [short, specific, actionable strings; claims without a cited source, wrong tone, unclear sections, remaining typos]}. '
        "Empty list if there are none.",
        "A single JSON object",
        temperature=0.2,
    )
    issues = data.get("issues", []) if isinstance(data, dict) else []
    return [str(i) for i in issues][:8], usage
