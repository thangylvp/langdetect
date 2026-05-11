# Task Requirement — Phân loại ngôn ngữ EN/VI

## Mục tiêu

Phân loại ngôn ngữ của câu đầu vào thành một trong các nhãn:

| Label | Ý nghĩa |
|-------|---------|
| `en` | Tiếng Anh |
| `vi` | Tiếng Việt |
| `unknown` | Không đủ tín hiệu để phán quyết (confidence < 0.6) |
| `unsupported_language` | Ngôn ngữ ngoài scope (không phải vi/en) |

Tham chiếu các Bảng 1–4 ở [`phuluc.md`](phuluc.md).

---

## Quy tắc 1 — Câu thuần một ngôn ngữ

- Câu chỉ chứa từ tiếng Việt → **vi**
- Câu chỉ chứa từ tiếng Anh → **en**

---

## Quy tắc 2 — Câu chứa từ của cả hai ngôn ngữ

Một câu chứa cả từ tiếng Anh và tiếng Việt phải đi qua **đủ 4 bước theo thứ tự**. Mỗi bước chỉ kích hoạt nếu bước trước không thỏa mãn.

### Bước 1 — Quét tín hiệu ngữ pháp tiếng Việt (từ chức năng)

Trong câu xuất hiện ít nhất một **Từ chức năng tiếng Việt** (Giới từ, trợ từ, hư từ, động từ/trạng từ không phải mượn — Phụ lục A Bảng 3) → **vi**

Ví dụ:
- `"Show me status của project Vision"` → vi (vì có `của`)
- `"Check hộ mình cái report"` → vi (vì có `mình`)

### Bước 2 — Quét mỏ neo ngữ pháp tiếng Anh (Grammar Anchors)

*Nếu Bước 1 không thỏa mãn — tức là không chứa từ chức năng tiếng Việt.*

Câu bắt đầu bằng các cụm từ hỏi hoặc mệnh lệnh chuẩn tiếng Anh (Phụ lục A Bảng 4) → **en**

Ví dụ:
- `"Is Voi châu Á dangerous?"` → en

### Bước 3 — Quét cấu trúc Chủ ngữ + Động từ tiếng Việt (Vietnamese S+V)

*Nếu Bước 1 và Bước 2 không thỏa mãn.*

Cả **Chủ ngữ (Subject)** và **Động từ (Verb)** trong câu đều là từ tiếng Việt → **vi**

Ví dụ:
- `"Nhân viên trực gate 1"` → vi

### Bước 4 — Phân tích bản chất danh từ tiếng Việt (Entity vs. Common Noun)

*Nếu Bước 1, 2, 3 đều không thỏa mãn.*

- **Trường hợp 4.1** — Tất cả từ tiếng Việt đều là **Danh từ riêng / Cultural Term** (địa danh, tên người, món ăn, thương hiệu Việt, ngày lễ… — Phụ lục A Bảng 1) → **en**

  Ví dụ: `"Admin delete Áo Dài"` → en

- **Trường hợp 4.2** — Xuất hiện dù chỉ một **Danh từ phổ thông tiếng Việt** (Phụ lục A Bảng 2) → **vi**

  Ví dụ: `"Admin delete bài viết"` → vi

---

## Quy tắc 3 — Câu thiếu tín hiệu ngôn ngữ

Khi câu không chứa đủ tín hiệu để áp dụng quy tắc 1 và 2 — thường xảy ra với:

- Câu có 1 từ vô nghĩa
- Các từ tồn tại trong cả hai ngôn ngữ (số, mã hiệu, từ mượn)
- Cảm thán (`oh`, `ukm`, `wow`, `alo`, …)

→ Trả về **`unknown`** kèm `confidence < 0.6`. Không phán quyết cưỡng bức.

### Gợi ý xử lý cho downstream agent (thứ tự ưu tiên)

1. **Dùng context hội thoại** — nếu là hội thoại nhiều lượt, suy ra ngôn ngữ từ các câu trước/sau trong cùng session.
2. **Fallback về ngôn ngữ mặc định của người dùng** — nếu có profile.
3. **Bỏ qua phân biệt ngôn ngữ** — câu phản hồi ngắn không mang nội dung (`"ok"`, `"ừ"`, `"done"`) có thể xử lý chung một pipeline.

---

## Quy tắc 4 — Ngôn ngữ ngoài scope

Khi câu không phải tiếng Việt cũng không phải tiếng Anh → trả về **`error: unsupported_language`**. Không phán quyết thành `vi`/`en`.

---

## Bảng hệ quả

| # | Quy tắc | Trường hợp | Label |
|---|---------|------------|-------|
| 1 | Quy tắc 1 | Câu không chứa bất kỳ từ tiếng Việt nào | `en` |
| 2 | Quy tắc 1 | Câu không chứa bất kỳ từ tiếng Anh nào | `vi` |
| 3 | Quy tắc 2 | Câu lẫn hai ngôn ngữ, phần tiếng Việt chỉ có danh từ riêng / cultural term (Bảng 1) | `en` |
| 4 | Quy tắc 2 | Câu lẫn hai ngôn ngữ, phần tiếng Việt có danh từ phổ thông có từ tiếng Anh tương đương (Bảng 2) | `vi` |
| 5 | Quy tắc 2 | Câu lẫn hai ngôn ngữ, phần tiếng Việt có động từ | `vi` |
| 6 | Quy tắc 2 | Câu lẫn hai ngôn ngữ, phần tiếng Việt có tính từ | `vi` |
| 7 | Quy tắc 2 | Câu lẫn hai ngôn ngữ, phần tiếng Việt có trạng từ | `vi` |
| 8 | Quy tắc 2 | Câu lẫn hai ngôn ngữ, phần tiếng Việt có hư từ (`và, nhưng, vì, thì, mà, của, với, rất`…) | `vi` |
| 9 | Quy tắc 3 | Câu thiếu tín hiệu ngôn ngữ, không xác định được | `unknown` + confidence < 0.6 |
| 10 | Quy tắc 4 | Câu thuộc ngôn ngữ ngoài scope (không phải vi, không phải en) | `error: unsupported_language` |

---

## Output schema (gợi ý)

```python
{
    "label":      "en" | "vi" | "unknown" | "unsupported_language",
    "confidence": float,    # 0.0 - 1.0
    "rule":       str,      # vd "rule_2_step_1" — for explainability
    "evidence":   dict,     # token nào kích hoạt quy tắc nào
}
```
