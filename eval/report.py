"""Đọc kết quả BenchmarkRun trong DB -> in bảng markdown + ghi chart PNG vào docs/report/img/.

Chạy từ thư mục backend, bằng python của venv (cần matplotlib: pip install -e ".[dev]"):
  .venv\\Scripts\\python ..\\eval\\report.py              # run mới nhất của mỗi variant
  .venv\\Scripts\\python ..\\eval\\report.py --ids 3,4,5  # chọn run cụ thể
  .venv\\Scripts\\python ..\\eval\\report.py --self-check # tự kiểm tra bằng dữ liệu giả
"""
import argparse
import statistics as st
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "report"
PASS_SEO = 80
VARIANTS = ["full", "no_editor", "no_qa_loop", "sequential"]
LABEL = {"full": "Đầy đủ", "no_editor": "Bỏ Editor", "no_qa_loop": "Bỏ vòng QA", "sequential": "Chạy tuần tự"}
AGENTS = ["researcher", "writer", "editor", "social", "seo", "images", "qa"]
# bảng màu categorical của skill dataviz, thứ tự cố định, đã chạy validate_palette.js (light)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
COLOR = dict(zip(VARIANTS, PALETTE))
AGENT_COLOR = dict(zip(AGENTS, PALETTE))
INK, INK2, MUTED, GRID, BASE, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
    "axes.edgecolor": BASE, "axes.facecolor": SURF, "figure.facecolor": SURF, "xtick.color": INK2, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y",
    "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.titlelocation": "left",
    "axes.titlesize": 11, "axes.titleweight": "bold", "savefig.dpi": 200, "savefig.bbox": "tight",
})


def load_runs(ids: list[int] | None) -> list[dict]:
    from sqlmodel import select

    from content_agent import db

    with db.session() as s:
        rows = [db.to_dict(r) for r in s.exec(select(db.BenchmarkRun).order_by(db.BenchmarkRun.id))]
    if ids:  # chọn tay: dùng đúng các run đó, không gộp
        return [r for r in rows if r["id"] in ids]
    return [m for v in VARIANTS if (m := _merge([r for r in rows if r["name"] == v or r["name"].startswith(f"{v}-extra")], v))]


def _merge(rs: list[dict], variant: str) -> dict | None:
    """Gộp các run cùng variant (tên = variant hoặc <variant>-extra*); mỗi tên lấy run mới nhất, bỏ run thử (trial)."""
    latest = {}
    for r in rs:  # id tăng dần
        latest[r["name"]] = r
    rs = list(latest.values())
    if not rs:
        return None
    items = [i for r in rs for i in r["results"].get("items", [])]
    res = {"items": items, "failed": sum(r["results"].get("failed", 0) for r in rs)}
    if hr := next((r["results"]["human_rating"] for r in rs if "human_rating" in r["results"]), None):
        res["human_rating"] = hr
    return {"id": "+".join(str(r["id"]) for r in rs), "name": variant, "config": {**rs[-1]["config"], "n": len(items)},
            "created_at": rs[-1]["created_at"], "results": res}


def ok_items(run: dict) -> list[dict]:
    return [i for i in run["results"].get("items", []) if i["status"] == "done"]


def stats(items: list[dict]) -> dict:
    col = lambda k: [i[k] for i in items]  # noqa: E731
    sd = lambda xs: st.stdev(xs) if len(xs) > 1 else 0.0  # noqa: E731
    return {
        "n": len(items), "seo": st.mean(col("seo")), "seo_sd": sd(col("seo")),
        "pass": sum(i["seo"] >= PASS_SEO for i in items) / len(items),
        "read": st.mean(col("readability")), "read_sd": sd(col("readability")), "words": st.mean(col("words")),
        "minutes": st.mean(col("seconds")) / 60, "cost": st.mean(col("cost_usd")), "qa": st.mean(col("qa_rounds")),
    }


def variant_of(run: dict) -> str:
    return run["config"].get("variant", run["name"])


def matched(runs: list[dict]) -> list[dict]:
    """Ablation chỉ chạy một phần từ khoá: thu `full` về đúng tập từ khoá chung để so sánh công bằng."""
    others = [{i["topic"] for i in ok_items(r)} for r in runs if variant_of(r) != "full"]
    common = set.intersection(*others) if others else None
    if not common:
        return runs
    out = []
    for r in runs:
        if variant_of(r) == "full":
            r = {**r, "results": {**r["results"], "items": [i for i in r["results"]["items"] if i["topic"] in common]}}
        out.append(r)
    return out


def summary_md(runs: list[dict]) -> str:
    out = ["# Kết quả benchmark", ""]
    for r in runs:
        c = r["config"]
        out.append(f"- Run #{r['id']} `{variant_of(r)}`: {c.get('provider', '?')} / {c.get('model', '?')}, {str(r['created_at'])[:16]}")
    out += ["", "| Variant | n | Lỗi | SEO TB ± std | Tỉ lệ ≥ 80 | Dễ đọc TB | Số từ TB | Phút/bài | $/bài | Vòng QA TB | Human rating |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        items = ok_items(r)
        if not items:
            continue
        s, hr = stats(items), r["results"].get("human_rating")
        out.append(f"| {LABEL.get(variant_of(r), variant_of(r))} | {s['n']} | {r['results'].get('failed', 0)} "
                   f"| {s['seo']:.1f} ± {s['seo_sd']:.1f} | {s['pass']:.0%} | {s['read']:.1f} | {s['words']:.0f} "
                   f"| {s['minutes']:.1f} | {s['cost']:.4f} | {s['qa']:.1f} | {hr if hr is not None else '—'} |")
    m = matched(runs)
    if m is not runs:
        n_common = len(ok_items(next(r for r in m if variant_of(r) == "full")))
        out += ["", f"## So sánh ablation trên cùng {n_common} từ khoá",
                "", "Chỉ so `full` với các variant ablation trên đúng những từ khoá mà cả bốn cùng chạy.", "",
                "| Variant | n | SEO TB ± std | Tỉ lệ ≥ 80 | Dễ đọc TB | Phút/bài | $/bài | Vòng QA TB |", "|---|---|---|---|---|---|---|---|"]
        for r in m:
            if ok_items(r):
                s = stats(ok_items(r))
                out.append(f"| {LABEL.get(variant_of(r), variant_of(r))} | {s['n']} | {s['seo']:.1f} ± {s['seo_sd']:.1f} | {s['pass']:.0%} "
                           f"| {s['read']:.1f} | {s['minutes']:.1f} | {s['cost']:.4f} | {s['qa']:.1f} |")
    full = next((r for r in runs if variant_of(r) == "full"), None)
    if full:
        out += ["", "## Variant đầy đủ theo ngôn ngữ", "",
                "| Ngôn ngữ | n | SEO TB ± std | Tỉ lệ ≥ 80 | Dễ đọc TB | Phút/bài | $/bài |", "|---|---|---|---|---|---|---|"]
        for lang in ("vi", "en"):
            items = [i for i in ok_items(full) if i["language"] == lang]
            if items:
                s = stats(items)
                out.append(f"| {lang} | {s['n']} | {s['seo']:.1f} ± {s['seo_sd']:.1f} | {s['pass']:.0%} | {s['read']:.1f} "
                           f"| {s['minutes']:.1f} | {s['cost']:.4f} |")
    return "\n".join(out) + "\n"


def _bars(ax, names: list[str], values: list[float], colors: list[str], fmt: str, err: list[float] | None = None):
    bars = ax.bar(names, values, width=0.6, color=colors, edgecolor=SURF, linewidth=2,
                  yerr=err, capsize=4, error_kw={"ecolor": INK2, "elinewidth": 1})
    # nhãn số trực tiếp: vài màu dưới 3:1 trên nền sáng nên không để màu tự mang thông tin
    ax.bar_label(bars, labels=[fmt.format(v) for v in values], padding=3, color=INK, fontsize=9)
    ax.tick_params(axis="x", length=0)


def chart_seo(runs: list[dict], out: Path) -> None:
    rs = [r for r in runs if ok_items(r)]
    ss = [stats(ok_items(r)) for r in rs]
    fig, ax = plt.subplots(figsize=(7, 4))
    _bars(ax, [LABEL.get(variant_of(r), variant_of(r)) for r in rs], [s["seo"] for s in ss],
          [COLOR.get(variant_of(r), PALETTE[0]) for r in rs], "{:.1f}", [s["seo_sd"] for s in ss])
    ax.axhline(PASS_SEO, color=MUTED, linestyle="--", linewidth=1)
    ax.annotate(f"ngưỡng {PASS_SEO}", (1.01, PASS_SEO), xycoords=("axes fraction", "data"), va="center", color=INK2, fontsize=9)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Điểm SEO (0–100)")
    ax.set_title("Điểm SEO trung bình theo variant, cùng bộ từ khoá (± độ lệch chuẩn)")
    fig.savefig(out / "seo_by_variant.png")
    plt.close(fig)


def chart_cost(runs: list[dict], out: Path) -> None:
    rs = [r for r in runs if ok_items(r)]
    ss = [stats(ok_items(r)) for r in rs]
    names = [LABEL.get(variant_of(r), variant_of(r)) for r in rs]
    colors = [COLOR.get(variant_of(r), PALETTE[0]) for r in rs]
    # small multiples, mỗi panel một trục y riêng (không dùng dual-axis)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    for ax, key, title, fmt in zip(axes, ("minutes", "cost", "qa"), ("Phút / bài", "Chi phí $ / bài", "Số vòng QA TB"),
                                   ("{:.1f}", "${:.4f}", "{:.1f}")):
        _bars(ax, names, [s[key] for s in ss], colors, fmt)
        ax.set_title(title)
        ax.margins(y=0.15)
        ax.tick_params(axis="x", labelrotation=20)
    fig.suptitle("Ablation: thời gian, chi phí và số vòng sửa", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(out / "quality_vs_cost.png")
    plt.close(fig)


def chart_distribution(full: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    scores = [i["seo"] for i in ok_items(full)]
    ax.hist(scores, bins=range(0, 105, 5), color=PALETTE[0], edgecolor=SURF, linewidth=2)
    ax.axvline(PASS_SEO, color=MUTED, linestyle="--", linewidth=1)
    ax.text(PASS_SEO - 1, ax.get_ylim()[1] * 0.92, f"ngưỡng {PASS_SEO}", ha="right", color=INK2, fontsize=9)
    ax.set_xlim(min(50, 5 * int(min(scores) // 5)), 100)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.set_xlabel("Điểm SEO")
    ax.set_ylabel("Số bài")
    ax.set_title(f"Phân bố điểm SEO, variant đầy đủ (n = {len(ok_items(full))})")
    fig.savefig(out / "seo_distribution.png")
    plt.close(fig)


def chart_lang(full: dict, out: Path) -> None:
    metrics = [("seo", "SEO"), ("read", "Độ dễ đọc")]
    fig, ax = plt.subplots(figsize=(7, 4))
    w = 0.36
    for k, (lang, color) in enumerate((("vi", PALETTE[0]), ("en", PALETTE[1]))):
        items = [i for i in ok_items(full) if i["language"] == lang]
        if not items:
            continue
        s = stats(items)
        vals = [s[m] for m, _ in metrics]
        bars = ax.bar([x + (k - 0.5) * w for x in range(len(metrics))], vals, width=w, color=color, edgecolor=SURF,
                      linewidth=2, yerr=[s[m + "_sd"] for m, _ in metrics], capsize=4,
                      error_kw={"ecolor": INK2, "elinewidth": 1}, label=f"{lang} (n = {len(items)})")
        ax.bar_label(bars, labels=[f"{v:.1f}" for v in vals], padding=3, color=INK, fontsize=9)
    ax.set_xticks(range(len(metrics)), [label for _, label in metrics])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 125)
    ax.set_ylabel("Điểm (0–100)")
    ax.legend(frameon=False, loc="upper left", ncol=2)
    ax.set_title("Tiếng Việt và tiếng Anh, variant đầy đủ (± độ lệch chuẩn)")
    fig.savefig(out / "lang_compare.png")
    plt.close(fig)


def chart_agents(runs: list[dict], out: Path) -> bool:
    rs = [r for r in runs if any(i.get("steps") for i in ok_items(r))]  # run cũ chưa lưu steps thì bỏ qua
    if not rs:
        return False
    fig, ax = plt.subplots(figsize=(8, 0.9 * len(rs) + 1.8))
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    names = [LABEL.get(variant_of(r), variant_of(r)) for r in rs]
    for y, r in enumerate(rs):
        items = [i for i in ok_items(r) if i.get("steps")]
        left = 0.0
        for a in AGENTS:
            # cộng mọi bước cùng agent trong 1 bài (vòng QA chạy Editor nhiều lần), rồi lấy TB theo bài
            m = st.mean(sum(x["seconds"] for x in i["steps"] if x["agent"] == a) for i in items) / 60
            if m:
                ax.barh(y, m, left=left, height=0.55, color=AGENT_COLOR[a], edgecolor=SURF, linewidth=2,
                        label=a if y == 0 or a not in ax.get_legend_handles_labels()[1] else None)
                left += m
        wall = st.mean(i["seconds"] for i in items) / 60
        ax.plot([wall, wall], [y - 0.38, y + 0.38], color=INK, linewidth=2)
        ax.text(max(left, wall) + 0.1, y, f"tổng bước {left:.1f}′ · thực tế {wall:.1f}′", va="center", color=INK2, fontsize=9)
    ax.set_yticks(range(len(rs)), names)
    ax.invert_yaxis()
    ax.tick_params(axis="y", length=0, labelcolor=INK2)
    ax.margins(x=0.35)
    ax.set_xlabel("Phút / bài (vạch đen = thời gian thực tế của cả job)")
    ax.legend(frameon=False, ncol=len(AGENTS), loc="upper center", bbox_to_anchor=(0.5, -0.16), fontsize=8)
    ax.set_title("Thời gian theo agent so với thời gian thực tế của job")
    fig.savefig(out / "agent_breakdown.png")
    plt.close(fig)
    return True


def build(runs: list[dict], out: Path) -> list[str]:
    out = out / "img"
    out.mkdir(parents=True, exist_ok=True)
    files = []
    if any(ok_items(r) for r in runs):
        chart_seo(matched(runs), out)  # chart ablation dùng cùng tập từ khoá
        chart_cost(matched(runs), out)
        files += ["seo_by_variant.png", "quality_vs_cost.png"]
    full = next((r for r in runs if variant_of(r) == "full" and ok_items(r)), None)
    if full:
        chart_distribution(full, out)
        chart_lang(full, out)
        files += ["seo_distribution.png", "lang_compare.png"]
    if chart_agents(matched(runs), out):
        files.append("agent_breakdown.png")
    return files


def _self_check() -> None:
    def item(lang, seo, steps=True):
        st_ = [{"agent": a, "seconds": 30.0, "cost_usd": 0.001, "tokens": 100} for a in AGENTS] if steps else None
        return {"topic": "t", "language": lang, "status": "done", "seo": seo, "readability": 70.0, "words": 1300,
                "seconds": 150.0, "cost_usd": 0.01, "qa_rounds": 1, **({"steps": st_} if st_ else {})}

    runs = [
        {"id": 1, "name": "full", "config": {"variant": "full", "model": "m", "provider": "p"}, "created_at": "2026-11-01",
         "results": {"failed": 1, "items": [item("vi", 90), item("en", 70), {**item("vi", 0), "status": "failed"}]}},
        {"id": 2, "name": "sequential", "config": {"variant": "sequential"}, "created_at": "2026-11-01",
         "results": {"failed": 0, "items": [item("vi", 85, steps=False)]}},
    ]
    rows = [{**runs[0], "id": 1}, {**runs[0], "id": 2, "name": "trial"},
            {**runs[0], "id": 3, "name": "full-extra", "results": {"failed": 0, "items": [item("vi", 100)]}},
            {**runs[0], "id": 4, "name": "full-extra2", "results": {"failed": 0, "items": [item("en", 60)]}}]
    m = _merge([r for r in rows if r["name"] == "full" or r["name"].startswith("full-extra")], "full")
    assert m["id"] == "1+3+4" and len(m["results"]["items"]) == 5 and m["results"]["failed"] == 1, m
    s = stats(ok_items(runs[0]))
    assert s["n"] == 2 and s["seo"] == 80 and s["pass"] == 0.5 and s["minutes"] == 2.5, s
    md = summary_md(runs)
    assert "| Đầy đủ | 2 | 1 | 80.0 ± 14.1 | 50% |" in md and "| vi | 1 | 90.0 ± 0.0 | 100% |" in md, md
    with tempfile.TemporaryDirectory() as d:
        files = build(runs, Path(d))  # PNG nằm trong <d>/img
        assert len(files) == 5, files
        assert all((Path(d) / "img" / f).stat().st_size > 0 for f in files)
    print("self-check OK")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ids", help="danh sách id BenchmarkRun, cách nhau bằng dấu phẩy")
    p.add_argument("--self-check", action="store_true")
    a = p.parse_args()
    if a.self_check:
        _self_check()
    else:
        runs = load_runs([int(x) for x in a.ids.split(",")] if a.ids else None)
        if not runs:
            raise SystemExit("chưa có BenchmarkRun nào; chạy eval/benchmark.py trước")
        print(summary_md(runs))  # bảng markdown: dán vào docs/report/README.md
        print("đã ghi:", ", ".join(build(runs, OUT)), "->", OUT / "img")
