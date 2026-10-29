from datetime import datetime, timezone

from sqlalchemy import JSON, Column, event
from sqlmodel import Field, Session, SQLModel, create_engine

from . import config


def now() -> datetime:
    return datetime.now(timezone.utc)


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str = "create"  # create | revise
    content_id: int | None = Field(default=None, index=True)
    input: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = "queued"  # queued | running | done | failed
    current_step: str = ""
    error: str = ""
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None


class RunStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    agent: str
    status: str = "running"  # running | done | failed
    note: str = ""
    started_at: datetime = Field(default_factory=now)
    finished_at: datetime | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class Content(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    topic: str
    audience: str = ""
    tone: str = ""
    language: str = "vi"
    platforms: list = Field(default_factory=list, sa_column=Column(JSON))
    # queued | running | pending_review | changes_requested | approved | rejected | scheduled | failed
    status: str = "queued"
    focus_keyword: str = ""
    meta_title: str = ""
    meta_description: str = ""
    slug: str = ""
    blog_md: str = ""
    social: dict = Field(default_factory=dict, sa_column=Column(JSON))
    image_prompts: list = Field(default_factory=list, sa_column=Column(JSON))
    sources: list = Field(default_factory=list, sa_column=Column(JSON))
    outline: list = Field(default_factory=list, sa_column=Column(JSON))
    keywords: list = Field(default_factory=list, sa_column=Column(JSON))
    seo_score: float = 0
    seo_detail: dict = Field(default_factory=dict, sa_column=Column(JSON))
    readability_score: float = 0
    qa_report: dict = Field(default_factory=dict, sa_column=Column(JSON))
    version: int = 0
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class ContentVersion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    content_id: int = Field(index=True)
    version: int
    snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_by: str = "agent"  # agent | human
    created_at: datetime = Field(default_factory=now)


class Review(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    content_id: int = Field(index=True)
    decision: str
    note: str = ""
    created_at: datetime = Field(default_factory=now)


class ScheduleEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    content_id: int = Field(index=True)
    platform: str
    scheduled_at: datetime
    status: str = "scheduled"  # scheduled | published


class SearchCache(SQLModel, table=True):
    query: str = Field(primary_key=True)
    language: str = Field(primary_key=True)
    result: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class BenchmarkRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))
    results: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{config.DB_PATH}", connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(_engine, "connect")
        def _wal(conn, _):  # API và MCP là 2 process cùng ghi 1 file
            conn.execute("PRAGMA journal_mode=WAL")

        SQLModel.metadata.create_all(_engine)
        with _engine.begin() as conn:  # migration: DB cũ chưa có job.content_id
            if "content_id" not in [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(job)")]:
                conn.exec_driver_sql("ALTER TABLE job ADD COLUMN content_id INTEGER")
                conn.exec_driver_sql("UPDATE job SET content_id = (SELECT id FROM content WHERE content.job_id = job.id) WHERE kind = 'create'")
                conn.exec_driver_sql("UPDATE job SET content_id = json_extract(input, '$.content_id') WHERE kind = 'revise'")
    return _engine


def session() -> Session:
    return Session(engine(), expire_on_commit=False)


def to_dict(row: SQLModel) -> dict:
    return row.model_dump(mode="json")
