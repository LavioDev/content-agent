"""Chạy 1 bài thật qua pipeline, in kết quả. Dùng: python scripts/run_one.py "chủ đề" [vi|en]"""
import asyncio
import os
import sys

os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from content_agent import pipeline, services  # noqa: E402


async def main(topic: str, lang: str) -> None:
    job_id = services.create_job(topic, "chủ shop online" if lang == "vi" else "small business owners", "friendly", lang)
    await pipeline.run_job(job_id)
    job = services.get_job(job_id)
    print(f"job={job_id} status={job['status']} elapsed={job['elapsed_s']}s tokens={job['tokens']} cost=${job['cost_usd']} error={job['error']}")
    for s in job["steps"]:
        t = (s["finished_at"] or s["started_at"])[11:19] if s["finished_at"] else "-"
        print(f"  {s['agent']:<10} {s['status']:<7} in={s['prompt_tokens']:>6} out={s['completion_tokens']:>6} ${s['cost_usd']:.5f} {s['note']}")
    c = services.get_content(job["content_id"])
    print(f"status={c['status']} seo={c['seo_score']} readability={c['readability_score']} words={c['qa_report'].get('word_count')} kw={c['focus_keyword']!r}")
    print("qa:", c["qa_report"].get("problems"), c["qa_report"].get("issues"))
    for i in c["seo_detail"]["items"]:
        print(("  ok  " if i["passed"] else "  FAIL"), i["label"], i["detail"])
    print("sources:", [s["url"] for s in c["sources"]])
    print("\n", c["blog_md"][:1200], "\n...\n", c["social"])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "vi"))
