"""Điều phối pipeline: Researcher → Writer → Editor → (Social ∥ SEO ∥ Images) → QA (vòng lặp về Editor ≤ 2 lần)."""
import asyncio

from sqlmodel import select

from . import config, db, services, steps
from .llm import Usage
from .scoring.text import words

_tasks: set[asyncio.Task] = set()  # giữ tham chiếu để task nền không bị GC


def start(job_id: int) -> None:
    t = asyncio.create_task(run_job(job_id))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def _save(content_id: int, **fields) -> None:
    with db.session() as s:
        c = s.get(db.Content, content_id)
        for k, v in fields.items():
            setattr(c, k, v)
        c.updated_at = db.now()
        s.add(c)
        s.commit()


async def _step(job_id: int, agent: str, fn, *args, note: str = ""):
    with db.session() as s:
        st = db.RunStep(job_id=job_id, agent=agent, note=note)
        s.add(st)
        job = s.get(db.Job, job_id)
        job.current_step = agent
        s.add(job)
        s.commit()
        step_id = st.id

    def finish(status: str, usage: Usage, note_: str = ""):
        with db.session() as s:
            st = s.get(db.RunStep, step_id)
            st.status, st.finished_at = status, db.now()
            st.prompt_tokens, st.completion_tokens, st.cost_usd = usage.prompt, usage.completion, usage.cost
            st.note = note_ or st.note
            s.add(st)
            s.commit()

    try:
        value, usage = await asyncio.to_thread(fn, *args)
    except Exception as e:
        finish("failed", Usage(), str(e)[:500])
        raise
    finish("done", usage)
    return value


def evaluate(c: db.Content) -> dict:
    """Kiểm tra bằng luật cứng; pass khi mọi mục đạt."""
    services.rescore(c)
    failed = [f"{i['label']} ({i['detail']})" for i in c.seo_detail["items"] if not i["passed"]]
    problems = []
    if c.seo_score < 80:
        problems.append(f"SEO score is {c.seo_score}/100 (need >= 80). Failing checks: " + "; ".join(failed))
    if not c.seo_detail["readability"]["passed"]:
        problems.append(f"Readability is {c.readability_score}/100: shorten long sentences and paragraphs")
    for p in c.platforms:
        text = c.social.get(p, "")
        if not text:
            problems.append(f"Missing {p} post")
        elif len(text) > config.PLATFORM_LIMITS[p]:
            problems.append(f"{p} post has {len(text)} characters, limit is {config.PLATFORM_LIMITS[p]}")
    return {
        "passed": not problems,
        "problems": problems,
        "seo_score": c.seo_score,
        "readability_score": c.readability_score,
        "word_count": len(words(c.blog_md)),
    }


async def run_job(job_id: int) -> None:
    with db.session() as s:
        job = s.get(db.Job, job_id)
        content = s.exec(select(db.Content).where(db.Content.job_id == job_id)).one()
        job.status = "running"
        s.add(job)
        s.commit()
        cid, inp, kind = content.id, dict(job.input), job.kind
    _save(cid, status="running")
    try:
        with db.session() as s:
            c = s.get(db.Content, cid)
            lang, tone, platforms = c.language, c.tone, list(c.platforms)
            blog, keyword, keywords = c.blog_md, c.focus_keyword, list(c.keywords)
            audience, topic = c.audience, c.topic

        variant = inp.get("variant", "full")  # ablation: full | no_editor | no_qa_loop | sequential
        feedback = ""
        if kind == "create":
            r = await _step(job_id, "researcher", steps.research, topic, audience, lang)
            keyword, keywords = r["focus_keyword"], r.get("keywords", [])
            _save(cid, outline=r["outline"], sources=r["sources"], focus_keyword=keyword, keywords=keywords)
            blog = await _step(job_id, "writer", steps.write, r, topic, audience, tone, lang, inp.get("word_count", 1500))
            _save(cid, blog_md=blog)
        else:
            feedback = inp["instructions"]

        if variant != "no_editor" or feedback:
            blog = await _step(job_id, "editor", steps.edit, blog, lang, tone, feedback)
            _save(cid, blog_md=blog)

        jobs = [
            lambda: _step(job_id, "social", steps.social, blog, platforms, lang, tone, audience),
            lambda: _step(job_id, "seo", steps.seo, blog, keyword, keywords, lang),
            lambda: _step(job_id, "images", steps.images, blog, lang),
        ]
        if variant == "sequential":
            soc, seo_out, imgs = [await j() for j in jobs]
        else:
            soc, seo_out, imgs = await asyncio.gather(*(j() for j in jobs))
        _save(cid, social=soc, image_prompts=imgs, **seo_out)

        max_rounds = 0 if variant == "no_qa_loop" else config.MAX_QA_ROUNDS
        for rnd in range(max_rounds + 1):
            with db.session() as s:
                c = s.get(db.Content, cid)
                report = evaluate(c)
                blog_now = c.blog_md
            issues = await _step(job_id, "qa", steps.qa, report, blog_now, lang, note=f"round {rnd + 1}")
            report |= {"issues": issues, "round": rnd + 1}
            if report["passed"] or rnd == max_rounds:
                break
            fb = "\n".join(report["problems"] + issues)
            blog = await _step(job_id, "editor", steps.edit, blog_now, lang, tone, fb, note=f"QA fix {rnd + 1}")
            seo_out = await _step(job_id, "seo", steps.seo, blog, keyword, keywords, lang, note=f"after QA fix {rnd + 1}")
            _save(cid, **seo_out)

        with db.session() as s:
            c = s.get(db.Content, cid)
            services.rescore(c)
            c.qa_report = report
            c.status = "pending_review"
            services.add_version(s, c, "agent")
            job = s.get(db.Job, job_id)
            job.status, job.finished_at, job.current_step = "done", db.now(), ""
            s.add(job)
            s.commit()
    except Exception as e:
        with db.session() as s:
            job = s.get(db.Job, job_id)
            job.status, job.error, job.finished_at = "failed", str(e)[:500], db.now()
            c = s.get(db.Content, cid)
            c.status = "changes_requested" if kind == "revise" else "failed"
            s.add_all([job, c])
            s.commit()
