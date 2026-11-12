"""Resolve document numbers, law names and article numbers to in-scope VLOnto documents and articles.

The name resolver follows eval_retrieval.py of the vn-legal data track (the resolver used for the hdpl gold
labels): names are compared diacritic-insensitively (vnlegal_text.name_key) with the title core of in-scope
codes, laws, ordinances and constitutions; with a year, the version issued (or else effective) in that year is
taken; without a year, the latest version issued and effective on or before the citing date.
"""
import re
from collections import defaultdict

from . import vnlegal_text as VT

NAME_TYPES = ("Bộ luật", "Luật", "Pháp lệnh", "Hiến pháp")
AMEND_RE = re.compile(r"(?i)^(sửa đổi|bổ sung|về |quy định)")
LAWTYPE_RE = re.compile(r"(Bộ luật|Hiến pháp|Pháp lệnh|Luật|Nghị định|Thông tư liên tịch|Thông tư|Nghị quyết liên tịch|Nghị quyết|Quyết định)\b")
NAME_STOP = re.compile(r"\s+(?:ngày|số|đã được|được sửa|được|tại|theo|quy định|hướng dẫn|và các|và khoản|và điều)\b.*$|\s*[\(\[;:].*$", re.I)
YEAR_RE = re.compile(r"(?:năm\s+)?\b((?:19|20)\d{2})\b")
ARTICLE_RE = re.compile(r"^0*(\d{1,4})([a-zđ]?)$")
POINT_RE = re.compile(r"^[a-zđ]$")


def norm_article(a):
    if a is None:
        return None
    a = str(a).strip().lower().replace(" ", "")
    m = ARTICLE_RE.match(a)
    if not m or m.group(1) == "":
        return None
    n = int(m.group(1))
    if n == 0:
        return None
    return f"{n}{m.group(2)}"


def norm_clause(c):
    if c is None:
        return None
    c = str(c).strip().lower()
    m = re.match(r"^0*(\d{1,3})([a-zđ]?)$", c)
    if not m or int(m.group(1)) == 0:
        return None
    return f"{int(m.group(1))}{m.group(2)}"


def norm_point(p):
    if p is None:
        return None
    p = str(p).strip().lower().rstrip(")")
    return p if POINT_RE.match(p) else None


def date_of(r):
    return r.get("effective_date") or r.get("issue_date")


class DocResolver:
    def __init__(self, docs_rows):
        """docs_rows: iterable of dicts with doc_id, doc_type, doc_number, doc_number_key, title_core, issue_date, effective_date."""
        self.by_key = defaultdict(list)
        self.name_index = defaultdict(list)
        self.docs = {}
        for r in docs_rows:
            self.docs[r["doc_id"]] = r
            if r.get("doc_number_key"):
                self.by_key[r["doc_number_key"]].append(r)
            if r["doc_type"] in NAME_TYPES and r.get("title_core") and not AMEND_RE.match(r["title_core"]):
                self.name_index[(r["doc_type"], VT.name_key(r["title_core"]))].append(r)
        for v in self.by_key.values():
            v.sort(key=lambda r: (r.get("issue_date") or "", r["doc_id"]))
        self.names_by_type = defaultdict(list)
        for (t, k) in self.name_index:
            self.names_by_type[t].append(k)
        self._cache_num = {}
        self._cache_name = {}

    # ------------------------------------------------------------ numbers
    def by_number(self, number, type_hint=None, at=None):
        """-> (doc_id or None, method or reason)."""
        if not number:
            return None, "no_number"
        key = VT.docnum_key(number)
        ck = (key, type_hint, at)
        if ck in self._cache_num:
            return self._cache_num[ck]
        cands = self.by_key.get(key, [])
        res = (None, "number_not_in_scope")
        if cands:
            c = cands
            if type_hint:
                ct = [r for r in c if r["doc_type"] == type_hint]
                c = ct or c
            signed = (at[0] or at[1]) if isinstance(at, tuple) else at
            if len(c) > 1 and signed:
                cb = [r for r in c if (r.get("issue_date") or "") <= signed]
                c = cb or c
            res = (c[-1]["doc_id"], "docnum-key")
        self._cache_num[ck] = res
        return res

    # ------------------------------------------------------------ names
    @staticmethod
    def pick_version(cands, year=None, pub=None):
        if year:
            c = [r for r in cands if r.get("issue_date") and r["issue_date"][:4] == str(year)]
            if c:
                return c[0], "year"
            c = [r for r in cands if r.get("effective_date") and r["effective_date"][:4] == str(year)]
            if c:
                return c[0], "year_effective"
            return None, None
        # pub: date string, or (signed, in_force_at): versions issued before the citing act was signed and in force
        # when it takes effect
        signed, inforce = pub if isinstance(pub, tuple) else (pub, pub)
        signed, inforce = signed or inforce, inforce or signed
        if signed:
            c = [r for r in cands if r.get("issue_date") and r["issue_date"] <= signed]
            c2 = [r for r in c if (r.get("effective_date") or r["issue_date"]) <= inforce]
            c = c2 or c
            if c:
                return max(c, key=lambda r: (r.get("effective_date") or r["issue_date"])), "in_force_at_date"
        if len(cands) == 1:
            return cands[0], "only_version"
        return None, None

    def by_name(self, doc_type, name, year=None, at=None):
        if doc_type not in NAME_TYPES or not name:
            return None, "type_not_resolvable_by_name"
        nk = VT.name_key(name)
        if len(nk) < 2:
            return None, "name_too_short"
        ck = (doc_type, nk, year, at)
        if ck in self._cache_name:
            return self._cache_name[ck]
        cands = self.name_index.get((doc_type, nk))
        how = "name"
        if not cands and len(nk) >= 4:
            pref = [k for k in self.names_by_type[doc_type] if k.startswith(nk)]
            if len(set(pref)) == 1:
                cands = self.name_index[(doc_type, pref[0])]
                how = "name_prefix"
        res = (None, "name_not_found")
        if cands:
            r, v = self.pick_version(cands, year, at)
            res = (r["doc_id"], "law-name-year") if r else (None, "no_version_for_date")
        self._cache_name[ck] = res
        return res

    # ------------------------------------------------------------ free-text references
    def parse_reference(self, text):
        """'Luật An toàn vệ sinh lao động', 'Điều 38 của Luật Luật sư', 'Bộ luật Dân sự năm 2015' ->
        (type, name, year, number)."""
        if not text:
            return None, None, None, None
        t = " ".join(VT.nfc(text).split())
        num = None
        m = VT.DOCNUM_ANY.search(t)
        if m:
            num = m.group(1)
        mt = None
        for mm in LAWTYPE_RE.finditer(t):
            mt = mm
            break
        if mt is None:
            return None, None, None, num
        typ = mt.group(1)
        rest = t[mt.end():].strip()
        rest = re.sub(r"^(?:số\s+)?", "", rest)
        ym = YEAR_RE.search(rest)
        year = int(ym.group(1)) if ym else None
        name = NAME_STOP.sub("", rest)
        name = re.sub(r"\s*(?:năm\s+)?(?:19|20)\d{2}\s*$", "", name).strip(" ,.;-")
        if typ in ("Luật", "Bộ luật") and name.lower().startswith(("luật ", "bộ luật ")) and not name.lower().startswith("luật sư"):
            name = re.sub(r"^(?:bộ\s+)?luật\s+", "", name, flags=re.I)
        return typ, name, year, num

    def resolve_reference(self, text, at=None, type_hint=None):
        """Number first, then type + name (+year). -> (doc_id, method, parsed)."""
        typ, name, year, num = self.parse_reference(text)
        if num:
            d, how = self.by_number(num, type_hint or typ, at)
            if d:
                return d, how, (typ, name, year, num)
        if typ in NAME_TYPES and name:
            d, how = self.by_name(typ, name, year, at)
            if d:
                return d, how, (typ, name, year, num)
            return None, how, (typ, name, year, num)
        return None, ("number_not_in_scope" if num else "no_law_reference"), (typ, name, year, num)
