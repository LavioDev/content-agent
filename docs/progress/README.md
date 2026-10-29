# Progress Tracker

Theo dõi tiến độ theo [PLAN.md](../PLAN.md) và [SPEC.md](../SPEC.md). Mỗi tuần tạo một file `week-XX.md` từ [_template.md](_template.md).

Ký hiệu: ⬜ chưa bắt đầu · ⏳ đang làm · ✅ xong · ⚠️ bị chặn

## Tổng quan mốc

| Tuần | Mốc | Trạng thái | Ghi chú |
|---|---|---|---|
| 1 | Setup & nghiên cứu | ✅ | [week-01](week-01.md). Chốt OpenRouter `qwen3-14b` @ DeepInfra |
| 2 | Researcher + Writer | ✅ | `steps.research`, `steps.write`, tool `research_topic`, `write_blog` |
| 3 | Editor + scorers | ✅ | `scoring/seo.py`, `scoring/readability.py` (VN + EN), có unit test |
| 4 | Social + SEO + QA + job runner | ✅ | Social ∥ SEO ∥ Images, vòng QA ≤ 2 lần, 4 biến thể ablation |
| 5 | Backend + MCP | ✅ | SQLite, REST + SSE, MCP 16 tool / 5 resource / 2 prompt (stdio + HTTP) |
| 6 | Dashboard | ✅ | Nuxt 4 + shadcn-vue: 8 trang, build thành công. Chưa kiểm tra bằng mắt trên trình duyệt |
| 7 | Đánh giá | ⏳ | Script `eval/benchmark.py` + 20 từ khoá sẵn; chưa chạy đủ, chưa có human rating |
| 8 | Hoàn thiện, báo cáo, demo | ⬜ | |

## KPI hiện tại

Số đo thật từ 2–3 bài chạy thử (chưa phải benchmark):

| Chỉ số | Mục tiêu | Hiện tại |
|---|---|---|
| Blog quality (human) | ≥ 4/5 | chưa chấm |
| SEO score | ≥ 80/100 | 90 / 90 |
| Thời gian/bài | < 10 phút | 80 s – 187 s |
| Chi phí/bài | báo cáo | $0.003 – $0.007 (≈ 80–185đ) |

## Việc tiếp theo

- [ ] Mở dashboard, chạy thử luồng demo mục 9.3 của SPEC, sửa lỗi giao diện nếu có
- [ ] Chạy `eval/benchmark.py` cho 4 biến thể (đủ 20 từ khoá)
- [ ] Mời 5 người chấm, nhập điểm trung bình bằng `--human-rating`
- [ ] Engagement proxy (LLM-as-judge) cho bài social
- [ ] Hỏi giảng viên: chấp nhận Qwen3-14B thay Qwen2.5-14B? 5 hay 6 agent?
