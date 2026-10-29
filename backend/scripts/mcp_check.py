"""Kiểm tra MCP bằng client thật. Dùng: python scripts/mcp_check.py http|stdio [chủ đề]
http: cần backend đang chạy (content-api). stdio: tự khởi động content-mcp."""
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

ROOT = Path(__file__).resolve().parents[2]


def data(res):
    if res.isError:
        raise SystemExit(f"TOOL ERROR: {res.content[0].text}")
    return res.structuredContent.get("result", res.structuredContent) if res.structuredContent else json.loads(res.content[0].text)


async def check(s: ClientSession, topic: str, full: bool) -> None:
    await s.initialize()
    tools = (await s.list_tools()).tools
    res = (await s.list_resource_templates()).resourceTemplates
    prompts = (await s.list_prompts()).prompts
    print(f"tools={len(tools)} resource_templates={len(res)} prompts={len(prompts)}")
    review = next(t for t in tools if t.name == "review_content")
    print("review_content destructiveHint =", review.annotations.destructiveHint)

    print("score_seo ->", data(await s.call_tool("score_seo", {"markdown": "# Xin chào\n\nNội dung ngắn.", "focus_keyword": "xin chào"}))["score"])
    print("score_readability ->", data(await s.call_tool("score_readability", {"text": "Câu ngắn. Rất dễ đọc.", "language": "vi"}))["score"])
    print("styleguide ->", (await s.read_resource("styleguide://threads")).contents[0].text[:40].replace("\n", " "))
    bad = await s.call_tool("get_job", {"job_id": 99999})
    print("error case ->", bad.isError, bad.content[0].text[:80])
    if not full:
        return

    job = data(await s.call_tool("create_content", {"topic": topic, "audience": "người mới bắt đầu", "language": "vi", "word_count": 800}))
    print("created", job)
    while True:
        await asyncio.sleep(10)
        j = data(await s.call_tool("get_job", {"job_id": job["job_id"]}))
        print(f"  {j['status']:<8} step={j['current_step']:<10} {j['elapsed_s']}s ${j['cost_usd']}")
        if j["status"] in ("done", "failed"):
            break
    if j["status"] != "done":
        raise SystemExit(f"JOB FAILED: {j['error']}")
    cid = j["content_id"]
    c = data(await s.call_tool("get_content", {"content_id": cid, "part": "qa"}))
    print("qa part ->", c["status"], c["seo_score"], c["readability_score"])
    print("resource blog ->", len((await s.read_resource(f"content://{cid}/blog")).contents[0].text), "chars")
    print("pending ->", [x["id"] for x in data(await s.call_tool("list_contents", {"status": "pending_review"}))])
    print("review (without note) ->", data(await s.call_tool("review_content", {"content_id": cid, "decision": "approve"})))
    print("schedule ->", data(await s.call_tool("schedule_content", {"content_id": cid, "platform": "facebook", "datetime": "2026-11-03T09:00:00+07:00"}))["scheduled_at"])
    print("metrics ->", {k: v for k, v in data(await s.call_tool("get_metrics", {})).items() if k.startswith("avg")})


async def main(mode: str, topic: str) -> None:
    if mode == "http":
        async with streamablehttp_client("http://127.0.0.1:8787/mcp") as (r, w, _), ClientSession(r, w) as s:
            await check(s, topic, full=True)
    else:
        params = StdioServerParameters(command=str(ROOT / "backend/.venv/Scripts/content-mcp.exe"), args=[])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await check(s, topic, full=len(sys.argv) > 3 and sys.argv[3] == "full")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "cách học tiếng Anh mỗi ngày"))
