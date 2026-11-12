"""Canonical names for the courts that issued the court decisions (cbba, anle).

Raw names come from the source's court field or from the decision header. They contain OCR errors,
legacy-font artefacts ('Sè' for 'Số'), anonymised initials ('huyện Gl', 'huyện Ht tỉnh Tn') and trailing
text ('… Số 15/2021/QĐST-HNGĐ'). parse_court() maps a raw name to a canonical court:

    kind      supreme | high | military | provincial | district | regional
    unit      TỈNH / THÀNH PHỐ (provincial) or HUYỆN / QUẬN / THỊ XÃ / THÀNH PHỐ (district level) or KHU VỰC
    name      unit name as written (upper case, tone marks normalised); None for supreme/high/provincial
    name_key  diacritic- and space-insensitive form of the name (merges 'Đông Tri ều' and 'Đông Triều')
    province  canonical province or centrally run city (None when the text does not state it)

or a reason string ('masked', 'unparsed', 'no-court-prefix') when the name cannot be used. Province-less
district names are resolved later against the names seen with a province (see build_courts).
"""
import re
import unicodedata

from .config import slugify, strip_diacritics

CENTRAL = ["HÀ NỘI", "HỒ CHÍ MINH", "HẢI PHÒNG", "ĐÀ NẴNG", "CẦN THƠ", "HUẾ"]
PROVINCES = [
    "AN GIANG", "BÀ RỊA VŨNG TÀU", "BẮC GIANG", "BẮC KẠN", "BẠC LIÊU", "BẮC NINH", "BẾN TRE", "BÌNH ĐỊNH", "BÌNH DƯƠNG",
    "BÌNH PHƯỚC", "BÌNH THUẬN", "CÀ MAU", "CAO BẰNG", "ĐẮK LẮK", "ĐẮK NÔNG", "ĐIỆN BIÊN", "ĐỒNG NAI", "ĐỒNG THÁP",
    "GIA LAI", "HÀ GIANG", "HÀ NAM", "HÀ TĨNH", "HẢI DƯƠNG", "HẬU GIANG", "HÒA BÌNH", "HƯNG YÊN", "KHÁNH HÒA",
    "KIÊN GIANG", "KON TUM", "LAI CHÂU", "LÂM ĐỒNG", "LẠNG SƠN", "LÀO CAI", "LONG AN", "NAM ĐỊNH", "NGHỆ AN",
    "NINH BÌNH", "NINH THUẬN", "PHÚ THỌ", "PHÚ YÊN", "QUẢNG BÌNH", "QUẢNG NAM", "QUẢNG NGÃI", "QUẢNG NINH",
    "QUẢNG TRỊ", "SÓC TRĂNG", "SƠN LA", "TÂY NINH", "THÁI BÌNH", "THÁI NGUYÊN", "THANH HÓA", "THỪA THIÊN HUẾ",
    "TIỀN GIANG", "TRÀ VINH", "TUYÊN QUANG", "VĨNH LONG", "VĨNH PHÚC", "YÊN BÁI"]
VARIANTS = {
    "HCM": "HỒ CHÍ MINH", "TPHCM": "HỒ CHÍ MINH", "HỒ CHÍ MINH": "HỒ CHÍ MINH", "HỒ CHÍ": "HỒ CHÍ MINH",
    "ĐẮC LẮC": "ĐẮK LẮK", "ĐẮK LẮC": "ĐẮK LẮK", "ĐẮC LẮK": "ĐẮK LẮK", "ĐĂK LĂK": "ĐẮK LẮK", "ĐĂK LẮK": "ĐẮK LẮK",
    "ĐẮK LĂK": "ĐẮK LẮK", "ĐĂKLĂK": "ĐẮK LẮK", "ĐẮKLẮK": "ĐẮK LẮK", "ĐẮCLẮC": "ĐẮK LẮK",
    "ĐĂK NÔNG": "ĐẮK NÔNG", "ĐẮC NÔNG": "ĐẮK NÔNG", "ĐĂKNÔNG": "ĐẮK NÔNG", "ĐẮKNÔNG": "ĐẮK NÔNG",
    "BẮC CẠN": "BẮC KẠN", "KONTUM": "KON TUM", "LAICHÂU": "LAI CHÂU"}
PROVINCE_DISPLAY = {"BÀ RỊA VŨNG TÀU": "Bà Rịa - Vũng Tàu", "HỒ CHÍ MINH": "Hồ Chí Minh"}
NAME_DISPLAY = {"PHAN RANG THÁP CHÀM": "Phan Rang - Tháp Chàm"}
HIGH_CITIES = {"HÀ NỘI": "Hà Nội", "ĐÀ NẴNG": "Đà Nẵng", "HỒ CHÍ MINH": "Thành phố Hồ Chí Minh"}

_PROV_INDEX = {}
for _p in PROVINCES + CENTRAL:
    _PROV_INDEX[tuple(_p.split())] = _p
for _v, _p in VARIANTS.items():
    _PROV_INDEX[tuple(_v.split())] = _p

UNITS = [("THÀNH", "PHỐ"), ("THỊ", "XÃ"), ("KHU", "VỰC"), ("HUYỆN",), ("QUẬN",), ("TỈNH",)]
# words that end a unit name (only checked after the first name token)
STOP = {"SỐ", "SÈ", "SOÁ", "VỚI", "XÉT", "BẢN", "BÁN", "TẠI", "TIẾN", "VÀ", "NGƯỜI", "TRONG", "TÒA", "THEO", "VỀ", "GỒM", "NGÀY",
        "QUYẾT", "CỘNG", "ĐỘC", "ĐỘ", "CĂN", "PHIÊN", "KÍNH", "THỤ", "ĐÃ", "LÀ", "CỦA", "ĐƯỢC", "BỊ", "CHỦ", "TỈ", "TỈN", "NHẬN",
        "ĐẠI", "MỞ", "GHI", "NHƯNG", "CHẤP", "DIỆN", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII"}
# words that end a unit name only before a given next word ('VŨ THƯ' is a district, 'THƯ KÝ' is the court clerk)
STOP_IF_NEXT = {"THƯ": {"KÝ"}}
# a one-word unit name is almost always an anonymised or truncated one ('HUYỆN TY', 'HUYỆN BÌNH Đ'); these are real
SINGLE_WORD_UNITS = {"VINH", "HUẾ", "PLEIKU", "KBANG", "LẮK", "LĂK", "ĐAKRÔNG", "SAPA", "CƯMGAR", "MĐRẮK", "MĐRĂK"}
# words that may follow an abbreviated last syllable of an anonymised name ('HUYỆN CHÂU TH TỈNH KIÊN GIANG')
MASK_FOLLOW = {"TỈNH", "THÀNH", "TP", "ĐỘC", "CĂN", "CỘNG", "SỐ", "SÈ"}

_TONE = {"OÀ": "ÒA", "OÁ": "ÓA", "OẢ": "ỎA", "OÃ": "ÕA", "OẠ": "ỌA", "OÈ": "ÒE", "OÉ": "ÓE", "OẺ": "ỎE", "OẼ": "ÕE",
         "OẸ": "ỌE", "UỲ": "ÙY", "UÝ": "ÚY", "UỶ": "ỦY", "UỸ": "ŨY", "UỴ": "ỤY"}
_LETTER = "A-ZĐÀ-ỸƠƯ"
_TONE_RE = re.compile(r"(?<!Q)(" + "|".join(_TONE) + r")(?![" + _LETTER + "])")
_SYL = re.compile(r"^(?:[BCDFGHJKLMNPQRSTVWXZ]*[AEIOUY]+(?:NG|NH|CH|[CMNPTKRLH])?)+$")   # final H: Chư Păh, Chư Pưh
_PREFIX = re.compile(r"T[ÒO]A ÁN (?:NHÂN DÂN|QUÂN SỰ)|\bTAND\b|\bTAQS\b")
# national motto printed in the two-column header; flattened text puts it between 'TÒA ÁN NHÂN DÂN' and the unit
_MOTTO = re.compile(r"C\s*[ỘÔO]\s*N\s*G\s*H\s*[ÒÕÓOỌỎ]\s*[AÀ]\s*X\s*Ã\s*H\s*Ộ\s*I\s*C\s*H\s*Ủ\s*N\s*G?\s*H\s*Ĩ\s*A\s*V\s*I\s*Ệ\s*T\s*N\s*A\s*M"
                    r"|Đ\s*Ộ\s*C\s*L\s*Ậ\s*P\s*T\s*Ự\s*D\s*O\s*H\s*Ạ\s*N\s*H\s*P\s*H\s*Ú\s*C")
_UNIT_FIX = [(re.compile(r"\bHUY\s+ỆN\b|\bHYỆN\b"), "HUYỆN"), (re.compile(r"\bTỈ\s+NH\b"), "TỈNH"), (re.compile(r"\bQU\s+ẬN\b"), "QUẬN"),
             (re.compile(r"\bT\s+X\b"), "THỊ XÃ")]


def clean(s):
    """NFC, upper case, new-style tone marks, legacy 'ƣ', abbreviations, punctuation to spaces."""
    s = unicodedata.normalize("NFC", s or "").replace("ƣ", "ư").replace("Ƣ", "Ư").upper()
    s = _TONE_RE.sub(lambda m: _TONE[m.group(1)], s)
    s = _MOTTO.sub(" ", s)
    s = re.sub(r"\bTP\.?\s*HCM\b|\bTPHCM\b", "THÀNH PHỐ HỒ CHÍ MINH ", s)
    s = re.sub(r"\bTPHỐ\b", "THÀNH PHỐ ", s)
    s = re.sub(r"\bTP\b\.?", "THÀNH PHỐ ", s)
    s = re.sub(r"\bTHNH PHỐ\b|\bTHANH PHỐ\b|\bTHÀNH PHÔ\b", "THÀNH PHỐ", s)
    s = re.sub(r"(?<=[" + _LETTER + r"0-9])(THÀNH PHỐ)", r" \1", s)
    s = re.sub(r"\b(TỈNH|HUYỆN|QUẬN)(?=[" + _LETTER + r"])", r"\1 ", s)
    s = re.sub(r"[’`´]", "’", s).replace("'", "’")
    s = re.sub(r"[^\w’]+", " ", s)      # punctuation, dashes, underscores (kept: letters, digits, apostrophe)
    s = s.replace("_", " ")
    for rx, rep in _UNIT_FIX:
        s = rx.sub(rep, s)
    return " ".join(_join_split(s.split()))


def _is_vowel_start(t):
    return bool(t) and strip_diacritics(t[0]).upper() in "AEIOUY"


def _join_split(toks):
    """Re-join syllables split by PDF extraction before a vowel: 'C ẨM' -> 'CẨM', 'PH Ố' -> 'PHỐ', 'QU ẢNG' -> 'QUẢNG'."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if (i + 1 < len(toks) and t.isalpha() and len(t) <= 3 and _is_vowel_start(toks[i + 1])
                and (t == "QU" or not any(strip_diacritics(ch).upper() in "AEIOUY" for ch in t))
                and _syllable_ok(t + toks[i + 1])):
            out.append(t + toks[i + 1])
            i += 2
            continue
        out.append(t)
        i += 1
    return out


def _syllable_ok(t):
    a = strip_diacritics(t).upper().replace("’", "")
    if not a or not a.isalpha() or not _SYL.match(a):
        return False
    if re.search(r"Q(?!U)", a) or re.match(r"^Y[^AEIOU]", a):
        return False
    return True


def _unit_at(toks, i):
    for u in UNITS:
        if tuple(toks[i:i + len(u)]) == u:
            return " ".join(u), i + len(u)
    return None, i


def _province_at(toks, i, min_len=1):
    for n in (4, 3, 2, 1):
        if n < min_len:
            break
        t = tuple(toks[i:i + n])
        if len(t) < n:
            continue
        p = _PROV_INDEX.get(t)
        if p:
            return p, i + n
    return None, i


def _province_after(toks, i):
    """Optional 'TỈNH'/'THÀNH PHỐ' then a province name."""
    u, j = _unit_at(toks, i)
    if u in ("TỈNH", "THÀNH PHỐ"):
        p, k = _province_at(toks, j)
        return (p, k) if p else (None, i)
    return _province_at(toks, i)


def _name(toks, i, allow_number):
    if i < len(toks) and toks[i] in ("HUYỆN", "QUẬN"):      # 'HUYỆN HUYỆN YÊN THÀNH'
        i += 1
    name, k = [], i
    while k < len(toks) and len(name) < 5:
        t = toks[k]
        stop = (k + 1 < len(toks) and toks[k + 1] in STOP_IF_NEXT[t]) if t in STOP_IF_NEXT else t in STOP
        if name and (_unit_at(toks, k)[0] or stop or _province_at(toks, k, min_len=2)[0]):
            break
        if t.isdigit():
            if allow_number and not name:
                name.append(t)
                k += 1
                break
            break
        if not _syllable_ok(t):
            if not name:   # first name token is not a Vietnamese syllable: anonymised initials or garbage
                return None, k, ("masked" if len(strip_diacritics(t).replace("’", "")) <= 4 else "unparsed")
            nxt = toks[k + 1] if k + 1 < len(toks) else None
            if len(strip_diacritics(t)) <= 2 and t != "V" and (nxt is None or nxt in MASK_FOLLOW or _province_at(toks, k + 1)[0]):
                return None, k, "masked"   # last syllable cut to its initial by the anonymisation: 'HUYỆN BÌNH Đ - TỈNH BẾN TRE'
            break          # garbage after a complete name ends the name
        name.append(t)
        k += 1
    if not name:
        return None, k, "unparsed"
    if len(name) > 4:
        return None, k, "unparsed"
    if len(name) == 1 and len(name[0]) == 1 and name[0].isalpha():      # 'HUYỆN Y', 'THÀNH PHỐ H' (not 'QUẬN 4')
        return None, k, "masked"
    if len(name) == 1 and not name[0].isdigit() and "’" not in name[0] and name[0].replace("’", "") not in SINGLE_WORD_UNITS:
        return None, k, "masked"   # 'HUYỆN TY' (Trấn Yên), 'THÀNH PHỐ VY' (Vĩnh Yên), 'HUYỆN TÂN S' -> 'TÂN'
    return name, k, None


def _parse_segment(seg):
    toks = seg.split()
    if not toks:
        return "unparsed"
    abbr = {"Q": ["QUẬN"], "H": ["HUYỆN"], "TX": ["THỊ", "XÃ"]}
    if toks[0] in abbr:       # 'TAND Q. Tân Bình', 'TAND TX. Sơn Tây' (right after the court prefix only)
        toks = abbr[toks[0]] + toks[1:]
    if toks[:2] == ["QUÂN", "SỰ"]:
        out = []
        for j, t in enumerate(toks[2:9], start=2):
            if t in STOP or t == "TÒA" or (t in STOP_IF_NEXT and toks[j + 1:j + 2] and toks[j + 1] in STOP_IF_NEXT[t]) \
                    or not (t.isdigit() or _syllable_ok(t)):
                break
            out.append(t)
        if not out:
            return "unparsed"
        return {"kind": "military", "unit": None, "name": " ".join(out), "name_key": slugify(" ".join(out)), "province": None}
    if toks[:2] == ["TỐI", "CAO"]:
        return {"kind": "supreme", "unit": None, "name": None, "name_key": None, "province": None, "tail": len(toks) - 2}
    if toks[:2] == ["CẤP", "CAO"]:
        j = 3 if toks[2:3] == ["TẠI"] else 2
        p, _ = _province_after(toks, j)
        if p in HIGH_CITIES:
            return {"kind": "high", "unit": None, "name": None, "name_key": None, "province": p}
        return "unparsed"
    unit, i = _unit_at(toks, 0)
    if unit is None:
        return "unparsed"
    if unit == "TỈNH":
        if i < len(toks) and (len(toks[i]) == 1 or (len(toks[i]) <= 3 and not _syllable_ok(toks[i]))):
            return "masked"
        p, j = _province_at(toks, i)
        return {"kind": "provincial", "unit": unit, "name": None, "name_key": None, "province": p, "tail": len(toks) - j} if p else "unparsed"
    if unit == "THÀNH PHỐ":
        p, j = _province_at(toks, i)
        nxt, _ = _unit_at(toks, j)
        if p in CENTRAL and nxt != "TỈNH":
            return {"kind": "provincial", "unit": unit, "name": None, "name_key": None, "province": p, "tail": len(toks) - j}
    if unit == "KHU VỰC":
        if i < len(toks) and toks[i].isdigit():
            p, _ = _province_after(toks, i + 1)
            return {"kind": "regional", "unit": unit, "name": toks[i], "name_key": toks[i], "province": p}
        return "masked" if i < len(toks) and len(toks[i]) <= 3 else "unparsed"
    name, k, why = _name(toks, i, allow_number=(unit == "QUẬN"))
    if why:
        return why
    p, _ = _province_after(toks, k)
    nm = " ".join(name)
    return {"kind": "district", "unit": unit, "name": nm, "name_key": strip_diacritics(nm).replace(" ", "").lower(), "province": p}


def parse_court(raw, prefer="last"):
    """Canonical court description (dict) or a reason string.

    prefer='last' (source court field): a field such as 'Tòa án nhân dân tỉnh X Tòa án nhân dân huyện Y' names the
    superior court first, so the last parsable court is the issuing one. prefer='first' (document header): the
    first court named is the issuing one, except for a two-line header 'TÒA ÁN NHÂN DÂN TỈNH X / TÒA ÁN NHÂN DÂN
    HUYỆN Y' where the provincial name is immediately followed by the district-level court.
    """
    if not raw:
        return "empty"
    s = clean(raw)
    ms = list(_PREFIX.finditer(s))
    if not ms:
        return "no-court-prefix"
    segs = []
    for n, m in enumerate(ms):
        seg = s[m.end():ms[n + 1].start() if n + 1 < len(ms) else len(s)].strip()
        if "QUÂN SỰ" in m.group(0) or m.group(0) == "TAQS":
            seg = ("QUÂN SỰ " + seg).strip()
        segs.append(seg)
    parsed = [_parse_segment(x) if x else "unparsed" for x in segs]
    out = None
    if prefer == "first":
        for n, p in enumerate(parsed):
            if p == "masked":      # an anonymised issuing court: do not fall through to courts named later
                return "masked"
            if isinstance(p, dict):
                q = parsed[n + 1] if n + 1 < len(parsed) else None
                if (p["kind"] == "provincial" and p.get("tail") == 0 and isinstance(q, dict)
                        and q["kind"] in ("district", "regional")):
                    out = dict(q, province=q["province"] or p["province"])
                elif p["kind"] == "supreme" and p.get("tail") == 0 and isinstance(q, dict):
                    out = q          # 'TÒA ÁN NHÂN DÂN TỐI CAO / TÒA ÁN NHÂN DÂN CẤP CAO TẠI …'
                else:
                    out = p
                break
    else:
        for p in reversed(parsed):
            if isinstance(p, dict):
                out = p
                break
        if out is not None and out["kind"] in ("district", "regional") and not out["province"]:
            for p in parsed:
                if isinstance(p, dict) and p["kind"] == "provincial":
                    out = dict(out, province=p["province"])
                    break
    if out is None:
        return "masked" if "masked" in parsed else "unparsed"
    out = dict(out)
    out.pop("tail", None)
    return out


def court_key(c):
    k = c["kind"]
    if k == "supreme":
        return "toi-cao"
    if k == "high":
        return "cap-cao-" + slugify(c["province"])
    if k == "military":
        return "quan-su-" + c["name_key"]
    if k == "provincial":
        return ("thanh-pho-" if c["province"] in CENTRAL else "tinh-") + slugify(c["province"])
    if k == "regional":
        return f"khu-vuc-{c['name']}" + ("-" + slugify(c["province"]) if c["province"] else "")
    base = slugify(c["unit"]) + "-" + c["name_key"]
    return base + ("-" + slugify(c["province"]) if c["province"] else "")


def level_of(c):
    return {"supreme": "Supreme", "high": "High", "military": "Military", "provincial": "Provincial",
            "district": "District", "regional": "District"}[c["kind"]]


def _title(t):
    parts = re.split(r"(’)", t)
    return "".join(p if p == "’" else p[:1].upper() + p[1:].lower() for p in parts)


def province_display(p):
    return PROVINCE_DISPLAY.get(p) or " ".join(_title(t) for t in p.split())


def name_display(n):
    return NAME_DISPLAY.get(n) or " ".join(t if t.isdigit() else _title(t) for t in n.split())


_MIL = {"QUÂN KHU": "Quân khu", "QUÂN CHỦNG": "Quân chủng", "HẢI QUÂN": "Hải quân", "THỦ ĐÔ": "Thủ đô",
        "PHÒNG KHÔNG": "Phòng không", "KHÔNG QUÂN": "Không quân", "BỘ ĐỘI": "Bộ đội", "BIÊN PHÒNG": "Biên phòng"}


def label(c, name_disp=None):
    k = c["kind"]
    if k == "supreme":
        return "Tòa án nhân dân tối cao"
    if k == "high":
        return "Tòa án nhân dân cấp cao tại " + HIGH_CITIES[c["province"]]
    if k == "provincial":
        return ("Tòa án nhân dân thành phố " if c["province"] in CENTRAL else "Tòa án nhân dân tỉnh ") + province_display(c["province"])
    if k == "regional":
        return f"Tòa án nhân dân khu vực {c['name']}" + (" - " + province_display(c["province"]) if c["province"] else "")
    if k == "military":
        s = " ".join(t.lower() for t in c["name"].split())
        for a, b in _MIL.items():
            s = re.sub(r"\b" + a.lower() + r"\b", b, s)
        for p in sorted(PROVINCES + CENTRAL, key=len, reverse=True):
            s = re.sub(r"\b" + p.lower() + r"\b", province_display(p), s)
        return "Tòa án quân sự " + s
    out = "Tòa án nhân dân " + c["unit"].lower() + " " + (name_disp or name_display(c["name"]))
    if c["province"]:
        out += (", thành phố " if c["province"] in CENTRAL else ", tỉnh ") + province_display(c["province"])
    return out


def head(c, name_raw=None):
    """Upper-case phrase that a citation of a decision of this court usually repeats (for case resolution)."""
    k = c["kind"]
    if k == "supreme":
        return "TỐI CAO"
    if k == "high":
        return "CẤP CAO TẠI " + c["province"]
    if k == "provincial":     # 'NHÂN DÂN TỈNH X' so that 'HUYỆN Y TỈNH X' does not match the provincial court
        return "NHÂN DÂN " + c["unit"] + " " + c["province"]
    if k == "military":
        return "QUÂN SỰ " + c["name"]
    if k == "regional":
        return "KHU VỰC " + c["name"] + " " + (c["province"] or "")
    return c["unit"] + " " + (name_raw or c["name"])
