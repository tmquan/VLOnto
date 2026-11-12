// pdf_check proof: the same document plus deliberate defects (expected: FAIL on glyphs + bounds)
#import "common.typ": template, content, mono
#show: template.with(title: "VLOnto — tài liệu mẫu có lỗi cố ý")
#content

= Lỗi cố ý (để kiểm tra pdf_check.py)
+ Ký tự không có trong phông đã đóng gói (chữ Hán): 法律 — Typst vẽ ô .notdef mà không cảnh báo.
+ Dòng mã quá dài, không có chỗ ngắt dòng, tràn qua lề phải:
  ```text
  vlo:VanBanQuyPhamPhapLuatDuocSuaDoiBoSungThayTheHoacBaiBoMotPhanHoacToanBoBoiVanBanKhacCoHieuLucPhapLyCaoHon
  ```
+ Nhãn bị đặt ra ngoài mép giấy: #place(top + right, dx: 32mm, dy: 6mm, text(font: mono, weight: "bold")[NGOÀI LỀ GIẤY])
