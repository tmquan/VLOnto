"""Shared Vietnamese legal-text utilities for the data pipeline.

Everything here is deterministic and dependency-free (stdlib only) so the same
functions run in cleaning, chunking, validity mapping, evaluation and serving.
"""
import re, unicodedata
from datetime import date, timedelta

# ----------------------------------------------------------------- Unicode
_ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffd]")
_SP = re.compile(r"[ \t\u00a0\u2002\u2003\u2009\u202f\u3000]+")

def nfc(s):
    return unicodedata.normalize("NFC", s) if s else s

def basic_clean(s):
    """NFC + remove zero-width/soft-hyphen/control chars + unify spaces."""
    if not s:
        return s
    s = unicodedata.normalize("NFC", s)
    s = _ZW.sub("", s)
    s = _CTRL.sub(" ", s)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(_SP.sub(" ", ln).strip() for ln in s.split("\n"))
    return s

# --------------------------------------------- tone placement normalisation
# old-style (hoà, thuỷ) vs new-style (hòa, thủy) tone placement: normalise to the
# new style for matching keys / BM25 tokens (display text keeps the source form)
_TONES = {"\u0300": 0, "\u0301": 1, "\u0303": 2, "\u0309": 3, "\u0323": 4}
_OLD2NEW = {}
for v1, v2 in [("o", "a"), ("o", "e"), ("u", "y")]:
    for t in _TONES:
        old = unicodedata.normalize("NFC", v1 + v2 + t)            # oà
        new = unicodedata.normalize("NFC", v1 + t + v2)            # òa
        _OLD2NEW[old] = new
        _OLD2NEW[old.upper()] = new.upper()
        _OLD2NEW[unicodedata.normalize("NFC", v1.upper() + v2 + t)] = unicodedata.normalize("NFC", v1.upper() + t + v2)
_OLD_RE = re.compile("(" + "|".join(sorted(map(re.escape, _OLD2NEW), key=len, reverse=True)) + r")(?![a-zA-Zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ])")

def tone_new_style(s):
    """'hoà' -> 'hòa', 'thuỷ' -> 'thủy' (only at syllable end, so 'hoàn' is untouched)."""
    return _OLD_RE.sub(lambda m: _OLD2NEW[m.group(1)], s) if s else s

def strip_diacritics(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")

def name_key(s):
    """Matching key for law names: NFC, new-style tones, lowercase, punctuation-free."""
    s = tone_new_style(nfc(s or "")).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())

# --------------------------------------------- Vietnamese syllable validator
_ONSETS = sorted(["ngh", "ng", "nh", "ch", "gh", "gi", "kh", "ph", "qu", "th", "tr", "b", "c", "d", "đ", "g",
                  "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "x", ""], key=len, reverse=True)
_RHYMES = set("""a ai ao au ay ac ach am an ang anh ap at ăc ăm ăn ăng ăp ăt âc âm ân âng âp ât âu ây
e eo ec em en eng ep et ê êch êm ên ênh êp êt êu i ia ich im in inh ip it iu iêc iêm iên iêng iêp iêt iêu
o oa oac oach oai oam oan oang oanh oao oap oat oay oăc oăm oăn oăng oăt oc oe oen oeo oet oi om on ong
ooc oong op ot ô ôc ôi ôm ôn ông ôp ôt ơ ơi ơm ơn ơp ơt u ua uân uâng uât uây uc uê uêch uênh ui um un ung
uơ uôc uôi uôm uôn uông uôt up ut uy uya uych uyên uyêt uynh uyt uyu ư ưa ưc ưi ưm ưn ưng ươc ươi ươm
ươn ương ươp ươt ươu ưt ưu y yêm yên yêng yêt yêu uyn uych oong""".split())
_TONE_CHARS = set(_TONES)

def _toneless(w):
    d = unicodedata.normalize("NFD", w.lower())
    return unicodedata.normalize("NFC", "".join(ch for ch in d if ch not in _TONE_CHARS))

_VALID_CACHE = {}
def valid_syllable(w):
    r = _VALID_CACHE.get(w)
    if r is not None:
        return r
    t = _toneless(w)
    ok = False
    for o in _ONSETS:
        if t.startswith(o):
            rest = t[len(o):]
            if rest in _RHYMES or (o == "gi" and rest in ("", "n", "ng", "m", "t", "c", "p", "u")) or (o == "qu" and rest in ("y", "ynh", "yt", "yên", "yêt", "ây", "ân", "ât", "a", "ang", "an", "at", "ac", "anh", "ach", "e", "en", "et", "ê", "ên", "êt", "ênh", "êch", "i", "o", "ơ", "yn")):
                ok = True
                break
    if len(_VALID_CACHE) < 2_000_000:
        _VALID_CACHE[w] = ok
    return ok

_ALPHA = re.compile(r"^[^\W\d_]+$")

def repair_split_syllables(line, freq=None):
    """Merge fragments split by HTML span artefacts: 'TƯ Ớ NG' -> 'TƯỚNG',
    'th ể' -> 'thể', 'n ô ng' -> 'nông'. A merge needs >=1 invalid fragment and a
    valid result; ties are broken by corpus syllable frequency (freq)."""
    if not line or " " not in line:
        return line, 0
    ws = line.split(" ")
    n = len(ws); out = []; i = 0; merges = 0
    f = freq or {}
    while i < n:
        w = ws[i]
        if _ALPHA.match(w):
            done = False
            # 3-way merge
            if i + 2 < n and _ALPHA.match(ws[i + 1]) and _ALPHA.match(ws[i + 2]):
                parts = ws[i:i + 3]
                if any(not valid_syllable(p) for p in parts) and valid_syllable("".join(parts)) and len("".join(parts)) <= 8:
                    out.append("".join(parts)); i += 3; merges += 1; done = True
            if not done and i + 1 < n and _ALPHA.match(ws[i + 1]):
                a, b = w, ws[i + 1]
                va, vb = valid_syllable(a), valid_syllable(b)
                if (not va or not vb) and valid_syllable(a + b) and len(a + b) <= 8:
                    # alternative: b belongs to the next fragment (nhà n ước -> nhà nước)
                    alt = None
                    if va and not vb and i + 2 < n and _ALPHA.match(ws[i + 2]) and valid_syllable(b + ws[i + 2]):
                        alt = b + ws[i + 2]
                    if alt is not None and f.get(alt.lower(), 0) > f.get((a + b).lower(), 0):
                        out.append(a); out.append(alt); i += 3; merges += 1; done = True
                    else:
                        out.append(a + b); i += 2; merges += 1; done = True
            if not done:
                out.append(w); i += 1
        else:
            out.append(w); i += 1
    return " ".join(out), merges

# ------------------------------------------------------------ line unwrapping
MARKER = re.compile(r"""^\s*[“"'(\[]?\s*(?:
    Điều\s+\d | Chương\s+[IVXLCDM\d] | CHƯƠNG\s+[IVXLCDM\d] | Mục\s+\d | MỤC\s+\d | Phần\s+thứ | PHẦN\s+THỨ |
    Tiểu\s+mục | \d{1,3}[\.\)]\s | \d{1,3}\.\d | [a-zđ]\)\s | [-+•–*]\s | [IVX]{1,5}[\.\)]\s |
    Nơi\s+nhận | Căn\s+cứ | Xét\s | Theo\s+đề\s+nghị | PHỤ\s+LỤC | Phụ\s+lục\s+[IVX\d] | \|
)""", re.X)
_HEAD = re.compile(r"^\s*(?:Điều\s+\d+[a-zđ]?\s*[\.:\-–]|Chương\s+[IVXLCDM\d]+|CHƯƠNG\s+[IVXLCDM\d]+|Mục\s+\d+|MỤC\s+\d+|Phần\s+thứ|PHẦN\s+THỨ)")
_TERM = re.compile(r"[\.:;!?…]\s*[”\"’)]*\s*$")

def _is_caps(s):
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 2 and sum(c.isupper() for c in letters) / len(letters) > 0.85

def unwrap_lines(text):
    """Re-join hard-wrapped lines into paragraphs while keeping structural
    markers (Điều/Chương/Mục/khoản '1.'/điểm 'a)'/bullets) on their own line."""
    lines = [l for l in text.split("\n")]
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if not out:
            out.append(s); continue
        prev = out[-1]
        if MARKER.match(s):
            out.append(s); continue
        first = s[0]
        cont = False
        if first.islower() or first in ",;:.)]}%”’" or (first.isdigit() and not re.match(r"^\d{1,3}[\.\)]\s", s)):
            cont = True
        elif _is_caps(prev) and _is_caps(s) and not _HEAD.match(prev):
            cont = True                      # split all-caps title line
        elif not _TERM.search(prev) and not _HEAD.match(prev) and not _is_caps(prev):
            cont = True                      # mid-sentence capitalised word (proper noun)
        if cont:
            out[-1] = prev + " " + s
        else:
            out.append(s)
    return "\n".join(out)

# ------------------------------------------------------ numbers and dates
_NUM_CORE = r"(\d{1,5}[a-zA-Z]?\s*/\s*(?:\d{4}\s*/\s*)?[A-ZĐa-zđ][A-ZĐa-zđ0-9\-\.]*(?:\s*/\s*[A-ZĐa-zđ0-9\-]+)?|\d{1,5}\s*-\s*[A-ZĐ][A-ZĐa-zđ0-9\-/]*)"
HEADER_NUM = re.compile(r"(?:^|[\s|>])(?:(?:Bộ\s+luật|Luật|Pháp\s+lệnh|Lệnh|Nghị\s+quyết)\s+)?[Ss]ố\s*(?:hiệu)?\s*[:：]\s*" + _NUM_CORE)
DOCNUM_ANY = re.compile(r"(?<![\w/])(\d{1,5}[a-z]?/\d{4}/[A-ZĐ][A-ZĐ0-9]*(?:-[A-ZĐ0-9]+)*)(?![\w])")
DOCNUM_NOYEAR = re.compile(r"(?<![\w/])(\d{1,5}/[A-ZĐ][A-ZĐ0-9]*-[A-ZĐ0-9]+(?:-[A-ZĐ0-9]+)*)(?![\w/])")

def norm_docnum(s):
    """Display form: no spaces, upper-case code, keep Đ. e.g. '112 /NQ-CP' -> '112/NQ-CP'."""
    if not s:
        return None
    s = nfc(s)
    s = re.sub(r"\s+", "", s).strip(".-/,;").replace("Ð", "Đ")
    return s

def docnum_key(s):
    """Lookup key: Đ->D, ASCII upper-case, separators inside the issuer code
    unified to '-' ('117/2007/TTLT/BTC-BLĐTBXH' == '117/2007/TTLT-BTC-BLĐTBXH')."""
    s = norm_docnum(s)
    if not s:
        return None
    s = strip_diacritics(s).upper().replace("&", "")
    m = re.match(r"^(\d{1,5}[A-Z]?)/(\d{4})/(.+)$", s)
    if m:
        return f"{int(re.sub(r'[A-Z]', '', m.group(1)) or 0)}{re.sub(r'[0-9]', '', m.group(1))}/{m.group(2)}/" + re.sub(r"[/_.]", "-", m.group(3))
    m = re.match(r"^(\d{1,5})[/-](.+)$", s)
    if m:
        return f"{int(m.group(1))}/" + re.sub(r"[/_.]", "-", m.group(2))
    return s

def has_year_format(num):
    return bool(num and re.match(r"^\d{1,5}[a-zA-Z]?/\d{4}/", num))

DATE_VN = re.compile(r"ngày\s*(\d\s?\d?)\s*tháng\s*(\d\s?\d?)\s*năm\s*(\d\s?\d\s?\d\s?\d)")
DATE_DMY = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})")

def mkdate(d, m, y):
    try:
        d, m, y = int(re.sub(r"\s", "", str(d))), int(re.sub(r"\s", "", str(m))), int(re.sub(r"\s", "", str(y)))
        if 1900 <= y <= 2100:
            return date(y, m, d).isoformat()
    except Exception:
        return None
    return None

def parse_dmy(s):
    """'01/01/2021' -> '2021-01-01'"""
    if not s:
        return None
    m = DATE_DMY.search(s)
    return mkdate(*m.groups()) if m else None

# ------------------------------------------------------------ header parsing
DOC_TYPE_CAPS = {
    "Hiến pháp": "HIẾN PHÁP", "Bộ luật": "BỘ LUẬT", "Luật": "LUẬT", "Pháp lệnh": "PHÁP LỆNH",
    "Nghị quyết": "NGHỊ QUYẾT", "Nghị quyết liên tịch": "NGHỊ QUYẾT LIÊN TỊCH", "Nghị định": "NGHỊ ĐỊNH",
    "Thông tư": "THÔNG TƯ", "Thông tư liên tịch": "THÔNG TƯ LIÊN TỊCH", "Quyết định": "QUYẾT ĐỊNH",
    "Chỉ thị": "CHỈ THỊ", "Lệnh": "LỆNH", "Văn bản hợp nhất": "VĂN BẢN HỢP NHẤT",
}
_STOP_LINE = re.compile(r"^(?:Căn\s+cứ|Xét\s|Theo\s+đề\s+nghị|Để\s|Thực\s+hiện|Trong\s|Nhằm|Ngày\s|Chương\s+[IVX1]|CHƯƠNG\s+[IVX1]|Điều\s+1\b|Phần\s+thứ|PHẦN\s+THỨ|Mục\s+1\b|I\.\s|1\.\s|[\(\[]?Ban\s+hành\s+kèm)")
_ISSUER_LINE = re.compile(r"^(?:QUỐC\s+HỘI|CHÍNH\s+PHỦ|THỦ\s+TƯỚNG|BỘ\s+TRƯỞNG|CHỦ\s+TỊCH|ỦY\s+BAN|UỶ\s+BAN|HỘI\s+ĐỒNG|CHÁNH\s+ÁN|VIỆN\s+TRƯỞNG|TỔNG\s+KIỂM\s+TOÁN|THỐNG\s+ĐỐC|TỔNG\s+CỤC\s+TRƯỞNG|CỤC\s+TRƯỞNG|BỘ\s+TÀI|BỘ\s+[A-ZĐ]|TỔNG\s+GIÁM\s+ĐỐC|GIÁM\s+ĐỐC|TỔNG\s+THƯ\s+KÝ|CỦA\s+QUỐC\s+HỘI|CỦA\s+CHÍNH\s+PHỦ|BAN\s+CHẤP\s+HÀNH|ĐOÀN\s+CHỦ\s+TỊCH|TÒA\s+ÁN|VIỆN\s+KIỂM\s+SÁT|KIỂM\s+TOÁN)")
_PROPER = [("việt nam", "Việt Nam"), ("quốc hội", "Quốc hội"), ("chính phủ", "Chính phủ"), ("thủ tướng", "Thủ tướng"),
           ("hà nội", "Hà Nội"), ("thành phố hồ chí minh", "Thành phố Hồ Chí Minh"), ("nhà nước", "Nhà nước"),
           ("ngân hàng nhà nước", "Ngân hàng Nhà nước"), ("ủy ban thường vụ quốc hội", "Ủy ban Thường vụ Quốc hội"),
           ("tòa án nhân dân tối cao", "Tòa án nhân dân tối cao"), ("bộ luật", "Bộ luật")]

def sentence_case(s):
    s = s.strip(" .;:-–")
    if _is_caps(s):
        s = s.lower()
        for a, b in _PROPER:
            s = s.replace(a, b)
        # capitalise cited law names: 'của luật sở hữu trí tuệ' -> 'của Luật Sở hữu trí tuệ'
        s = re.sub(r"(?:(?<=của )|(?<=^))(bộ luật|Bộ luật|luật|pháp lệnh)\s+(\w)",
                   lambda m: {"bộ luật": "Bộ luật", "luật": "Luật", "pháp lệnh": "Pháp lệnh"}[m.group(1).lower()] + " " + m.group(2).upper(), s)
    return s

def parse_header(text, doc_type):
    """Return dict(doc_number, issue_date, title_core, title_raw, header_end)."""
    head = text[:6000]
    out = {"doc_number": None, "issue_date": None, "title_core": None, "title_raw": None}
    flat = " ".join(head[:2500].split())
    # PDF-extraction artefacts in the number line: 'S ố: 19/2026/NĐ-CP', 'Số: 1 56 /2018/NĐ-CP'
    flat = re.sub(r"\bS ố\b", "Số", flat)
    flat = re.sub(r"(Số\s*(?:hiệu)?\s*[:：]\s*)(\d(?:\s?\d){0,4})(?=\s*/)", lambda x: x.group(1) + x.group(2).replace(" ", ""), flat)
    m = HEADER_NUM.search(flat)
    if m:
        out["doc_number"] = norm_docnum(m.group(1))
    md = DATE_VN.search(flat)
    if md:
        out["issue_date"] = mkdate(*md.groups())
    caps = DOC_TYPE_CAPS.get(doc_type)
    lines = [l.strip() for l in head.split("\n") if l.strip()]
    start = None
    if caps:
        for i, l in enumerate(lines[:60]):
            ll = " ".join(l.split())
            if ll == caps or ll.startswith(caps + " ") or ll == caps + ":":
                # skip the 'QUYẾT ĐỊNH:' enacting line and the motto
                if ll.endswith(":"):
                    continue
                start = i
                rest = ll[len(caps):].strip()
                break
    if start is not None:
        parts = [rest] if rest else []
        for l in lines[start + 1:start + 12]:
            ll = " ".join(l.split())
            joined = " ".join(parts)
            if _STOP_LINE.match(ll) or (_ISSUER_LINE.match(ll) and _is_caps(ll) and parts and not re.search(r"(?i)(\bcủa|\bvề)$", joined)):
                break
            if ll.endswith(":") and _is_caps(ll):
                break
            if parts and _is_caps(" ".join(parts)) and not _is_caps(ll):
                break                        # descriptive mixed-case line after an all-caps title
            parts.append(ll)
            if sum(len(p) for p in parts) > 600:
                break
        raw = " ".join(parts).strip()
        raw = re.sub(r"\s*-{3,}\s*$", "", raw)
        if raw:
            raw, _ = repair_split_syllables(raw)
            out["title_raw"] = raw
            core = sentence_case(raw)
            # old-style header 'của <issuer> số <num> ngày <date> <subject>' -> '<subject>'
            core = re.sub(r"(?i)^của\s+.{0,200}?\s+số\s*:?\s*\S+(?:\s+ngày\s+\d{1,2}\s*(?:tháng|/|-)\s*\d{1,2}\s*(?:năm|/|-)\s*\d{4})?\s*,?\s*", "", core)
            core = re.sub(r"(?i)^(?:của\s+[^,]{0,120}?)\s*$", "", core).strip()
            out["title_core"] = core or None
    return out

def make_title(doc_type, doc_number, core):
    if not core:
        return f"{doc_type} {doc_number}" if doc_number else doc_type
    if doc_type in ("Luật", "Bộ luật", "Pháp lệnh", "Hiến pháp"):
        c = core if re.match(r"(?i)(sửa đổi|bổ sung|về |quy định)", core) else core[0].upper() + core[1:]
        if doc_type == "Hiến pháp":
            return f"Hiến pháp {c}".strip() if not c.lower().startswith("nước") else f"Hiến pháp {c}"
        return f"{doc_type} {c}"
    c = core[0].lower() + core[1:] if not core[:2].isupper() else core
    return f"{doc_type} {doc_number} {c}" if doc_number else f"{doc_type} {c}"

# ------------------------------------------------------------ status values
def norm_status(s):
    """Map the free-text status to (code, date). Codes: in_force, expired,
    partially_expired, not_yet_effective, not_applicable, unknown."""
    if not s:
        return None, None
    s = nfc(s).strip()
    d = parse_dmy(s)
    low = s.lower()
    if low.startswith("hết hiệu lực một phần"):
        return "partially_expired", d
    if low.startswith("hết hiệu lực"):
        return "expired", d
    if low.startswith("còn hiệu lực đến"):
        return "in_force_until", d
    if low.startswith("còn hiệu lực"):
        return "in_force", None
    if low.startswith("chưa có hiệu lực"):
        return "not_yet_effective", d
    if low.startswith("không còn phù hợp"):
        return "not_applicable", None
    return "unknown", None

# --------------------------------------------------------- effective date
EFF_RE = re.compile(r"(?:có|có\s+hiệu\s+lực)?\s*hiệu\s+lực(?:\s+thi\s+hành)?(?:\s+chính\s+thức)?\s*(?:kể\s+)?(?:từ|từ\s+ngày|kể\s+từ\s+ngày|từ\s+ngày)\s*(?:ngày\s*)?(\d{1,2})\s*(?:tháng|/|-)\s*(\d{1,2})\s*(?:năm|/|-)\s*(\d{4})")
EFF_SIGN = re.compile(r"hiệu\s+lực(?:\s+thi\s+hành)?\s+(?:kể\s+)?từ\s+ngày\s+(?:ký|ban\s+hành|thông\s+qua)")
EFF_AFTER = re.compile(r"hiệu\s+lực(?:\s+thi\s+hành)?\s+(?:sau|kể\s+từ\s+sau)\s+(\d{1,3})\s+ngày\s*,?\s*kể\s+từ\s+ngày\s+(?:ký|ban\s+hành)")

def extract_effective(text, issue_date=None):
    """Effective date stated in the text (first 'có hiệu lực ... từ ngày d tháng m năm y')."""
    flat = " ".join(text.split())
    m = EFF_RE.search(flat)
    if m:
        d = mkdate(*m.groups())
        if d:
            return d, "text_date"
    if issue_date:
        m = EFF_AFTER.search(flat)
        if m:
            try:
                return (date.fromisoformat(issue_date) + timedelta(days=int(m.group(1)))).isoformat(), "text_after_days"
            except Exception:
                pass
        if EFF_SIGN.search(flat):
            return issue_date, "text_on_signing"
    return None, None

# ---------------------------------------------------------------- tokenizer
_TOK = re.compile(r"[^\W_]+(?:[\./\-][^\W_]+)*", re.U)

def vi_tokens(s, bigrams=False):
    """Syllable tokenizer for BM25: NFC, new-style tones, lowercase; keeps doc
    numbers like 45/2019/qh14 as one token; optional adjacent-syllable bigrams."""
    s = tone_new_style(nfc(s or "")).lower()
    toks = _TOK.findall(s)
    if bigrams and len(toks) > 1:
        return toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
    return toks
