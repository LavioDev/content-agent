"""REST + SSE cho dashboard, đồng thời mount MCP streamable-HTTP tại /mcp."""
import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import select

from . import config, db, pipeline, services
from .mcp_server import mcp


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.engine()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="AI Content Agent", lifespan=lifespan)


@app.exception_handler(services.ServiceError)
async def _service_error(_: Request, e: services.ServiceError):
    return JSONResponse({"detail": str(e)}, status_code=404 if "not found" in str(e) else 400)


@app.middleware("http")
async def _mcp_auth(request: Request, call_next):
    if config.MCP_TOKEN and request.url.path.startswith("/mcp") and request.headers.get("authorization") != f"Bearer {config.MCP_TOKEN}":
        return JSONResponse({"detail": "invalid or missing MCP token"}, status_code=401)
    return await call_next(request)


class JobIn(BaseModel):
    topic: str
    audience: str = "general readers"
    tone: str = "friendly"
    language: str = "vi"
    platforms: list[str] | None = None
    word_count: int = 1500


class ReviewIn(BaseModel):
    decision: str
    note: str = ""


class ScheduleIn(BaseModel):
    platform: str
    datetime: str


class ReviseIn(BaseModel):
    instructions: str


@app.post("/api/jobs")
async def create_job(body: JobIn):
    job_id = services.create_job(**body.model_dump())
    pipeline.start(job_id)
    return services.get_job(job_id)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int):
    return services.get_job(job_id)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: int):
    """SSE: gửi 'snapshot' mỗi khi job/step đổi; kết thúc khi job done/failed. Đọc từ DB nên hoạt động cả khi job chạy ở process MCP khác."""
    services.get_job(job_id)  # 404 sớm

    async def gen():
        last = None
        while True:
            snap = services.get_job(job_id)
            key = json.dumps({k: snap[k] for k in ("status", "current_step", "steps")}, default=str)
            if key != last:
                last = key
                yield f"event: snapshot\ndata: {json.dumps(snap, default=str)}\n\n"
            if snap["status"] in ("done", "failed"):
                yield f"event: end\ndata: {snap['status']}\n\n"
                return
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/contents")
def list_contents(status: str | None = None, q: str | None = None, start: str | None = None, end: str | None = None, limit: int = 50):
    return services.list_contents(status, q, start, end, limit)


@app.get("/api/contents/{content_id}")
def get_content(content_id: int):
    return services.get_content(content_id)


@app.delete("/api/contents/{content_id}")
def delete_content(content_id: int):
    services.delete_content(content_id)
    return {"ok": True}


@app.patch("/api/contents/{content_id}")
def patch_content(content_id: int, body: dict):
    return services.patch_content(content_id, **body)


@app.post("/api/contents/{content_id}/review")
def review(content_id: int, body: ReviewIn):
    return services.review(content_id, body.decision, body.note)


@app.post("/api/contents/{content_id}/revise")
async def revise(content_id: int, body: ReviseIn):
    job_id = services.revise_job(content_id, body.instructions)
    pipeline.start(job_id)
    return services.get_job(job_id)


@app.post("/api/contents/{content_id}/schedule")
def schedule(content_id: int, body: ScheduleIn):
    return services.schedule(content_id, body.platform, body.datetime)


@app.delete("/api/schedule/{entry_id}")
def unschedule(entry_id: int):
    services.unschedule(entry_id)
    return {"ok": True}


@app.get("/api/calendar")
def calendar(start: str, end: str):
    return services.calendar(start, end)


@app.get("/api/metrics")
def metrics(start: str | None = None, end: str | None = None):
    return services.metrics(start, end)


@app.get("/api/benchmarks")
def benchmarks():
    with db.session() as s:
        return [db.to_dict(b) for b in s.exec(select(db.BenchmarkRun).order_by(db.BenchmarkRun.id.desc()))]


@app.get("/api/settings")
def settings():
    return {"model": config.MODEL, "provider": config.PROVIDER, "price_in": config.PRICE_IN, "price_out": config.PRICE_OUT,
            "search": "serper" if config.SERPER_API_KEY else "duckduckgo", "mcp_endpoint": f"http://127.0.0.1:{config.PORT}/mcp",
            "mcp_auth": bool(config.MCP_TOKEN), "project_root": str(config.ROOT), "platforms": list(config.PLATFORMS), "qa_rounds": config.MAX_QA_ROUNDS}


app.mount("/", mcp.streamable_http_app())  # phải đặt cuối để không che /api/*


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=config.PORT)


if __name__ == "__main__":
    main()
