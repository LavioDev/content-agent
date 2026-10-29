# Báo giá LLM (OpenRouter) — tra cứu 29/10/2026

Nguồn: `https://openrouter.ai/api/v1/models` và `/api/v1/models/qwen/qwen3.8-27b/endpoints`. Giá có thể đổi, kiểm tra lại trước khi chạy đánh giá.

## Model chính: `qwen/qwen3.8-27b`

- Open-weight, dense, 27B, đa phương thức (text + ảnh + video → text)
- Hỗ trợ tools, structured outputs, reasoning (thinking, có thể điều chỉnh `reasoning_effort`)
- Context 262K (một số provider 1M)
- **Không có biến thể `:free`** trên OpenRouter (đó là lý do tìm `qwen3.8-27b:free` không ra)

### Giá theo provider ($/1M token)

| Provider | Input | Output | Context | Ghi chú |
|---|---|---|---|---|
| Chutes (fp8) | 0.039 | 1.25 | 262K | **Rẻ nhất** |
| Near AI (fp8) | 0.040 | 1.35 | 262K | Uptime 99.9% |
| Darkbloom (fp4) | 0.035 | 2.20 | 262K | fp4 có thể giảm chất lượng |
| Reka / Modal | 0.040 | 2.20 / 2.30 | 262K | |
| Tenstorrent (fp4) | 0.15 | 1.50 | 262K | |
| DeepInfra (bf16) | 0.15 | 1.875 | 262K | Chưa quantize |
| Cerebras (fp16) | 0.99 | 1.49 | 65K | Thường rất nhanh, context nhỏ |
| Alibaba (chính chủ) | 0.425 | 2.55 | 1M | |
| Novita | 0.42 | 3.00 | 1M | |

Một số provider khác (Wafer, DekaLLM, ModelRun, Phala, AkashML, Parasail, CoreWeave, Cloudflare, Venice, Mancer) có giá cao hơn hoặc ngang các dòng trên.

## Model so sánh

| Model | Input | Output | Context |
|---|---|---|---|
| `qwen/qwen3-14b` @ NextBit (int4) | 0.10 | 0.22 | 41K |
| `qwen/qwen3-14b` @ DeepInfra (fp8) | 0.12 | 0.24 | 41K |
| `qwen/qwen3.8-flash` | 0.15 | 0.47 | 1M |
| `qwen/qwen3.8-max-0902` | 2.00 | 6.00 | 1M |

## Ước tính chi phí mỗi bài

Giả định: 30.000 token input + 10.000 token output (6 agent, kèm dữ liệu research).
Đây là ước tính của mình, cần thay bằng số đo thật từ log khi pipeline chạy.

| Cấu hình | Không thinking | Thinking (output ×3) |
|---|---|---|
| qwen3.8-27b @ Chutes | ~$0.014 | ~$0.039 |
| qwen3.8-27b @ DeepInfra | ~$0.023 | ~$0.061 |
| qwen3.8-27b @ Alibaba | ~$0.038 | ~$0.108 |
| qwen3-14b @ NextBit | ~$0.0052 (~140đ) | ~$0.0096 (~250đ) |
| qwen3-14b @ DeepInfra | ~$0.0060 (~160đ) | ~$0.0108 (~290đ) |

Quy đổi 1 USD ≈ 26.500đ (tỷ giá ước lượng tháng 7/2026, chưa kiểm tra lại). Nạp $5 ≈ 132.000đ, chưa tính phí nạp/ngân hàng.

Chạy 20 bài test + 5 lượt thử mỗi bài khoảng 100 lượt: ≈ $1.4 (27b @ Chutes, không thinking) hoặc ≈ $0.6 (qwen3-14b).

## Khuyến nghị

1. Ngân sách đề tài: nạp **$5** là dư.
2. Dùng `qwen3-14b` nếu muốn bám đúng "cỡ 14B" của đề, rẻ nhất, nhưng context chỉ 41K.
3. Dùng `qwen3.8-27b` nếu ưu tiên chất lượng tiếng Việt; chọn provider rẻ (Chutes, Near AI) bằng `provider.order` hoặc routing `floor`.
4. Output đắt gấp 30 lần input ở 27b, nên **giới hạn `max_tokens` và tắt/giảm thinking** (`reasoning_effort` thấp) cho các agent không cần suy luận (Social Adapter, SEO).
5. Đặt `Key limit` của key OpenRouter thấp (vd $5) để tránh phát sinh ngoài ý muốn.
