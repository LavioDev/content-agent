"""Chạy benchmark pipeline trên bộ từ khoá và lưu kết quả vào DB (hiện ở trang /benchmark).

Chạy từ thư mục backend, bằng python của venv:
  .venv\\Scripts\\python ..\\eval\\benchmark.py --variant full --limit 5
variant: full | no_editor | no_qa_loop | sequential   (ablation, xem docs/report/README.md mục 2)
--skip N --limit M: lấy bài thứ N+1..N+M sau khi xen kẽ vi/en; --name <variant>-extra để report.py gộp vào variant
--concurrency: số bài chạy cùng lúc (mặc định 1)
--human-rating: điểm TB 1-5 từ 5 người chấm (nhập tay sau khi có kết quả rating)
"""
import argparse
import asyncio
import json
import statistics as st
from datetime import datetime
from pathlib import Path

from content_agent import config, db, pipeline, services

KEYWORDS = Path(__file__).with_name("keywords.json")


async def run_one(item: dict, variant: str) -> dict:
    job_id = services.create_job(item["topic"], item["audience"], "friendly", item["language"], variant=variant)
    await pipeline.run_job(job_id)
    job = services.get_job(job_id)
    c = services.get_content(job["content_id"])
    return {
        "topic": item["topic"], "language": item["language"], "status": job["status"], "content_id": c["id"],
        "seo": c["seo_score"], "readability": c["readability_score"], "words": c["qa_report"].get("word_count", 0),
        "seconds": job["elapsed_s"], "cost_usd": job["cost_usd"], "qa_rounds": c["qa_report"].get("round", 0),
        "tokens": job["tokens"],
        # theo agent, để report.py vẽ thời gian/chi phí từng bước
        "steps": [{
            "agent": x["agent"], "cost_usd": x["cost_usd"], "tokens": x["prompt_tokens"] + x["completion_tokens"],
            "seconds": round((datetime.fromisoformat(x["finished_at"]) - datetime.fromisoformat(x["started_at"])).total_seconds(), 1)
            if x["finished_at"] else 0,
        } for x in job["steps"]],
    }


async def main(a: argparse.Namespace) -> None:
    items = json.loads(KEYWORDS.read_text(encoding="utf-8"))
    if a.language:
        items = [i for i in items if i["language"] == a.language]
    # xen kẽ vi/en khi giới hạn số bài để mẫu nhỏ vẫn cân bằng
    items = [x for pair in zip([i for i in items if i["language"] == "vi"], [i for i in items if i["language"] == "en"]) for x in pair] or items
    items = items[a.skip : a.skip + a.limit]
    rows, sem = [], asyncio.Semaphore(a.concurrency)  # thời gian chờ LLM là chính nên chạy song song được; seconds đo dưới tải

    async def one(item: dict) -> None:
        async with sem:
            r = await run_one(item, a.variant)
        rows.append(r)
        print(f"[{len(rows)}/{len(items)}] {r['status']:<6} seo={r['seo']:>5} read={r['readability']:>5} {r['seconds']:>6.0f}s ${r['cost_usd']:.4f}  {r['topic']}", flush=True)

    await asyncio.gather(*(one(i) for i in items))
    ok = [r for r in rows if r["status"] == "done"]
    if not ok:
        raise SystemExit("không có bài nào chạy thành công")
    avg = lambda k: round(st.mean(r[k] for r in ok), 3)  # noqa: E731
    results = {
        "n": len(ok), "failed": len(rows) - len(ok), "avg_seo": avg("seo"), "avg_readability": avg("readability"),
        "avg_seconds": avg("seconds"), "avg_cost_usd": avg("cost_usd"), "avg_words": avg("words"),
        "seo_pass_rate": round(sum(r["seo"] >= 80 for r in ok) / len(ok), 3), "items": rows,
    }
    if a.human_rating:
        results["human_rating"] = a.human_rating
    with db.session() as s:
        s.add(db.BenchmarkRun(name=a.name or a.variant, config={"variant": a.variant, "model": config.MODEL, "provider": config.PROVIDER, "n": len(rows)}, results=results))
        s.commit()
    print({k: v for k, v in results.items() if k != "items"})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--variant", default="full", choices=["full", "no_editor", "no_qa_loop", "sequential"])
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--skip", type=int, default=0, help="bỏ N bài đầu (chạy tiếp phần từ khoá chưa dùng)")
    p.add_argument("--concurrency", type=int, default=1, help="số bài chạy song song")
    p.add_argument("--language", choices=["vi", "en"])
    p.add_argument("--name")
    p.add_argument("--human-rating", type=float)
    asyncio.run(main(p.parse_args()))
