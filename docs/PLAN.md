# Đề tài 34 — Collaborative Multi-Agent Content Pipeline

> Tự động sản xuất nội dung đa định dạng (Blog + Social) bằng nhiều agent hợp tác, có human review tại checkpoint.

## 1. Mục tiêu

Pipeline content marketing tự động:

```
topic keyword → nghiên cứu → viết blog dài → biên tập → rút gọn cho social → SEO optimize → image prompts → QA → human approve → publish
```

### Yêu cầu kỹ thuật (KPI nghiệm thu)

| Chỉ số | Mục tiêu | Cách đo |
|---|---|---|
| Chất lượng blog | ≥ 4/5 | Human rating, 5 raters, thang Likert 1–5 |
| SEO score | ≥ 80/100 | Bộ chấm điểm theo rule kiểu Yoast (tự cài đặt) |
| Thời gian sản xuất | < 10 phút/bài (demo mục tiêu ~5 phút) | Log thời gian từng task |
| Chi phí | Báo cáo $/bài | Đếm token + số lần gọi SERP API |

## 2. Input / Output

**Input**
- `topic`: từ khoá chủ đề (tiếng Việt hoặc tiếng Anh)
- `audience`: đối tượng mục tiêu (vd: sinh viên IT, chủ shop online)
- `tone`: giọng văn (chuyên nghiệp, thân thiện, hài hước…)
- `platforms`: danh sách nền tảng social (Threads, Facebook, LinkedIn)

**Output** (lưu dạng JSON + Markdown)
- Blog ~1500 từ (Markdown) + meta title, meta description, slug, focus keyword
- 3 bài social (Threads / Facebook / LinkedIn)
- 3–5 image prompts (ảnh bìa + ảnh minh hoạ)
- Báo cáo QA: SEO score, readability score, danh sách lỗi
- Trạng thái duyệt: `draft → pending_review → approved / rejected → scheduled`

## 3. Kiến trúc

### 3.1 Các agent (CrewAI)

| # | Agent | Nhiệm vụ | Tools |
|---|---|---|---|
| 1 | **Researcher** | Tìm kiếm web, tổng hợp nguồn, lập outline, đề xuất keyword phụ | SERP API, web scraper |
| 2 | **Writer** | Viết blog ~1500 từ theo outline + style guide | LLM (Qwen2.5-14B) |
| 3 | **Editor** | Sửa ngữ pháp, mạch văn, giọng văn, độ dễ đọc | Readability scorer |
| 4 | **Social Adapter** | Chuyển blog thành bài Threads / Facebook / LinkedIn | Style guide từng nền tảng |
| 5 | **SEO Optimizer** | Tối ưu keyword density, heading, meta, internal link, image prompts | SEO scorer |
| 6 | **QA Checker** | Kiểm tra cuối: độ dài, fact có nguồn, SEO ≥ 80, readability đạt; trả về pass/fail + lý do | SEO scorer, readability scorer |

> Đề bài ghi "5 agents" nhưng liệt kê 6 vai trò. Phương án: giữ 6 agent; nếu cần đúng 5 thì gộp QA Checker vào SEO Optimizer.

### 3.2 Luồng xử lý (sequential + parallel)

```
                 ┌──────────────┐
 Input  ───────► │  Researcher  │
                 └──────┬───────┘
                        ▼
                 ┌──────────────┐
                 │    Writer    │
                 └──────┬───────┘
                        ▼
                 ┌──────────────┐
                 │    Editor    │
                 └──────┬───────┘
              ┌─────────┴──────────┐   (chạy song song — async_execution)
              ▼                    ▼
     ┌────────────────┐   ┌────────────────┐
     │ Social Adapter │   │ SEO Optimizer  │
     └───────┬────────┘   └───────┬────────┘
              └─────────┬──────────┘
                        ▼
                 ┌──────────────┐   fail (tối đa 2 vòng) → quay lại Editor
                 │  QA Checker  │ ─────────────────────────────┐
                 └──────┬───────┘                              │
                        ▼ pass                                 │
              ┌───────────────────┐                            │
              │ HUMAN APPROVAL    │ ◄──────────────────────────┘
              │ (dashboard)       │
              └─────────┬─────────┘
                        ▼
                 Content calendar / Publish
```

- Social Adapter và SEO Optimizer độc lập nhau → chạy song song để giảm thời gian.
- Human checkpoint: (1) sau outline của Researcher (tuỳ chọn), (2) bắt buộc trước publish.

### 3.3 Công nghệ

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Orchestration | CrewAI (Process.sequential + `async_execution=True`) | |
| LLM | Qwen2.5-14B-Instruct qua Ollama / vLLM | Bản 4-bit cần ~10 GB VRAM. Fallback: API (Qwen qua OpenRouter/DashScope) nếu không đủ GPU |
| Search | SerpAPI hoặc Serper.dev | Có free tier; cache kết quả để tiết kiệm |
| Readability | `textstat` (Flesch-Kincaid cho EN) | Tiếng Việt: dùng chỉ số tự định nghĩa (độ dài câu TB, độ dài đoạn, tỉ lệ từ dài) |
| SEO scoring | Module tự viết theo checklist Yoast | Yoast không có API công khai |
| Backend | FastAPI + SQLite + MCP server (FastMCP) | Chi tiết: [SPEC.md](SPEC.md) |
| Dashboard | Nuxt 4 + Vue + shadcn-vue | Form nhập keyword, xem tiến độ, duyệt, calendar view |

## 4. Prompting

- **Style guide theo nền tảng** (`prompts/style_guides/*.md`):
  - Threads: ≤ 500 ký tự, hook câu đầu, 1–3 hashtag, giọng gần gũi
  - Facebook: 100–250 từ, có emoji vừa phải, CTA, câu hỏi tương tác
  - LinkedIn: 150–300 từ, chuyên nghiệp, có insight/số liệu, xuống dòng nhiều
- **SEO tiếng Việt**: focus keyword có dấu + không dấu, keyword trong H1/H2 đầu/meta/100 từ đầu, mật độ 0.5–2.5%.
- **Readability target**: EN Flesch Reading Ease ≥ 60; VN câu TB ≤ 20 từ, đoạn ≤ 4 câu.
- Mỗi agent có `role`, `goal`, `backstory` rõ ràng; output ép về JSON schema (Pydantic) để agent sau parse được.

## 5. SEO scoring (thang 100)

| Tiêu chí | Điểm |
|---|---|
| Focus keyword trong title (H1) | 10 |
| Keyword trong 100 từ đầu | 10 |
| Keyword trong ≥ 1 H2 | 10 |
| Mật độ keyword 0.5–2.5% | 10 |
| Meta description 120–160 ký tự, chứa keyword | 10 |
| Meta title ≤ 60 ký tự | 5 |
| Slug ngắn, chứa keyword | 5 |
| Độ dài ≥ 1200 từ | 10 |
| Có ≥ 3 heading H2 | 10 |
| Có link ngoài (nguồn) / link nội bộ | 10 |
| Ảnh có alt text (từ image prompts) | 5 |
| Readability đạt ngưỡng | 5 |

## 6. Đánh giá

1. **Human rating**: 5 raters × ≥ 10 bài, tiêu chí: chính xác, mạch lạc, hữu ích, giọng văn, sẵn sàng publish. Báo cáo mean ± std, Krippendorff's alpha.
2. **SEO score**: trung bình trên toàn bộ bài test; tỉ lệ bài ≥ 80.
3. **Engagement proxy (simulated)**: LLM-as-judge đóng vai người dùng mạng xã hội, chấm khả năng like/share/comment (1–5) cho từng bài social.
4. **Chi phí & thời gian**: token in/out, số SERP call, thời gian từng agent → $/bài, phút/bài.
5. **Ablation** (điểm cộng): bỏ Editor / bỏ QA loop / chạy tuần tự thay vì song song → so sánh chất lượng & thời gian.

Bộ test: 10–20 keyword (một nửa tiếng Việt, một nửa tiếng Anh), đa lĩnh vực.

## 7. Demo

Web dashboard:
1. Nhập keyword + audience + tone + platform → bấm **Generate**
2. Thanh tiến độ theo từng agent (≈ 5 phút)
3. Xem kết quả: blog, social posts, image prompts, SEO/readability score
4. **Approval workflow**: Approve / Request changes (ghi chú → chạy lại Editor) / Reject
5. **Content calendar view**: kéo bài đã duyệt vào lịch đăng

## 8. Cấu trúc thư mục dự kiến

> Đã được thay bằng bản chi tiết trong [SPEC.md](SPEC.md) mục 11 (tách `backend/` + `frontend/`).

```
ai-content-agent/
├── docs/
│   ├── PLAN.md
│   └── progress/
├── src/
│   ├── agents/          # định nghĩa agent
│   ├── tasks/           # định nghĩa task
│   ├── tools/           # serp_search, seo_scorer, readability
│   ├── crew.py          # lắp pipeline
│   └── api/             # FastAPI
├── prompts/style_guides/
├── dashboard/           # Streamlit / React
├── eval/                # script đánh giá, bộ keyword test, kết quả rating
├── tests/
└── .env.example
```

## 9. Kế hoạch thực hiện (8 tuần)

| Tuần | Mốc | Kết quả bàn giao |
|---|---|---|
| 1 | Setup & nghiên cứu | Môi trường, chạy được Qwen2.5-14B, đọc CrewAI / GPT Researcher / GPT Author, chốt kiến trúc |
| 2 | Researcher + Writer | Từ keyword ra outline + blog nháp |
| 3 | Editor + tools | Readability scorer (EN + VN), SEO scorer + unit test |
| 4 | Social Adapter + SEO Optimizer + QA | Pipeline đầy đủ chạy CLI, có song song + vòng QA |
| 5 | Backend + lưu trữ | FastAPI, SQLite, trạng thái duyệt, log thời gian/chi phí |
| 6 | Dashboard | Form nhập, tiến độ, approval workflow, calendar view |
| 7 | Đánh giá | Chạy bộ test, thu thập human rating, engagement proxy, ablation |
| 8 | Hoàn thiện | Tối ưu tốc độ, báo cáo, slide, video demo |

## 10. Rủi ro & phương án

| Rủi ro | Phương án |
|---|---|
| Không đủ GPU chạy Qwen2.5-14B | Dùng bản quantized 4-bit, hoặc gọi API; giữ interface LLM thay được |
| Vượt 10 phút/bài | Chạy song song, giới hạn số nguồn research, cache SERP, model nhỏ hơn (7B) cho Social/SEO |
| Flesch-Kincaid không hợp tiếng Việt | Chỉ số readability riêng cho VN, ghi rõ trong báo cáo |
| Hallucination / fact sai | Researcher bắt buộc trả nguồn; QA kiểm tra mỗi số liệu có citation |
| Hết quota SERP API | Cache theo keyword, mock dữ liệu khi dev |
| Khó tìm đủ 5 raters | Mời sớm từ tuần 5, form Google Forms sẵn |

## 11. Tài liệu tham khảo

**Repo**
1. CrewAI — https://github.com/crewAIInc/crewAI
2. GPT Researcher — https://github.com/assafelovic/gpt-researcher
3. GPT Author — https://github.com/mshumer/gpt-author

**Paper**
1. Sun et al., 2023 — *PEARL: Planning and Executing Actions for Instruction Following with a Knowledge Graph*
2. Xu et al., 2024 — *EduAgent: Gamified Student Simulation in Education*
3. Akula et al., 2020 — *CoCoX: Generating Conceptual and Counterfactual Explanations via Fault-Lines*
