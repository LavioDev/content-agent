"""MCP server: 16 tools, 5 resources, 2 prompts. Mỏng — mọi logic nằm ở services/steps/pipeline."""
import asyncio
import os
import sys

# CrewAI mặc định in telemetry/banner ra stdout, làm hỏng giao thức stdio của MCP
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from . import config, db, pipeline, services, steps  # noqa: E402
from .scoring import score_readability as _score_readability  # noqa: E402
from .scoring import score_seo as _score_seo  # noqa: E402

mcp = FastMCP("ai-content-agent")
PLATFORMS = list(config.PLATFORMS)


def _blog(content_id: int | None, blog_markdown: str | None) -> tuple[str, dict | None]:
    if content_id is not None:
        c = services.get_content(content_id)
        return c["blog_md"], c
    if not blog_markdown:
        raise services.ServiceError("provide content_id or blog_markdown")
    return blog_markdown, None


# ---------------------------------------------------------------- tools
@mcp.tool()
async def create_content(topic: str, audience: str = "general readers", tone: str = "friendly", language: str = "vi",
                         platforms: list[str] | None = None, word_count: int = 1500) -> dict:
    """Start the full content pipeline (research, blog, edit, social, SEO, images, QA) in the background.
    Returns a job_id immediately; poll get_job until status is 'done', then use get_content.
    language: 'vi' or 'en'. platforms: any of threads, facebook, linkedin (default all)."""
    job_id = services.create_job(topic, audience, tone, language, platforms, word_count)
    pipeline.start(job_id)
    return {"job_id": job_id, "status": "queued"}


@mcp.tool()
async def get_job(job_id: int) -> dict:
    """Status of a pipeline job: current step, per-agent steps with tokens/cost, elapsed seconds, content_id when available."""
    return services.get_job(job_id)


@mcp.tool()
async def get_content(content_id: int, part: str | None = None) -> dict:
    """Get a content item. part (optional): blog | social | seo | images | qa. Omit for everything."""
    c = services.get_content(content_id)
    parts = {
        "blog": ["topic", "focus_keyword", "blog_md"],
        "social": ["social"],
        "seo": ["focus_keyword", "meta_title", "meta_description", "slug", "seo_score", "seo_detail"],
        "images": ["image_prompts"],
        "qa": ["qa_report", "readability_score", "seo_score", "status"],
    }
    if part is None:
        return c
    if part not in parts:
        raise services.ServiceError(f"part must be one of {list(parts)}")
    return {"id": c["id"], **{k: c[k] for k in parts[part]}}


@mcp.tool()
async def list_contents(status: str | None = None, start: str | None = None, end: str | None = None, limit: int = 20) -> list[dict]:
    """List content items (newest first). status: queued|running|pending_review|changes_requested|approved|scheduled|rejected|failed.
    start/end: ISO dates."""
    return services.list_contents(status, None, start, end, limit)


@mcp.tool()
async def research_topic(topic: str, language: str = "vi", audience: str = "general readers", num_sources: int = 5) -> dict:
    """Run only the Researcher agent: web search + outline + focus keyword + cited sources."""
    data, _ = await asyncio.to_thread(steps.research, topic, audience, language, num_sources)
    return data


@mcp.tool()
async def write_blog(topic: str, outline: list[str], audience: str = "general readers", tone: str = "friendly",
                     language: str = "vi", focus_keyword: str | None = None, word_count: int = 1500) -> dict:
    """Run only the Writer agent: write a Markdown blog post from an outline (no sources are cited)."""
    r = {"focus_keyword": focus_keyword or topic, "keywords": [], "outline": outline, "sources": []}
    md, _ = await asyncio.to_thread(steps.write, r, topic, audience, tone, language, word_count)
    return {"blog_md": md}


@mcp.tool()
async def adapt_social(content_id: int | None = None, blog_markdown: str | None = None, platforms: list[str] | None = None,
                       language: str = "vi", tone: str = "friendly") -> dict:
    """Adapt a blog (by content_id, or raw markdown) to Threads/Facebook/LinkedIn posts. Saves them when content_id is given."""
    blog, c = _blog(content_id, blog_markdown)
    posts, _ = await asyncio.to_thread(steps.social, blog, platforms or PLATFORMS, c["language"] if c else language, c["tone"] if c else tone,
                                       c["audience"] if c else "general readers")
    if c:
        services.patch_content(content_id, social=c["social"] | posts)
    return posts


@mcp.tool()
async def optimize_seo(focus_keyword: str, content_id: int | None = None, blog_markdown: str | None = None, language: str = "vi") -> dict:
    """Optimise a blog for a focus keyword: returns meta title/description, slug, optimised blog and its SEO score. Saves when content_id is given."""
    blog, c = _blog(content_id, blog_markdown)
    lang = c["language"] if c else language
    out, _ = await asyncio.to_thread(steps.seo, blog, focus_keyword, c["keywords"] if c else [], lang)
    out["seo"] = _score_seo(out["blog_md"], focus_keyword, out["meta_title"], out["meta_description"], out["slug"],
                            c["image_prompts"] if c else None, lang)
    if c:
        services.patch_content(content_id, focus_keyword=focus_keyword, **{k: out[k] for k in ("blog_md", "meta_title", "meta_description", "slug")})
    return out


@mcp.tool()
async def generate_image_prompts(content_id: int, count: int = 4) -> list[dict]:
    """Generate text-to-image prompts (+ alt text) for a content item and save them."""
    c = services.get_content(content_id)
    imgs, _ = await asyncio.to_thread(steps.images, c["blog_md"], c["language"], count)
    services.patch_content(content_id, image_prompts=imgs)
    return imgs


@mcp.tool()
def score_seo(markdown: str, focus_keyword: str, meta_title: str = "", meta_description: str = "", slug: str = "",
              language: str = "vi") -> dict:
    """Score markdown 0-100 with the Yoast-style checklist. No LLM call. Returns per-criterion results."""
    return _score_seo(markdown, focus_keyword, meta_title, meta_description, slug, None, language)


@mcp.tool()
def score_readability(text: str, language: str = "vi") -> dict:
    """Readability 0-100 (English: Flesch Reading Ease; Vietnamese: sentence/paragraph length based). No LLM call."""
    return _score_readability(text, language)


@mcp.tool()
async def revise_content(content_id: int, instructions: str) -> dict:
    """Re-run Editor -> Social/SEO/Images -> QA on an existing item, applying the instructions. Returns a job_id."""
    job_id = services.revise_job(content_id, instructions)
    pipeline.start(job_id)
    return {"job_id": job_id, "status": "queued"}


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
def review_content(content_id: int, decision: str, note: str = "") -> dict:
    """Human approval gate. decision: approve | request_changes | reject (note required for request_changes).
    Only call this when the user has explicitly decided."""
    return services.review(content_id, decision, note)


@mcp.tool()
def schedule_content(content_id: int, platform: str, datetime: str) -> dict:
    """Schedule an APPROVED item on a platform (threads|facebook|linkedin). datetime: ISO 8601, e.g. 2026-11-03T09:00."""
    return services.schedule(content_id, platform, datetime)


@mcp.tool()
def get_calendar(start: str, end: str) -> list[dict]:
    """Scheduled posts between two ISO dates."""
    return services.calendar(start, end)


@mcp.tool()
def get_metrics(start: str | None = None, end: str | None = None) -> dict:
    """Aggregate metrics: counts by status, average SEO/readability, time and cost per article, items awaiting review."""
    return services.metrics(start, end)


# ---------------------------------------------------------------- resources
@mcp.resource("content://{content_id}/blog", mime_type="text/markdown")
def res_blog(content_id: int) -> str:
    """Blog markdown."""
    return services.get_content(content_id)["blog_md"]


@mcp.resource("content://{content_id}/social/{platform}", mime_type="text/plain")
def res_social(content_id: int, platform: str) -> str:
    """Social post for one platform."""
    return services.get_content(content_id)["social"].get(platform, "")


@mcp.resource("content://{content_id}/report", mime_type="application/json")
def res_report(content_id: int) -> dict:
    """QA + SEO + readability report."""
    c = services.get_content(content_id)
    return {"status": c["status"], "qa": c["qa_report"], "seo": c["seo_detail"], "readability_score": c["readability_score"]}


@mcp.resource("styleguide://{platform}", mime_type="text/markdown")
def res_styleguide(platform: str) -> str:
    """Style guide: blog | threads | facebook | linkedin."""
    return steps.style_guide(platform)


@mcp.resource("calendar://{month}", mime_type="application/json")
def res_calendar(month: str) -> list[dict]:
    """Schedule for a month, yyyy-mm."""
    y, m = map(int, month.split("-"))
    nxt = f"{y + (m == 12)}-{(m % 12) + 1:02d}-01"
    return services.calendar(f"{month}-01", f"{nxt}T00:00:00")


# ---------------------------------------------------------------- prompts
@mcp.prompt()
def content_campaign(topic: str, audience: str = "general readers", platforms: str = "threads,facebook,linkedin") -> str:
    """Run a whole content campaign."""
    return (f"Use create_content for the topic '{topic}' (audience: {audience}, platforms: {platforms}). "
            "Poll get_job every ~20 seconds until it is done. Then get_content and show me the blog title, SEO score, "
            "the social posts and the QA issues. Do NOT call review_content — ask me whether to approve.")


@mcp.prompt()
def review_checklist(content_id: int) -> str:
    """Checklist for the human reviewer."""
    return (f"Fetch content {content_id} with get_content. Check: facts have cited sources; tone matches the audience; "
            "no typos or run-together words; SEO score >= 80 and failing SEO items; each social post fits its platform; "
            "image prompts match the article. Summarise findings, then ask me to approve, request changes or reject.")


def main() -> None:
    if "--http" in sys.argv:
        import uvicorn

        from .api import app

        uvicorn.run(app, host="127.0.0.1", port=config.PORT)
    else:
        db.engine()
        mcp.run("stdio")


if __name__ == "__main__":
    main()
