# Sổ tay VLOnto: thử chuỗi Markdown → Typst

Chuỗi xử lý: **Markdown** → `pandoc -t typst` → *Typst* → PDF. Văn bản tiếng Việt có đủ dấu: huyền, sắc, hỏi, ngã, nặng; các chữ ă, â, ê, ô, ơ, ư, đ.[^1]

## Danh sách

- Luật → Nghị định → Thông tư → Điều
- Trạng thái: ✓ còn hiệu lực, ✗ hết hiệu lực
- Ký hiệu: “ngoặc kép” ‘đơn’ … § ≤ ≥ × ° ² ≠ ₫

1. Tải dữ liệu.
2. Dựng đồ thị tri thức.
3. Kiểm tra bằng SHACL.

## Bảng

| Số hiệu         | Tên văn bản      | Năm  |
|-----------------|------------------|-----:|
| 31/2024/QH15    | Luật Đất đai     | 2024 |
| 45/2019/QH14    | Bộ luật Lao động | 2019 |

## Mã nguồn

```sparql
PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
SELECT ?vb ?tieuDe WHERE {
  ?vb a vlo:LegalDocument ; vlo:title ?tieuDe .   # “Luật Đất đai”@vi
}
```

> Trích dẫn: Văn bản có hiệu lực pháp lý cao hơn được ưu tiên áp dụng.

Xem thêm trang dự án tại <https://tmquan.github.io/VLOnto/>.

---

[^1]: Chú thích cuối trang bằng tiếng Việt: dữ liệu mẫu.
