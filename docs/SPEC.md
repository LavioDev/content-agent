# SPEC — AI Content Agent (MCP Server + Web Dashboard)

> Đặc tả kỹ thuật cho đề tài 34. Kế hoạch & lịch: xem [PLAN.md](PLAN.md). Giá LLM: xem [LLM_PRICING.md](LLM_PRICING.md).
> Phiên bản: 0.1 — 29/10/2026

## 1. Mục tiêu

Xây dựng một **MCP server** cung cấp đầy đủ chức năng của pipeline sản xuất nội dung đa agent (research → blog → edit → social → SEO → image prompts → QA → duyệt → lên lịch), kèm **web dashboard** (Nuxt + Vue + shadcn-vue) để biểu diễn, theo dõi và duyệt nội dung.

Cùng một lõi xử lý được dùng qua hai cửa:

- **MCP** — để Claude Desktop, Claude Code, Cursor… gọi pipeline như một bộ tool.
- **REST + SSE** — để dashboard hiển thị tiến độ realtime và workflow duyệt.

### Tiêu chí thành công

| Chỉ số | Mục tiêu |
|---|---|
| Blog quality (5 raters) | ≥ 4/5 |
| SEO score | ≥ 80/100 |
| Thời gian / bài | < 10 phút (mục tiêu demo ~5 phút) |
| Chi phí / bài | Đo và hiển thị trên dashboard |
| MCP | Tất cả tool chạy được trong MCP Inspector và Claude Desktop |
| Dashboard | Chạy hết luồng demo (mục 9) không lỗi |

## 2. Phạm vi

### Trong phạm vi

- Pipeline 6 agent bằng CrewAI (Researcher, Writer, Editor, Social Adapter, SEO Optimizer, QA Checker)
- MCP server: tools, resources, prompts (mục 5)
- Backend REST API + SSE stream tiến độ
- Dashboard: tạo nội dung, theo dõi pipeline, xem/sửa kết quả, duyệt, lịch nội dung, trang benchmark
- Chấm điểm SEO và readability (VN + EN)
- Log token, chi phí, thời gian theo từng agent
- Bộ script đánh giá (benchmark, ablation, engagement proxy)
- Hỗ trợ input tiếng Việt và tiếng Anh

### Ngoài phạm vi

- Đăng bài thật lên Facebook / Threads / LinkedIn (chỉ copy / export)
- Sinh ảnh thật (chỉ sinh image prompt)
- Đăng nhập nhiều người dùng, phân quyền (một user, chạy local)
- Deploy production, scale nhiều worker
- Fine-tune model

## 3. Công nghệ

### Backend (Python 3.12)

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Quản lý package | `venv` + `pip` (`pyproject.toml`) | Máy dev chưa có `uv`; đổi sang `uv` được mà không sửa code |
| Agent orchestration | CrewAI | Yêu cầu đề bài; hỗ trợ sequential + `async_execution` |
| LLM | OpenRouter `qwen/qwen3-14b` @ DeepInfra (cấu hình qua `.env`) | Đã test kết nối; đổi model bằng `.env` |
| MCP | MCP Python SDK chính thức (`mcp`, FastMCP) | Transport `stdio` + `streamable-http` |
| REST API | FastAPI | Cùng process với MCP HTTP, có SSE |
| DB | SQLite + SQLModel | Đủ cho một user, không cần server DB |
| Search | Serper.dev hoặc SerpAPI (+ cache SQLite) | Research web, đối thủ SERP |
| Lấy nội dung trang | `httpx` + `trafilatura` | Trích text sạch từ URL |
| Readability | `textstat` (EN) + scorer tự viết (VN) | Flesch-Kincaid không hợp tiếng Việt |
| SEO scoring | Module tự viết theo checklist mục 7 | Yoast không có API |
| Test | `pytest` | |

### Frontend

| Thành phần | Lựa chọn |
|---|---|
| Framework | Nuxt 4 (Vue 3, `<script setup>`, TypeScript) |
| UI kit | shadcn-vue (Reka UI) + Tailwind CSS v4 |
| Icon | `lucide-vue-next` |
| Biểu đồ | shadcn-vue Charts |
| Markdown | `@nuxtjs/mdc` (render blog) |
| Toast | `vue-sonner` (component Sonner của shadcn-vue) |
| Dark mode | `@nuxtjs/color-mode` |
| Gọi API | `$fetch` / `useFetch` có sẵn của Nuxt, `EventSource` cho SSE |
| Kéo-thả lịch | HTML5 drag & drop thuần (không thêm thư viện) |

Frontend gọi backend qua proxy của Nuxt (`routeRules` → `http://localhost:8000`), **không bao giờ nhận API key LLM**.

## 4. Kiến trúc

```
┌──────────────────────┐        ┌──────────────────────────────────────────────┐
│ Claude Desktop /     │ stdio  │                 backend (Python)              │
│ Claude Code / Cursor ├───────►│  ┌────────────┐   ┌──────────────────────┐   │
└──────────────────────┘  or    │  │ MCP server │──►│                      │   │
                     streamable │  └────────────┘   │   core services      │   │
                        HTTP    │  ┌────────────┐   │  - pipeline (CrewAI) │──►│── OpenRouter (Qwen)
┌──────────────────────┐ REST + │  │ FastAPI    │──►│  - scorers           │──►│── Serper / SerpAPI
│ Nuxt dashboard       ├───────►│  │ REST + SSE │   │  - content / review  │   │
│ (shadcn-vue)         │  SSE   │  └────────────┘   │  - job runner        │   │
└──────────────────────┘        │                   └──────────┬───────────┘   │
                                │                              ▼               │
                                │                        SQLite (data.db)      │
                                └──────────────────────────────────────────────┘
```

- **Core services** là nơi duy nhất chứa logic. MCP tools và REST endpoints chỉ là lớp mỏng gọi vào core.
- **Job runner**: pipeline chạy nền (asyncio task trong process). Mỗi agent bắt đầu / kết thúc → ghi `run_step` vào DB và phát event lên SSE.
- **Human approval gate**: pipeline dừng ở trạng thái `pending_review`; chỉ người (qua dashboard hoặc tool `review_content` có xác nhận của MCP client) mới chuyển sang `approved`.

### Luồng pipeline

```
Researcher → Writer → Editor → ┬─ Social Adapter ─┬→ QA Checker ─pass→ pending_review
                               └─ SEO Optimizer ──┘      │
                                                         └─fail (≤2 vòng)→ Editor
```

### Trạng thái nội dung

```
queued → running → pending_review → approved → scheduled → published (đánh dấu tay)
                 ↘ failed          ↘ changes_requested → running
                                   ↘ rejected
```

## 5. MCP server

Tên server: `ai-content-agent`. Chạy: `uv run content-mcp` (stdio) hoặc `uv run content-mcp --http` (streamable HTTP, cổng 8787, path `/mcp`).

### 5.1 Tools

| Tool | Input | Output | Ghi chú |
|---|---|---|---|
| `create_content` | `topic`, `audience`, `tone`, `language` (`vi`/`en`), `platforms[]`, `word_count=1500` | `{job_id, status}` | Chạy cả pipeline nền, trả về ngay |
| `get_job` | `job_id` | trạng thái, step hiện tại, % tiến độ, thời gian, chi phí | Để client poll |
| `get_content` | `content_id`, `part?` (`blog`/`social`/`seo`/`images`/`qa`) | nội dung tương ứng | |
| `list_contents` | `status?`, `from?`, `to?`, `limit=20` | danh sách tóm tắt | |
| `research_topic` | `topic`, `language`, `num_sources=5` | outline, nguồn, keyword phụ | Chạy riêng agent Researcher |
| `write_blog` | `topic`, `outline[]`, `audience`, `tone`, `language`, `focus_keyword?`, `word_count` | blog Markdown | Chạy riêng Writer (không có nguồn để trích dẫn) |
| `adapt_social` | `content_id` hoặc `blog_markdown`, `platforms[]` | bài cho từng nền tảng | |
| `optimize_seo` | `content_id` hoặc `blog_markdown`, `focus_keyword` | meta, slug, blog đã tối ưu, điểm | |
| `generate_image_prompts` | `content_id`, `count=4` | prompt + alt text | |
| `score_seo` | `markdown`, `focus_keyword`, `meta?` | điểm 0–100 + chi tiết từng tiêu chí | Không gọi LLM |
| `score_readability` | `text`, `language` | điểm + chỉ số chi tiết | Không gọi LLM |
| `revise_content` | `content_id`, `instructions` | `{job_id}` | Chạy lại Editor → QA theo ghi chú |
| `review_content` | `content_id`, `decision` (`approve`/`request_changes`/`reject`), `note?` | trạng thái mới | Tool có tác động — đánh dấu `destructiveHint` để client hỏi xác nhận |
| `schedule_content` | `content_id`, `platform`, `datetime` | mục lịch | Chỉ cho nội dung `approved` |
| `get_calendar` | `from`, `to` | danh sách mục lịch | |
| `get_metrics` | `from?`, `to?` | SEO TB, readability TB, thời gian TB, chi phí TB, số bài theo trạng thái | |

### 5.2 Resources

| URI | Nội dung |
|---|---|
| `content://{id}/blog` | Blog Markdown |
| `content://{id}/social/{platform}` | Bài social |
| `content://{id}/report` | Báo cáo QA + SEO + readability (JSON) |
| `styleguide://{platform}` | Style guide của nền tảng (`threads`, `facebook`, `linkedin`, `blog`) |
| `calendar://{yyyy-mm}` | Lịch nội dung theo tháng |

### 5.3 Prompts

| Prompt | Tham số | Mục đích |
|---|---|---|
| `content_campaign` | `topic`, `audience`, `platforms` | Hướng dẫn client chạy cả chiến dịch: create → chờ → review |
| `review_checklist` | `content_id` | Checklist cho người duyệt |

### 5.4 Yêu cầu

- Mọi tool có JSON schema rõ ràng (Pydantic), mô tả bằng tiếng Anh để client LLM hiểu tốt; nội dung trả về theo `language` của input.
- Lỗi trả về dạng tool error có thông điệp dễ hiểu (vd: `content not approved`), không trả stack trace.
- `create_content` không chặn quá vài giây; tiến độ qua `get_job` (và MCP progress notification nếu client hỗ trợ).
- Chế độ HTTP yêu cầu header `Authorization: Bearer <MCP_TOKEN>` từ `.env`.

## 6. REST API (cho dashboard)

Base: `/api`

| Method | Path | Mô tả |
|---|---|---|
| POST | `/jobs` | Tạo job (body giống `create_content`) |
| GET | `/jobs/{id}` | Trạng thái job + các step |
| GET | `/jobs/{id}/events` | **SSE**: event `snapshot` (toàn bộ job + các step) mỗi khi có thay đổi, event `end` khi job xong/lỗi. Đọc từ DB nên chạy được cả khi job do process MCP khác khởi tạo |
| GET | `/contents` | Danh sách, lọc `status`, `q`, `from`, `to` |
| GET | `/contents/{id}` | Chi tiết đầy đủ (blog, social, seo, images, qa, versions) |
| PATCH | `/contents/{id}` | Sửa tay blog / social / meta (tạo version mới, chấm lại điểm) |
| POST | `/contents/{id}/review` | `approve` / `request_changes` / `reject` + ghi chú |
| POST | `/contents/{id}/schedule` | Lên lịch theo nền tảng |
| DELETE | `/schedule/{entry_id}` | Bỏ lịch |
| GET | `/calendar?from&to` | Mục lịch |
| GET | `/metrics` | Số liệu tổng hợp cho dashboard |
| GET | `/benchmarks` | Kết quả các lần chạy đánh giá |
| GET | `/settings` | Model, provider, giới hạn (không trả key) |

## 7. Chấm điểm

### 7.1 SEO (100 điểm)

| Tiêu chí | Điểm |
|---|---|
| Focus keyword trong H1 | 10 |
| Keyword trong 100 từ đầu | 10 |
| Keyword trong ≥ 1 H2 | 10 |
| Mật độ keyword 0.5–2.5% | 10 |
| Meta description 120–160 ký tự, có keyword | 10 |
| Meta title ≤ 60 ký tự | 5 |
| Slug ngắn, có keyword, không dấu | 5 |
| ≥ 1200 từ | 10 |
| ≥ 3 heading H2 | 10 |
| Có link nguồn ngoài | 10 |
| Image prompt có alt text | 5 |
| Readability đạt ngưỡng | 5 |

Keyword tiếng Việt so khớp cả bản có dấu và không dấu, không phân biệt hoa thường.

### 7.2 Readability

- **EN**: Flesch Reading Ease (`textstat`), đạt khi ≥ 60.
- **VN**: điểm 0–100 tự định nghĩa, đếm theo **âm tiết** (tách theo khoảng trắng, ~1.4 âm tiết/từ): câu trung bình ≤ 22 âm tiết, đoạn ≤ 4 câu, tỉ lệ câu > 40 âm tiết. Ngưỡng chọn theo kinh nghiệm, cần hiệu chỉnh lại với human rating. Lịch sử thay đổi: [progress/issues.md](progress/issues.md).

## 8. Mô hình dữ liệu

```
Job          id, input(json), status, current_step, started_at, finished_at, error
RunStep      id, job_id, agent, status, started_at, finished_at, prompt_tokens, completion_tokens, cost_usd, output(json)
Content      id, job_id, topic, language, status, focus_keyword, meta_title, meta_description, slug,
             blog_md, social(json: {threads, facebook, linkedin}), image_prompts(json),
             sources(json), seo_score, seo_detail(json), readability_score, qa_report(json),
             version, created_at, updated_at
ContentVersion id, content_id, version, snapshot(json), created_by(agent|human), created_at
Review       id, content_id, decision, note, created_at
ScheduleEntry id, content_id, platform, scheduled_at, status(scheduled|published)
SearchCache  query, language, result(json), created_at
BenchmarkRun id, name, config(json), results(json), created_at
```

## 9. Dashboard (Nuxt + shadcn-vue)

### 9.1 Trang

| Route | Nội dung | Component shadcn-vue chính |
|---|---|---|
| `/` | Tổng quan: thẻ KPI (số bài, SEO TB, thời gian TB, chi phí TB), biểu đồ theo ngày, bài chờ duyệt | Card, Chart, Badge, Table |
| `/new` | Form tạo nội dung: topic, audience, tone, ngôn ngữ, nền tảng | Form, Input, Select, Textarea, Checkbox, Button |
| `/jobs/[id]` | Pipeline trực tiếp: timeline 6 agent, trạng thái từng bước, thời gian, token, chi phí, log ngắn; tự chuyển sang trang nội dung khi xong | Stepper, Progress, Card, Collapsible |
| `/contents` | Danh sách nội dung, lọc theo trạng thái, tìm kiếm | Table, Tabs, Input, Badge |
| `/contents/[id]` | Tab: Blog (preview / sửa), Threads, Facebook, LinkedIn (mô phỏng giao diện post), SEO (điểm + checklist), Images (prompt + nút copy), QA, Lịch sử version. Thanh duyệt: Approve / Request changes / Reject | Tabs, Card, Textarea, Dialog, Alert, Button, Sonner |
| `/calendar` | Lịch tháng/tuần, kéo bài đã duyệt vào ngày, màu theo nền tảng | Calendar, Popover, Badge |
| `/benchmark` | Bảng + biểu đồ kết quả đánh giá, ablation, chi phí | Table, Chart |
| `/settings` | Model, provider, MCP endpoint + hướng dẫn kết nối Claude Desktop | Card, Input, Button |

### 9.2 Yêu cầu giao diện

- Giao diện tiếng Việt; dark/light mode.
- Responsive tới 375px (mobile xem được, thao tác chính dùng desktop).
- Trạng thái loading (Skeleton), trạng thái rỗng, thông báo lỗi rõ ràng cho mọi trang.
- Bàn phím dùng được cho các thao tác chính; component shadcn-vue giữ nguyên thuộc tính a11y.
- Preview social mô phỏng gần giống bài đăng thật (avatar, tên, giới hạn ký tự, cảnh báo khi vượt).

### 9.3 Luồng demo (~5 phút)

1. `/new` → nhập "chuyển đổi số cho doanh nghiệp nhỏ", audience "chủ shop online", tone "thân thiện" → Generate
2. `/jobs/[id]` → xem 6 agent chạy realtime, Social và SEO chạy song song
3. `/contents/[id]` → xem blog, 3 bài social, SEO 85/100 → Request changes "thêm ví dụ thực tế" → Approve
4. `/calendar` → kéo bài vào thứ 3 tuần sau cho Facebook và LinkedIn
5. Claude Desktop → hỏi "liệt kê các bài đang chờ duyệt" → MCP trả về danh sách giống dashboard

## 10. Yêu cầu phi chức năng

| Mục | Yêu cầu |
|---|---|
| Hiệu năng | < 10 phút/bài; SEO Optimizer và Social Adapter chạy song song |
| Chi phí | Ghi `usage.cost` của OpenRouter cho từng bước |
| Bảo mật | Key chỉ ở `.env` backend; `.env` trong `.gitignore`; MCP HTTP cần token; dashboard chỉ bind `localhost` |
| Tin cậy | Lỗi LLM/API: retry 2 lần (backoff); job lỗi lưu `error` và vẫn xem được các bước đã xong |
| Tái lập | Cố định model + provider (`allow_fallbacks: false`) khi benchmark; lưu config vào `BenchmarkRun` |
| Dữ liệu | Không xoá version cũ khi sửa; xoá content cần xác nhận |

## 11. Cấu trúc thư mục

```
ai-content-agent/
├── backend/
│   ├── pyproject.toml
│   ├── src/content_agent/
│   │   ├── agents/          # định nghĩa 6 agent
│   │   ├── tasks/           # task CrewAI
│   │   ├── tools/           # serp_search, fetch_page
│   │   ├── scoring/         # seo.py, readability.py
│   │   ├── services/        # pipeline, contents, reviews, calendar, metrics
│   │   ├── db.py            # SQLModel models + session
│   │   ├── mcp_server.py    # FastMCP: tools / resources / prompts
│   │   └── api.py           # FastAPI + SSE, mount MCP HTTP
│   ├── prompts/style_guides/
│   └── tests/
├── frontend/                # Nuxt 4 + shadcn-vue
│   ├── app/pages/
│   ├── app/components/      # ui/ (shadcn-vue), pipeline/, content/, calendar/
│   └── nuxt.config.ts
├── eval/                    # keyword test set, script benchmark, kết quả rating
├── scripts/                 # check_llm.py, …
├── docs/
├── .env.example
└── .gitignore
```

## 12. Kiểm thử & nghiệm thu

| Mức | Nội dung |
|---|---|
| Unit | `scoring/` (SEO, readability VN/EN) có test với mẫu cố định; schema input của tool |
| Tích hợp | Chạy pipeline với LLM giả (mock) để test luồng trạng thái, vòng QA, SSE event |
| MCP | Gọi từng tool bằng MCP Inspector; kết nối Claude Desktop qua stdio |
| E2E thủ công | Chạy luồng demo mục 9.3 trước mỗi buổi báo cáo |
| Đánh giá | Benchmark theo [PLAN.md](PLAN.md) mục 6, kết quả hiển thị ở `/benchmark` |

### Checklist nghiệm thu

- [ ] 16 MCP tool, 5 resource, 2 prompt hoạt động trong MCP Inspector
- [ ] Claude Desktop tạo được nội dung và đọc lại được qua MCP
- [ ] Dashboard: tạo → theo dõi realtime → duyệt → lên lịch, không lỗi
- [ ] SEO TB ≥ 80, thời gian TB < 10 phút trên bộ test
- [ ] Human rating TB ≥ 4/5 (5 raters)
- [ ] Chi phí / bài hiển thị trên dashboard và trong báo cáo

## 13. Lộ trình gắn với PLAN

| Tuần | Phần của SPEC |
|---|---|
| 2 | Researcher + Writer, `research_topic`, `write_blog` |
| 3 | `scoring/`, Editor, `score_seo`, `score_readability` + unit test |
| 4 | Social, SEO, QA, job runner, `create_content`, `get_job` |
| 5 | DB, MCP đầy đủ (tools / resources / prompts), REST + SSE |
| 6 | Dashboard: `/new`, `/jobs/[id]`, `/contents/[id]`, `/calendar`, `/` |
| 7 | `/benchmark`, chạy đánh giá |
| 8 | Hoàn thiện UI, demo, báo cáo |

## 14. Khác biệt so với bản đầu và trạng thái triển khai

| Mục | Thực tế |
|---|---|
| Cổng backend | 8787 (cổng 8000 bị WSL `wslrelay` chiếm trên máy dev) |
| Search | Serper nếu có `SERPER_API_KEY`, không thì DuckDuckGo (`ddgs`), có cache 24h |
| Image Prompts | Tách thành một agent riêng chạy song song với Social và SEO (7 bước thay vì 6) |
| QA Checker | Pass/fail do luật cứng (SEO ≥ 80, dễ đọc ≥ 60, giới hạn ký tự social); LLM chỉ viết nhận xét định tính |
| Chi phí | Tính từ token CrewAI báo × giá trong `.env`, là ước lượng (CrewAI không trả `usage.cost` của OpenRouter) |
| Ablation | `variant` của job: `full`, `no_editor`, `no_qa_loop`, `sequential` (chỉ dùng qua `eval/benchmark.py`) |
| Chưa làm | Human rating 5 người, engagement proxy (LLM-as-judge), chạy benchmark đủ 20 từ khoá |

## 15. Câu hỏi mở

- Giữ 6 agent hay gộp còn 5 theo đề bài?
- Giảng viên có chấp nhận Qwen3-14B thay cho Qwen2.5-14B không?
- Chọn Serper.dev hay SerpAPI (so free tier khi đăng ký)?
- Có cần MCP client chạy trên máy khác (dùng HTTP) hay chỉ stdio local?
