# Ghi chép vấn đề

## #1 — SEO và độ dễ đọc thấp dần ở các bài sau (30/10/2026)

### Hiện tượng

Các bài tạo sau có cảm giác điểm SEO và độ dễ đọc giảm dần. Dữ liệu 4 bài trong `data.db`:

| Bài | Giọng văn | Chủ đề nhập | Từ khoá chính | SEO | Dễ đọc (thang cũ) | Câu TB (âm tiết) | Câu dài | Vòng QA |
|---|---|---|---|---|---|---|---|---|
| #6 | thân thiện | "Viết bài viết về hành trình phát triển bản thân" | 6 âm tiết | 80 | 78,8 | 23,8 | 6% | 1 |
| #7 | truyền cảm hứng | "Tìm hiểu về nick vujicic và viết tôi 1 bài…" | 5 | 95 | 49,9 | 27,3 | 21% | 3 |
| #8 | truyền cảm hứng | "tìm hiểu về ESP32 và viết tôi bài viết về lịch sử hình thành" | 5 | 45 | 50,4 | 26,0 | 25% | 3 |
| #9 | truyền cảm hứng | "viết tôi 1 bài dễ đọc về AI" | 6 | 70 | 63,2 | 26,3 | 12% | 3 |

Không phải pipeline "xuống cấp theo thời gian": mỗi job độc lập, không có trạng thái chung ngoài cache search 24h. Điểm thấp do cách nhập và 5 lỗi dưới đây.

### Nguyên nhân

1. **Vòng sửa QA không sửa được gì.** Ghi chú gửi Editor chỉ có tên mục trượt ("Từ khoá chính trong H1"), không có từ khoá, không chỉ câu nào dài. Prompt Editor lại dặn "giữ mọi heading". Bằng chứng: Editor ở các vòng sửa trả về đúng cùng số token (#8: 2264 → 2264; #9: 2504 → 2504), tức là gần như chép lại. 3 bài sau đều chạy hết 3 vòng, tốn ~2× thời gian/tiền mà điểm không tăng.
2. **Từ khoá chính dài, cứng, so khớp nguyên cụm.** #8: từ khoá "lịch sử hình thành ESP32", H1 viết "lịch sử hình thành *của* ESP32" → trượt H1, 100 từ đầu, H2, mật độ (SEO 45). #6: từ khoá 6 âm tiết lặp nhiều → mật độ 4,07% vượt trần.
3. **Chủ đề nhập dạng câu lệnh** ("tìm hiểu về… và viết tôi bài…") được dùng nguyên văn làm truy vấn search và làm chủ đề bài → search kém, H1 lẫn chữ "Tìm hiểu về…".
4. **Giọng "truyền cảm hứng" kéo dài câu** (26–27 âm tiết/câu vs 23,8), Writer không bị ép câu ngắn.
5. **Thang dễ đọc tiếng Việt quá khắt khe.** `\w+` đếm âm tiết chứ không phải từ, nhưng ngưỡng 20 "từ"/câu lấy từ tiếng Anh → câu 26 âm tiết (~18 từ thật, bình thường) bị trừ 24 điểm.

### Đã sửa

| # | Sửa | File |
|---|---|---|
| 1 | QA sinh **lệnh sửa cụ thể** (`qa_report.fixes`): nêu nguyên văn từ khoá cần đưa vào H1/câu đầu/H2, số lần cần dùng, danh sách câu dài cần tách. Lệnh sửa đặt **đầu** prompt Editor và được phép sửa heading. Editor luôn biết từ khoá. | `pipeline.py` (`_fixes`, `evaluate`), `steps.py` (`edit`) |
| 1b | **Dừng sớm** khi một vòng sửa không làm tăng SEO hoặc dễ đọc (`qa_report.stopped_early`). | `pipeline.py` |
| 2, 3 | Researcher chạy 2 bước: (a) tách `subject` khỏi câu lệnh, chọn `focus_keyword` 2–4 từ đọc tự nhiên trong câu/heading, sinh `search_query`; (b) search bằng query đó rồi lập outline (1 H2 chứa từ khoá). | `steps.py` (`research`) |
| 2 | Writer phải dùng **nguyên cụm** từ khoá trong H1, câu đầu và 1 H2. | `steps.py` (`write`) |
| 4 | Writer: "giọng văn đổi cách dùng từ, không đổi độ dài câu" — câu TB < 20 từ, không câu nào > 30 từ. | `steps.py` (`write`) |
| 5 | Thang dễ đọc VI tính theo âm tiết: câu TB ≤ 22 âm tiết, câu dài > 40 âm tiết. Trả kèm `long_examples` (tối đa 5 câu dài) để Editor biết sửa câu nào. | `scoring/readability.py` |

Chấm lại 4 bài cũ bằng thang mới (không đổi nội dung): #6 78,8 → 89,8 · #7 49,9 → 64,4 · #8 50,4 → 73,7 · #9 63,2 → 80,2. Điểm cũ trong DB **không** tự cập nhật; báo cáo cần ghi rõ dùng thang nào.

Test: 21 test qua (thêm test dừng sớm, lệnh sửa có từ khoá + câu dài + nguồn, thang âm tiết).

### Chạy lại thật sau khi sửa (cùng chủ đề, giọng "truyền cảm hứng")

| Chủ đề | Từ khoá chính | SEO | Dễ đọc | Câu TB | Câu dài | Vòng QA | Thời gian | Chi phí |
|---|---|---|---|---|---|---|---|---|
| ESP32 (trước: #8) | "lịch sử ESP32" (trước: "lịch sử hình thành ESP32") | 45 → **80** | 99 | 22,2 | 0% | 3 | 183 s | $0.0073 |
| AI (trước: #9) | "trí tuệ nhân tạo là gì" | 70 → **80** | 100 | 18,3 | 0% | 1 | 97 s | $0.0039 |

Dễ đọc tăng thật (câu ngắn hơn), không chỉ do đổi thang. Cả 2 bài vẫn trượt mục **link nguồn** → vấn đề #2.

## #2 — Bài không có link nguồn (30/10/2026)

- Bài ESP32 có 3 nguồn từ search nhưng blog cuối có 0 link: Writer/Editor/SEO làm rơi link khi viết lại.
  **Đã sửa:** khi trượt mục link, lệnh sửa QA liệt kê sẵn các nguồn `[tiêu đề](url)` để Editor chèn vào; không có nguồn thì không yêu cầu (tránh bịa link).
- Bài AI có 0 nguồn: DuckDuckGo trả về rỗng (cache search không có truy vấn này). **Còn mở:** nên thêm `SERPER_API_KEY` cho benchmark, DuckDuckGo không ổn định.

### Còn mở (#1)

- Ngưỡng 22/40 âm tiết là ước lượng — hiệu chỉnh lại khi có điểm human rating.
- Mẫu mới có 4 bài + 2 bài chạy lại; cần benchmark đủ 20 từ khoá để kết luận.
- Từ khoá vẫn so khớp nguyên cụm (bỏ dấu, không phân biệt hoa thường). Cách này chặt hơn Yoast thật, nhưng giữ để chấm điểm nhất quán.
