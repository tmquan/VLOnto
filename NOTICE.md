# Notices

## Attribution

> VLOnto is derived from six datasets published on Hugging Face by TMQuan: `thuvienphapluat-vn-vbpl` (metadata CC BY 4.0; source thuvienphapluat.vn), `thuvienphapluat-vn-hdpl`, `thuvienphapluat-vn-tnpl` and `thuvienphapluat-vn-htpl` (source thuvienphapluat.vn and thuvienphapluat.vn/tnpl/; only identifiers, links, dates, categories, term names and derived links are used), `anle-toaan-gov-vn` (CC BY 4.0; source anle.toaan.gov.vn, Supreme People's Court of Viet Nam) and `cbba-toaan-gov-vn` (CC BY 4.0; source congbobanan.toaan.gov.vn, Supreme People's Court of Viet Nam). English term labels from `tnpl` are machine translations. Extracted relations are produced automatically and may be wrong. VLOnto is not an official legal text and is not legal advice.

Vietnamese:

> VLOnto được xây dựng từ sáu bộ dữ liệu do TMQuan công bố trên Hugging Face: `thuvienphapluat-vn-vbpl` (siêu dữ liệu theo CC BY 4.0; nguồn thuvienphapluat.vn), `thuvienphapluat-vn-hdpl`, `thuvienphapluat-vn-tnpl`, `thuvienphapluat-vn-htpl` (nguồn thuvienphapluat.vn; chỉ dùng mã định danh, liên kết, ngày, lĩnh vực, tên thuật ngữ và các liên kết suy ra), `anle-toaan-gov-vn` (CC BY 4.0; nguồn anle.toaan.gov.vn, Tòa án nhân dân tối cao) và `cbba-toaan-gov-vn` (CC BY 4.0; nguồn congbobanan.toaan.gov.vn, Tòa án nhân dân tối cao). Tên tiếng Anh của thuật ngữ là bản dịch máy. Các quan hệ được trích xuất tự động và có thể sai. VLOnto không phải văn bản pháp luật chính thức và không phải tư vấn pháp lý.

## Source datasets

| Dataset | Revision | Licence |
|---|---|---|
| [`tmquan/thuvienphapluat-vn-vbpl`](https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-vbpl) | `705ade5853` | cc-by-4.0 |
| [`tmquan/thuvienphapluat-vn-hdpl`](https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-hdpl) | `e814ecbfa1` | other |
| [`tmquan/thuvienphapluat-vn-tnpl`](https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-tnpl) | `f94d1e2485` | other |
| [`tmquan/thuvienphapluat-vn-htpl`](https://huggingface.co/datasets/tmquan/thuvienphapluat-vn-htpl) | `043c8f2988` | other |
| [`tmquan/anle-toaan-gov-vn`](https://huggingface.co/datasets/tmquan/anle-toaan-gov-vn) | `d6124923dd` | cc-by-4.0 |
| [`tmquan/cbba-toaan-gov-vn`](https://huggingface.co/datasets/tmquan/cbba-toaan-gov-vn) | `8ace3afc9c` | cc-by-4.0 |

## Question titles on the Traces page

The Traces page (`site/traces.html`, data in `site/data/traces/`) shows the titles of the 538 questions it traces, as
published on thuvienphapluat.vn (`thuvienphapluat-vn-hdpl`, revision `e814ecbfa1`), each with a link to its source
and a machine-assisted English gloss. It shows no answer text. The titles remain subject to the terms of
thuvienphapluat.vn.

Trang Truy vết (`site/traces.html`, dữ liệu trong `site/data/traces/`) hiển thị tiêu đề của 538 câu hỏi được truy vết,
như đăng trên thuvienphapluat.vn (`thuvienphapluat-vn-hdpl`, phiên bản `e814ecbfa1`), kèm liên kết tới nguồn và bản
dịch tiếng Anh có sự hỗ trợ của máy. Trang không hiển thị nội dung câu trả lời. Các tiêu đề vẫn tuân theo điều khoản
của thuvienphapluat.vn.

## Third-party components

- Fonts in `site/fonts/` and `typst/fonts/` (Be Vietnam Pro, Noto Serif, JetBrains Mono NL, Noto Sans Symbols 2,
  Noto Sans Math) and the web-only Latin + Vietnamese subset of Libertinus Sans 7.051 used by the 3D views (the figure
  font of the paper): SIL Open Font License 1.1; licence files are next to the fonts.
- JavaScript libraries in `site/vendor/` (three.js, 3d-force-graph, three-spritetext, ECharts, Oxigraph): see
  `site/vendor/THIRD_PARTY_LICENSES.md` and `tools/vendor.lock.json`.
