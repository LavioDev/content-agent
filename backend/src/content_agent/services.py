"""Logic nghiệp vụ dùng chung cho REST API và MCP: tạo job, duyệt, lịch, số liệu."""
from datetime import datetime, timezone

from sqlmodel import func, select

from . import config, db
from .scoring import score_seo

SNAPSHOT_FIELDS = (
    "focus_keyword", "meta_title", "meta_description", "slug", "blog_md",
    "social", "image_prompts", "sources", "seo_score", "readability_score",
)


def _dt(value: str) -> datetime:
    """ISO 8601 -> datetime có múi giờ; chuỗi không có múi giờ coi là UTC."""
    d = datetime.fromisoformat(value)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class ServiceError(Exception):
    """Lỗi người dùng nhìn thấy được (trả về như tool error / HTTP 4xx)."""


def _get(s, model, id_):
    row = s.get(model, id_)
    if not row:
        raise ServiceError(f"{model.__name__.lower()} {id_} not found")
    return row


def rescore(c: db.Content) -> None:
    r = score_seo(c.blog_md, c.focus_keyword, c.meta_title, c.meta_description, c.slug, c.image_prompts, c.language)
    c.seo_score = r["score"]
    c.seo_detail = r
    c.readability_score = r["readability"]["score"]


def add_version(s, c: db.Content, by: str) -> None:
    c.version += 1
    c.updated_at = db.now()
    s.add(c)
    s.add(db.ContentVersion(content_id=c.id, version=c.version, created_by=by, snapshot={k: getattr(c, k) for k in SNAPSHOT_FIELDS}))


def create_job(topic: str, audience: str = "general readers", tone: str = "friendly", language: str = "vi",
               platforms: list[str] | None = None, word_count: int = 1500, variant: str = "full") -> int:
    platforms = platforms or list(config.PLATFORMS)
    if language not in ("vi", "en"):
        raise ServiceError("language must be 'vi' or 'en'")
    if bad := [p for p in platforms if p not in config.PLATFORMS]:
        raise ServiceError(f"unknown platform(s) {bad}; allowed: {list(config.PLATFORMS)}")
    if variant not in ("full", "no_editor", "no_qa_loop", "sequential"):
        raise ServiceError("unknown variant")
    if not topic.strip():
        raise ServiceError("topic is empty")
    inp = dict(topic=topic.strip(), audience=audience, tone=tone, language=language, platforms=platforms, word_count=word_count, variant=variant)
    with db.session() as s:
        job = db.Job(kind="create", input=inp)
        s.add(job)
        s.commit()
        c = db.Content(job_id=job.id, topic=inp["topic"], audience=audience, tone=tone, language=language, platforms=platforms)
        s.add(c)
        s.commit()
        job.content_id = c.id
        s.add(job)
        s.commit()
        return job.id


def revise_job(content_id: int, instructions: str) -> int:
    with db.session() as s:
        c = _get(s, db.Content, content_id)
        if c.status in ("running", "queued"):
            raise ServiceError("content is still being processed")
        job = db.Job(kind="revise", content_id=content_id, input={"content_id": content_id, "instructions": instructions})
        s.add(job)
        s.commit()
        c.job_id = job.id
        c.status = "queued"
        s.add(c)
        s.commit()
        return job.id


def get_job(job_id: int) -> dict:
    with db.session() as s:
        job = _get(s, db.Job, job_id)
        steps = s.exec(select(db.RunStep).where(db.RunStep.job_id == job_id).order_by(db.RunStep.id)).all()
        content = s.exec(select(db.Content).where(db.Content.job_id == job_id)).first()
        end = job.finished_at or db.now()
        return {
            **db.to_dict(job),
            "content_id": content.id if content else None,
            "steps": [db.to_dict(x) for x in steps],
            "elapsed_s": round((end - job.started_at).total_seconds(), 1),
            "cost_usd": round(sum(x.cost_usd for x in steps), 6),
            "tokens": sum(x.prompt_tokens + x.completion_tokens for x in steps),
        }


def _summary(c: db.Content) -> dict:
    return {k: getattr(c, k) for k in ("id", "job_id", "topic", "language", "status", "focus_keyword", "seo_score",
                                       "readability_score", "version")} | {
        "platforms": c.platforms, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat()}


def list_contents(status: str | None = None, q: str | None = None, start: str | None = None,
                  end: str | None = None, limit: int = 50) -> list[dict]:
    with db.session() as s:
        stmt = select(db.Content).order_by(db.Content.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(db.Content.status == status)
        if q:
            stmt = stmt.where(db.Content.topic.contains(q))
        if start:
            stmt = stmt.where(db.Content.created_at >= _dt(start))
        if end:
            stmt = stmt.where(db.Content.created_at <= _dt(end))
        return [_summary(c) for c in s.exec(stmt)]


def get_content(content_id: int) -> dict:
    with db.session() as s:
        c = _get(s, db.Content, content_id)
        versions = s.exec(select(db.ContentVersion).where(db.ContentVersion.content_id == content_id)
                          .order_by(db.ContentVersion.version.desc())).all()
        reviews = s.exec(select(db.Review).where(db.Review.content_id == content_id).order_by(db.Review.id.desc())).all()
        sched = s.exec(select(db.ScheduleEntry).where(db.ScheduleEntry.content_id == content_id)).all()
        job_ids = s.exec(select(db.Job.id).where(db.Job.content_id == content_id).order_by(db.Job.id)).all()
        return db.to_dict(c) | {
            "jobs": [get_job(j) for j in job_ids],
            "versions": [{"version": v.version, "created_by": v.created_by, "created_at": v.created_at.isoformat()} for v in versions],
            "reviews": [db.to_dict(r) for r in reviews],
            "schedule": [db.to_dict(x) for x in sched],
        }


def delete_content(content_id: int) -> None:
    with db.session() as s:
        c = _get(s, db.Content, content_id)
        if c.status in ("running", "queued"):
            raise ServiceError("content is still being processed")
        job_ids = s.exec(select(db.Job.id).where(db.Job.content_id == content_id)).all()
        for model, col in ((db.RunStep, db.RunStep.job_id), (db.Job, db.Job.id)):
            for row in s.exec(select(model).where(col.in_(job_ids))):
                s.delete(row)
        for model in (db.ContentVersion, db.Review, db.ScheduleEntry):
            for row in s.exec(select(model).where(model.content_id == content_id)):
                s.delete(row)
        s.delete(c)
        s.commit()


def patch_content(content_id: int, **fields) -> dict:
    allowed = {"blog_md", "meta_title", "meta_description", "slug", "focus_keyword", "social", "image_prompts"}
    if bad := set(fields) - allowed:
        raise ServiceError(f"cannot edit fields {sorted(bad)}")
    with db.session() as s:
        c = _get(s, db.Content, content_id)
        if c.status in ("running", "queued"):
            raise ServiceError("content is still being processed")
        for k, v in fields.items():
            setattr(c, k, v)
        rescore(c)
        add_version(s, c, "human")
        s.commit()
    return get_content(content_id)


def review(content_id: int, decision: str, note: str = "") -> dict:
    new_status = {"approve": "approved", "request_changes": "changes_requested", "reject": "rejected"}.get(decision)
    if not new_status:
        raise ServiceError("decision must be approve, request_changes or reject")
    with db.session() as s:
        c = _get(s, db.Content, content_id)
        if c.status not in ("pending_review", "changes_requested", "approved", "scheduled"):
            raise ServiceError(f"content is '{c.status}', it can only be reviewed once the pipeline has finished")
        if decision == "request_changes" and not note.strip():
            raise ServiceError("a note is required when requesting changes")
        c.status = new_status
        c.updated_at = db.now()
        s.add(c)
        s.add(db.Review(content_id=content_id, decision=decision, note=note))
        s.commit()
    return {"content_id": content_id, "status": new_status}


def schedule(content_id: int, platform: str, when: str) -> dict:
    with db.session() as s:
        c = _get(s, db.Content, content_id)
        if c.status not in ("approved", "scheduled"):
            raise ServiceError("only approved content can be scheduled")
        if platform not in config.PLATFORMS:
            raise ServiceError(f"platform must be one of {list(config.PLATFORMS)}")
        entry = db.ScheduleEntry(content_id=content_id, platform=platform, scheduled_at=_dt(when))
        c.status = "scheduled"
        s.add_all([entry, c])
        s.commit()
        return db.to_dict(entry)


def unschedule(entry_id: int) -> None:
    with db.session() as s:
        e = _get(s, db.ScheduleEntry, entry_id)
        c = s.get(db.Content, e.content_id)
        s.delete(e)
        s.commit()
        left = s.exec(select(db.ScheduleEntry).where(db.ScheduleEntry.content_id == e.content_id)).first()
        if c and c.status == "scheduled" and not left:
            c.status = "approved"
            s.add(c)
            s.commit()


def calendar(start: str, end: str) -> list[dict]:
    with db.session() as s:
        rows = s.exec(select(db.ScheduleEntry, db.Content).join(db.Content, db.Content.id == db.ScheduleEntry.content_id)
                      .where(db.ScheduleEntry.scheduled_at >= _dt(start),
                             db.ScheduleEntry.scheduled_at <= _dt(end))
                      .order_by(db.ScheduleEntry.scheduled_at)).all()
        return [db.to_dict(e) | {"topic": c.topic, "seo_score": c.seo_score} for e, c in rows]


def metrics(start: str | None = None, end: str | None = None) -> dict:
    with db.session() as s:
        cstmt = select(db.Content)
        if start:
            cstmt = cstmt.where(db.Content.created_at >= _dt(start))
        if end:
            cstmt = cstmt.where(db.Content.created_at <= _dt(end))
        contents = s.exec(cstmt).all()
        done = [c for c in contents if c.status not in ("queued", "running", "failed")]
        by_status: dict[str, int] = {}
        by_day: dict[str, int] = {}
        for c in contents:
            by_status[c.status] = by_status.get(c.status, 0) + 1
            by_day[c.created_at.date().isoformat()] = by_day.get(c.created_at.date().isoformat(), 0) + 1
        jobs = {j.id: j for j in s.exec(select(db.Job).where(db.Job.status == "done"))}
        cost = dict(s.exec(select(db.RunStep.job_id, func.sum(db.RunStep.cost_usd)).group_by(db.RunStep.job_id)).all())
        times = [(jobs[c.job_id].finished_at - jobs[c.job_id].started_at).total_seconds() for c in done if c.job_id in jobs and jobs[c.job_id].finished_at]
        costs = [cost.get(c.job_id, 0) for c in done if c.job_id in jobs]

        def avg(xs):
            return round(sum(xs) / len(xs), 3) if xs else 0

        return {
            "total": len(contents),
            "by_status": by_status,
            "by_day": [{"date": d, "count": n} for d, n in sorted(by_day.items())],
            "avg_seo": avg([c.seo_score for c in done]),
            "avg_readability": avg([c.readability_score for c in done]),
            "avg_seconds": avg(times),
            "avg_cost_usd": avg(costs),
            "pending_review": [_summary(c) for c in contents if c.status == "pending_review"],
        }
