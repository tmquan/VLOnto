// Shared template + content for the pdf_check proof documents (Vietnamese, vendored fonts only).
// Build: typst compile --root tools/tests/typst --font-path typst/fonts --ignore-system-fonts \
//          --ignore-embedded-fonts --creation-timestamp 1767225600 tools/tests/typst/sample_ok.typ out.pdf
// Noto Serif has no ≠ ≤ ≥ → ←: without the `covers` entry HarfBuzz draws ≠ from Noto Serif as "=" + U+0338
// (combining overlay, misplaced). Arrows and mathematical operators therefore always come from Noto Sans Math.
#let math-symbols = (name: "Noto Sans Math", covers: regex("[\u{2190}-\u{21FF}\u{2200}-\u{22FF}]"))
#let sans = ("Be Vietnam Pro", "Noto Sans Symbols 2", "Noto Sans Math")
#let serif = (math-symbols, "Noto Serif", "Noto Sans Symbols 2", "Noto Sans Math")
#let mono = ("JetBrains Mono NL", "Noto Sans Symbols 2", "Noto Sans Math")

#let template(title: "", body) = {
  set document(title: title, author: "VLOnto toolchain")
  set page(
    paper: "a4",
    margin: (top: 22mm, right: 20mm, bottom: 24mm, left: 20mm),
    header: context {
      set text(font: sans, size: 8.5pt, fill: luma(90))
      [VLOnto · Sổ tay kiểm thử #h(1fr) Tài liệu mẫu]
    },
    footer: context {
      set text(font: sans, size: 8.5pt, fill: luma(90))
      align(center)[Trang #counter(page).display("1 / 1", both: true)]
    },
  )
  set text(font: serif, size: 10.5pt, lang: "vi")
  set par(justify: true, leading: 0.72em, spacing: 1.1em)
  set heading(numbering: "1.")
  show heading: set text(font: sans, weight: "bold")
  show heading.where(level: 1): set text(size: 14pt)
  show raw: set text(font: mono, size: 8.8pt)
  show raw.where(block: true): block.with(fill: luma(246), inset: 8pt, radius: 3pt, width: 100%)
  show math.equation: set text(font: "Noto Sans Math")
  body
}

#let content = [
  #align(center, text(font: sans, size: 19pt, weight: "bold")[Sổ tay VLOnto — tài liệu mẫu])
  #align(center, text(font: sans, size: 10.5pt, fill: luma(80))[Kiểm thử bộ công cụ: phông chữ tiếng Việt, lề trang, mã nguồn, bảng, công thức])

  = Mục đích
  Tài liệu này kiểm tra rằng mọi chữ cái tiếng Việt đều hiển thị đúng với các phông chữ đã đóng gói: chữ có dấu huyền, sắc, hỏi, ngã, nặng; các nguyên âm ă, â, ê, ô, ơ, ư và phụ âm đ. Người sử dụng đất có quyền và nghĩa vụ theo quy định của pháp luật; quyền lợi hợp pháp được Nhà nước bảo hộ. Văn bản quy phạm pháp luật có hiệu lực pháp lý cao hơn được ưu tiên áp dụng khi có quy định khác nhau về cùng một vấn đề.

  _Chữ nghiêng:_ #emph[Điều 1. Phạm vi điều chỉnh — Luật này quy định về chế độ sở hữu đất đai.] *Chữ đậm:* *Quyền và nghĩa vụ của công dân đối với đất đai.*

  = Bảng chữ cái có dấu
  #text(font: sans)[
    a à á ả ã ạ ă ằ ắ ẳ ẵ ặ â ầ ấ ẩ ẫ ậ e è é ẻ ẽ ẹ ê ề ế ể ễ ệ i ì í ỉ ĩ ị o ò ó ỏ õ ọ ô ồ ố ổ ỗ ộ ơ ờ ớ ở ỡ ợ u ù ú ủ ũ ụ ư ừ ứ ử ữ ự y ỳ ý ỷ ỹ ỵ đ \
    A À Á Ả Ã Ạ Ă Ằ Ắ Ẳ Ẵ Ặ Â Ầ Ấ Ẩ Ẫ Ậ E È É Ẻ Ẽ Ẹ Ê Ề Ế Ể Ễ Ệ I Ì Í Ỉ Ĩ Ị O Ò Ó Ỏ Õ Ọ Ô Ồ Ố Ổ Ỗ Ộ Ơ Ờ Ớ Ở Ỡ Ợ U Ù Ú Ủ Ũ Ụ Ư Ừ Ứ Ử Ữ Ự Y Ỳ Ý Ỷ Ỹ Ỵ Đ
  ]

  a à á ả ã ạ ă ằ ắ ẳ ẵ ặ â ầ ấ ẩ ẫ ậ e è é ẻ ẽ ẹ ê ề ế ể ễ ệ i ì í ỉ ĩ ị o ò ó ỏ õ ọ ô ồ ố ổ ỗ ộ ơ ờ ớ ở ỡ ợ u ù ú ủ ũ ụ ư ừ ứ ử ữ ự y ỳ ý ỷ ỹ ỵ đ \
  A À Á Ả Ã Ạ Ă Ằ Ắ Ẳ Ẵ Ặ Â Ầ Ấ Ẩ Ẫ Ậ E È É Ẻ Ẽ Ẹ Ê Ề Ế Ể Ễ Ệ I Ì Í Ỉ Ĩ Ị O Ò Ó Ỏ Õ Ọ Ô Ồ Ố Ổ Ỗ Ộ Ơ Ờ Ớ Ở Ỡ Ợ U Ù Ú Ủ Ũ Ụ Ư Ừ Ứ Ử Ữ Ự Y Ỳ Ý Ỷ Ỹ Ỵ Đ

  = Ký hiệu
  Thân văn: → ← ✓ ✗ • – — “ ” ‘ ’ … § ≤ ≥ × ° ² ₫ « » ↔ ⇒ ≠ ± \
  #text(font: sans)[Tiêu đề: → ← ✓ ✗ • – — “ ” ‘ ’ … § ≤ ≥ × ° ² ₫ « » ↔ ⇒ ≠ ±] \
  `Mã: → ← ✓ ✗ • – — “ ” ‘ ’ … § ≤ ≥ × ° ² ₫ « » ↔ ⇒ ≠ ±`

  = Mã nguồn
  ```sparql
  PREFIX vlo: <https://tmquan.github.io/VLOnto/ontology#>
  SELECT ?vb ?tieuDe ?nam WHERE {
    ?vb a vlo:LegalDocument ;
        vlo:title ?tieuDe ;            # “Luật Đất đai”@vi
        vlo:year ?nam .
    FILTER(LANG(?tieuDe) = "vi" && ?nam >= 2013)
  } ORDER BY ?nam
  ```

  = Bảng
  #table(
    columns: (auto, 1fr, auto),
    inset: 6pt,
    table.header([*Số hiệu*], [*Tên văn bản*], [*Năm*]),
    [31/2024/QH15], [Luật Đất đai], [2024],
    [45/2019/QH14], [Bộ luật Lao động], [2019],
    [168/2024/NĐ-CP], [Nghị định quy định xử phạt vi phạm hành chính về trật tự, an toàn giao thông trong lĩnh vực giao thông đường bộ], [2024],
  )

  = Công thức
  Số văn bản còn hiệu lực thỏa mãn $ sum_(i=1)^n x_i <= n dot max_i x_i $ với $x_i >= 0$.

  #pagebreak()
  = Trang hai: đoạn văn dài
  #for i in range(1, 7) [
    Khoản #i. Tổ chức, cá nhân có trách nhiệm thực hiện đúng quy định về quản lý, sử dụng đất; khi phát hiện hành vi vi phạm thì kịp thời báo cáo cơ quan nhà nước có thẩm quyền xử lý theo quy định của pháp luật. Việc giải quyết tranh chấp được thực hiện công khai, minh bạch, bảo đảm quyền và lợi ích hợp pháp của các bên liên quan.

  ]
]
