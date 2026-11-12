#!/usr/bin/env python3
"""Deterministic fixtures for the toolchain proofs (synthetic sample data, not legal facts).

  make_test_data.py OUT_WEB_DIR
writes  OUT/proof/data_src/test_graph.json   2,000 nodes (20 laws, 180 decrees/circulars, 1,800 articles)
        OUT/proof/data_src/sample.ttl        8 documents with Vietnamese titles (vlo: namespace)
        OUT/proof/fonts_test.html            every Vietnamese letter + required symbols in the 3 font stacks
        OUT/proof/fonts_embedded_test.html   same page using the data: URI font CSS
        OUT/sample_site/data_src/stats.json  dashboard numbers for the sample site
"""
import json
import random
import sys
import unicodedata
from pathlib import Path

out = Path(sys.argv[1])
(out / "proof/data_src").mkdir(parents=True, exist_ok=True)
(out / "sample_site/data_src").mkdir(parents=True, exist_ok=True)
rnd = random.Random(20261111)

LAW_NAMES = ["Luật Đất đai", "Bộ luật Lao động", "Bộ luật Dân sự", "Luật Hôn nhân và gia đình", "Luật Bảo hiểm xã hội",
             "Luật Giao thông đường bộ", "Luật Doanh nghiệp", "Luật Đầu tư", "Luật Nhà ở", "Luật Thuế thu nhập cá nhân",
             "Luật Xử lý vi phạm hành chính", "Luật Tố tụng hành chính", "Luật Cư trú", "Luật Căn cước", "Luật Giáo dục",
             "Luật Khám bệnh, chữa bệnh", "Luật Bảo vệ môi trường", "Luật Phòng cháy, chữa cháy", "Luật Thương mại",
             "Luật Hộ tịch"]
nodes, links = [], []
for i, name in enumerate(LAW_NAMES):
    nodes.append({"id": f"L{i:02d}", "kind": "law", "label": f"{name} (mẫu)"})
for j in range(180):
    law = j % 20
    kind = "decree" if j % 3 else "circular"
    label = (f"Nghị định {j + 1:03d}/20{20 + j % 6}/NĐ-CP" if kind == "decree" else f"Thông tư {j + 1:02d}/20{20 + j % 6}/TT-BTC")
    nodes.append({"id": f"D{j:03d}", "kind": kind, "label": label})
    links.append({"source": f"D{j:03d}", "target": f"L{law:02d}", "rel": "hướng dẫn"})
for k in range(1800):
    parent = rnd.randrange(200)
    pid = f"L{parent:02d}" if parent < 20 else f"D{parent - 20:03d}"
    nodes.append({"id": f"A{k:04d}", "kind": "article", "title": f"Điều {k % 120 + 1}"})
    links.append({"source": f"A{k:04d}", "target": pid, "rel": "thuộc"})
for _ in range(400):
    a, b = rnd.randrange(1800), rnd.randrange(1800)
    if a != b:
        links.append({"source": f"A{a:04d}", "target": f"A{b:04d}", "rel": "dẫn chiếu"})
graph = {"nodes": nodes, "links": links,
         "note": "Dữ liệu mẫu tổng hợp cho kiểm thử kỹ thuật - không phải dữ liệu pháp lý."}
(out / "proof/data_src/test_graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=0), encoding="utf-8")

TTL = """@prefix vlo: <https://tmquan.github.io/VLOnto/ontology#> .
@prefix id: <https://tmquan.github.io/VLOnto/id/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
# Sample fixture for the toolchain proof (titles/numbers only; no legal-status claims).
"""
DOCS = [("luat-45-2013-qh13", "Luật", "45/2013/QH13", "Luật Đất đai", "Land Law", 2013),
        ("luat-31-2024-qh15", "Luật", "31/2024/QH15", "Luật Đất đai", "Land Law", 2024),
        ("bo-luat-91-2015-qh13", "Bộ luật", "91/2015/QH13", "Bộ luật Dân sự", "Civil Code", 2015),
        ("bo-luat-45-2019-qh14", "Bộ luật", "45/2019/QH14", "Bộ luật Lao động", "Labour Code", 2019),
        ("luat-52-2014-qh13", "Luật", "52/2014/QH13", "Luật Hôn nhân và gia đình", "Law on Marriage and Family", 2014),
        ("luat-41-2024-qh15", "Luật", "41/2024/QH15", "Luật Bảo hiểm xã hội", "Law on Social Insurance", 2024),
        ("nd-100-2019-nd-cp", "Nghị định", "100/2019/NĐ-CP", "Nghị định quy định xử phạt vi phạm hành chính trong lĩnh vực giao thông đường bộ và đường sắt", "Decree 100/2019", 2019),
        ("nd-168-2024-nd-cp", "Nghị định", "168/2024/NĐ-CP", "Nghị định quy định xử phạt vi phạm hành chính về trật tự, an toàn giao thông trong lĩnh vực giao thông đường bộ", "Decree 168/2024", 2024)]
for slug, typ, num, vi, en, year in DOCS:
    TTL += (f'\nid:{slug} a vlo:LegalDocument ;\n    vlo:documentType "{typ}"@vi ;\n    vlo:documentNumber "{num}" ;\n'
            f'    vlo:title "{vi}"@vi , "{en}"@en ;\n    vlo:year "{year}"^^xsd:gYear .\n')
(out / "proof/data_src/sample.ttl").write_text(TTL, encoding="utf-8")

stats = {"documents": 40816, "chunks": 659589, "relations": 15035,
         "by_type": [["Luật", 412], ["Nghị định", 6120], ["Thông tư", 14390], ["Quyết định", 17204], ["Nghị quyết", 2690]],
         "by_year": [[y, n] for y, n in zip(range(2015, 2027), [2410, 2633, 2790, 2954, 3120, 3302, 3416, 3608, 3781, 3920, 4105, 3277])],
         "note": "Số liệu mẫu cho trang kiểm thử (sample numbers)."}
(out / "sample_site/data_src/stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

# font test pages
VOW = "aăâeêioôơuưy"
TONES = ["", "\u0300", "\u0301", "\u0309", "\u0303", "\u0323"]
low = " ".join("".join(unicodedata.normalize("NFC", v + t) for t in TONES) for v in VOW) + " đ"
up = " ".join("".join(unicodedata.normalize("NFC", v.upper() + t) for t in TONES) for v in VOW) + " Đ"
SYMS = "→ ← ✓ ✗ • – — “ ” ‘ ’ … § ≤ ≥ × ° ² ₫ « » ↔ ⇒ ≠ ±"
SENT = "Điều 12. Quyền và nghĩa vụ của người sử dụng đất được pháp luật bảo hộ; mọi hành vi xâm phạm đều bị xử lý."


def page(css: str, title: str) -> str:
    rows = []
    for var, name in (("--vlo-font-sans", "Sans: Be Vietnam Pro"), ("--vlo-font-serif", "Serif: Noto Serif"),
                      ("--vlo-font-mono", "Mono: JetBrains Mono NL")):
        rows.append(f"""<section style="font-family: var({var})">
  <h2>{name}</h2>
  <p class="l">{low}</p>
  <p class="l">{up}</p>
  <p class="l"><b>{up}</b></p>
  <p class="l"><i>{low}</i></p>
  <p class="s">{SYMS}</p>
  <p>{SENT}</p>
</section>""")
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css}">
<style>
  body {{ margin: 0; padding: 16px 20px; color: #141b2d; background: #fff; font-family: var(--vlo-font-sans); }}
  h1 {{ font-size: 20px; line-height: 1.4; margin: 0 0 12px; }}
  h2 {{ font-size: 15px; line-height: 1.4; margin: 14px 0 4px; color: #3d4a75; }}
  p {{ margin: 2px 0; font-size: 15px; line-height: 1.7; overflow-wrap: anywhere; }}
  .l {{ letter-spacing: 0.02em; }}
  .s {{ font-size: 17px; }}
</style>
</head>
<body>
<h1>{title}</h1>
{chr(10).join(rows)}
</body>
</html>
"""


(out / "proof/fonts_test.html").write_text(page("fonts/fonts.css", "Kiểm thử phông chữ tiếng Việt (fonts.css)"), encoding="utf-8")
(out / "proof/fonts_embedded_test.html").write_text(page("fonts/fonts-embedded.css", "Kiểm thử phông chữ nhúng (fonts-embedded.css)"), encoding="utf-8")
print(f"fixtures: {len(nodes)} nodes, {len(links)} links, {len(DOCS)} TTL documents, font pages written")
