import pytest

from content_agent import config, db

KW = "chuyển đổi số"
SENT = "Doanh nghiệp nhỏ cần bắt đầu từ những việc đơn giản và đo được kết quả mỗi tuần."  # 16 từ


def make_article(kw: str = KW, with_kw: bool = True, links: bool = True, h2: int = 4, sentences: int = 90) -> str:
    """Bài ~1400 từ, câu ngắn; keyword xuất hiện ~6 lần (mật độ ~1.3%)."""
    parts = [f"# {kw.capitalize()} cho doanh nghiệp nhỏ" if with_kw else "# Doanh nghiệp nhỏ"]
    parts.append((f"Bài viết về {kw}. " if with_kw else "Bài viết hướng dẫn. ") + SENT)
    per = sentences // h2
    for i in range(h2):
        title = f"{kw} bước {i + 1}" if with_kw and i == 0 else f"Bước {i + 1}"
        parts.append(f"## {title}")
        parts.append("\n\n".join(" ".join([SENT] * 3) for _ in range(per // 3)))
    if with_kw:
        parts.append(f"Kết luận: {kw} giúp tiết kiệm thời gian. Hãy áp dụng {kw} ngay hôm nay. Đừng quên {kw}.")
    if links:
        parts.append("Nguồn: [Bộ Kế hoạch](https://example.com/bao-cao)")
    return "\n\n".join(parts)


GOOD_META = {
    "meta_title": "Chuyển đổi số cho doanh nghiệp nhỏ",
    "meta_description": "Hướng dẫn chuyển đổi số cho doanh nghiệp nhỏ: bắt đầu từ đâu, cần công cụ gì và cách đo kết quả mỗi tuần một cách đơn giản.",
    "slug": "chuyen-doi-so",
}
GOOD_IMAGES = [{"prompt": "A small shop owner using a laptop", "alt": "Chủ shop dùng máy tính"}]


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(db, "_engine", None)
    yield
    if db._engine is not None:
        db._engine.dispose()
    monkeypatch.setattr(db, "_engine", None)
