"""Test luồng pipeline với LLM giả (không tốn tiền, không cần mạng)."""
import pytest
from sqlmodel import select

from content_agent import db, pipeline, services, steps
from content_agent.llm import Usage

from .conftest import GOOD_IMAGES, GOOD_META, KW, make_article

U = Usage(100, 50)
GOOD = make_article()
BAD = make_article(with_kw=False)


@pytest.fixture
def fake(monkeypatch):
    calls = []

    def rec(name, value):
        def fn(*a, **k):
            calls.append(name)
            return (value(len(calls)) if callable(value) else value), U
        return fn

    research = {"focus_keyword": KW, "keywords": ["số hoá"], "outline": ["Mở đầu", "Kết"], "sources": []}
    monkeypatch.setattr(steps, "research", rec("research", research))
    monkeypatch.setattr(steps, "write", rec("write", BAD))
    monkeypatch.setattr(steps, "edit", rec("edit", lambda n: BAD))
    monkeypatch.setattr(steps, "social", rec("social", {"threads": "a", "facebook": "b", "linkedin": "c"}))
    monkeypatch.setattr(steps, "images", rec("images", GOOD_IMAGES))
    monkeypatch.setattr(steps, "qa", rec("qa", ["ok"]))
    return calls, monkeypatch


def set_seo(monkeypatch, outputs):
    it = iter(outputs)
    monkeypatch.setattr(steps, "seo", lambda *a, **k: ({**GOOD_META, "blog_md": next(it)}, U))


async def run(**kw):
    job_id = services.create_job("chuyển đổi số", **kw)
    await pipeline.run_job(job_id)
    return job_id


async def test_happy_path_ends_in_pending_review(fake):
    calls, mp = fake
    set_seo(mp, [GOOD])
    job_id = await run(platforms=["threads", "facebook", "linkedin"])
    job = services.get_job(job_id)
    assert job["status"] == "done"
    assert [s["agent"] for s in job["steps"]] == ["researcher", "writer", "editor", "social", "seo", "images", "qa"]
    assert job["cost_usd"] > 0 and job["tokens"] == 7 * 150
    c = services.get_content(job["content_id"])
    assert c["status"] == "pending_review" and c["seo_score"] >= 80 and c["qa_report"]["passed"]
    assert c["version"] == 1 and c["focus_keyword"] == KW


async def test_qa_failure_loops_back_to_editor(fake):
    calls, mp = fake
    set_seo(mp, [BAD, GOOD])  # lần 1 SEO kém -> QA fail -> Editor+SEO lần 2 đạt
    job_id = await run()
    job = services.get_job(job_id)
    assert calls.count("edit") == 2
    assert [s["agent"] for s in job["steps"]].count("qa") == 2
    assert services.get_content(job["content_id"])["qa_report"]["round"] == 2


async def test_qa_gives_up_after_max_rounds(fake):
    calls, mp = fake
    set_seo(mp, [BAD] * 5)
    job_id = await run()
    c = services.get_content(services.get_job(job_id)["content_id"])
    assert c["status"] == "pending_review" and not c["qa_report"]["passed"]
    assert c["qa_report"]["round"] == 3 and calls.count("edit") == 3  # 1 + 2 vòng sửa


async def test_step_failure_marks_job_and_content_failed(fake):
    calls, mp = fake
    mp.setattr(steps, "research", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    job_id = await run()
    job = services.get_job(job_id)
    assert job["status"] == "failed" and "boom" in job["error"]
    assert job["steps"][0]["status"] == "failed"
    assert services.get_content(job["content_id"])["status"] == "failed"


async def test_revise_reruns_from_editor(fake):
    calls, mp = fake
    set_seo(mp, [GOOD, GOOD])
    cid = services.get_job(await run())["content_id"]
    calls.clear()
    job_id = services.revise_job(cid, "thêm ví dụ")
    await pipeline.run_job(job_id)
    assert calls[0] == "edit" and "research" not in calls and "write" not in calls
    assert services.get_content(cid)["version"] == 2


async def test_review_schedule_and_edit_rules(fake):
    calls, mp = fake
    set_seo(mp, [GOOD])
    cid = services.get_job(await run())["content_id"]
    with pytest.raises(services.ServiceError):
        services.schedule(cid, "facebook", "2026-11-03T09:00")  # chưa duyệt
    with pytest.raises(services.ServiceError):
        services.review(cid, "request_changes", "")  # thiếu ghi chú
    services.review(cid, "approve")
    entry = services.schedule(cid, "facebook", "2026-11-03T09:00")
    assert services.get_content(cid)["status"] == "scheduled"
    assert len(services.calendar("2026-11-01", "2026-11-30")) == 1
    services.unschedule(entry["id"])
    assert services.get_content(cid)["status"] == "approved"
    c = services.patch_content(cid, meta_title="Mới")
    assert c["version"] == 2 and c["versions"][0]["created_by"] == "human"
    m = services.metrics()
    assert m["total"] == 1 and m["avg_seo"] >= 80


def test_create_job_validation():
    with pytest.raises(services.ServiceError):
        services.create_job("x", language="fr")
    with pytest.raises(services.ServiceError):
        services.create_job("x", platforms=["tiktok"])
    with pytest.raises(services.ServiceError):
        services.create_job("  ")


async def test_ablation_variants(fake):
    calls, mp = fake
    set_seo(mp, [GOOD])
    job_id = services.create_job("x", variant="no_editor")
    await pipeline.run_job(job_id)
    assert "edit" not in calls  # bỏ Editor

    calls.clear()
    set_seo(mp, [BAD])
    job_id = services.create_job("x", variant="no_qa_loop")
    await pipeline.run_job(job_id)
    steps_ = [s["agent"] for s in services.get_job(job_id)["steps"]]
    assert steps_.count("qa") == 1 and steps_.count("editor") == 1  # không có vòng sửa

    calls.clear()
    set_seo(mp, [GOOD])
    job_id = services.create_job("x", variant="sequential")
    await pipeline.run_job(job_id)
    order = [s["agent"] for s in services.get_job(job_id)["steps"]]
    assert order[3:6] == ["social", "seo", "images"] and services.get_job(job_id)["status"] == "done"
    with pytest.raises(services.ServiceError):
        services.create_job("x", variant="nope")


async def test_content_jobs_history_and_delete(fake):
    calls, mp = fake
    set_seo(mp, [GOOD, GOOD])
    cid = services.get_job(await run())["content_id"]
    await pipeline.run_job(services.revise_job(cid, "rút gọn mở đầu"))
    jobs = services.get_content(cid)["jobs"]
    assert [j["kind"] for j in jobs] == ["create", "revise"]
    assert jobs[1]["input"]["instructions"] == "rút gọn mở đầu" and jobs[0]["steps"]
    services.delete_content(cid)
    with pytest.raises(services.ServiceError):
        services.get_content(cid)
    with db.session() as s:
        assert not s.exec(select(db.RunStep)).all() and not s.exec(select(db.Job)).all()
