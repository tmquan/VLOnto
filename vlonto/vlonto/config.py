"""Paths, source revisions, release switches, IRI builders and small shared helpers for the VLOnto build.

Release v1 (1.0.0) is built from the four thuvienphapluat.vn datasets (vbpl, hdpl, tnpl, htpl). The court datasets
(anle-toaan-gov-vn, cbba-toaan-gov-vn) are planned for v2: they are read only when the build is run with
VLONTO_INCLUDE_COURTS=1 (or `python -m vlonto.cli ... --with-courts`). The judiciary classes and properties stay in the
ontology either way.
"""
import os
import re
import unicodedata

from . import RELEASE, __version__

VERSION = __version__
# Build date stamped into the outputs (stats, reports, build activity IRI); the ontology's dcterms:modified must equal
# it (checked by `vlonto.cli check-ontology`). Override with VLONTO_BUILD_DATE=YYYY-MM-DD for a later rebuild.
BUILD_DATE = os.environ.get("VLONTO_BUILD_DATE", "2026-11-12")
if not re.match(r"^\d{4}-\d{2}-\d{2}$", BUILD_DATE):
    raise ValueError(f"VLONTO_BUILD_DATE={BUILD_DATE!r}: use YYYY-MM-DD")
# Validity of documents is evaluated as of this date (pipeline/validity.py AS_OF, STATUS_FIRST=1); unchanged since 0.1.0.
VALIDITY_AS_OF = "2026-11-08"
ONTOLOGY_IRI = "https://tmquan.github.io/VLOnto/ontology"
ONTOLOGY_VERSION_IRI = f"{ONTOLOGY_IRI}/{VERSION}"


def _flag(name, default):
    v = os.environ.get(name, default).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off", ""):
        return False
    raise ValueError(f"{name}={v!r}: use 1 or 0")


# Court data switch: OFF for release v1 (court decisions and precedents are planned for v2).
INCLUDE_COURTS = _flag("VLONTO_INCLUDE_COURTS", "0")
COURT_DATASETS = ("anle-toaan-gov-vn", "cbba-toaan-gov-vn")
COURT_TABLES = ("courts", "decisions", "precedents", "edges_decision_provision", "edges_decision_case", "edges_precedent_source")
COURT_CLASSES = ("Court", "CourtDecision", "Judgment", "CourtRuling", "Precedent")

# V = VLOnto root (contains repo/, build/, envs/); default: three levels above this package (<V>/repo/vlonto/vlonto).
# R = processed vn-legal corpus root; default: the sibling directory <V>/../vnlegal.
V = os.environ.get("V", os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
R = os.environ.get("R", os.path.join(os.path.dirname(V), "vnlegal"))
HF_HUB = os.environ.get("HF_HUB", os.path.join(R, "hf", "hub"))
REPO = os.environ.get("VLONTO_REPO", os.path.join(V, "repo"))
BUILD = os.environ.get("VLONTO_BUILD", os.path.join(V, "build"))
KG = os.path.join(BUILD, "kg")
KG_LOCAL = os.path.join(BUILD, "kg_local")
RDF_DIR = os.path.join(BUILD, "rdf")
SITE = os.path.join(BUILD, "site_data")
REPORTS = os.path.join(BUILD, "reports")

SOURCES_ALL = {
    "thuvienphapluat-vn-vbpl": {"revision": "705ade585384108ded5fc30f40a06fe110bdff22", "licence": "cc-by-4.0",
                                "publisher": "thuvienphapluat.vn", "kind": "legal documents"},
    "thuvienphapluat-vn-hdpl": {"revision": "e814ecbfa1a1c0c32727c2f2ad2498d52f04b8bd", "licence": "other",
                                "publisher": "thuvienphapluat.vn", "kind": "legal Q&A"},
    "thuvienphapluat-vn-tnpl": {"revision": "f94d1e24852f233e85330c6d5093f43adbddde29", "licence": "other",
                                "publisher": "thuvienphapluat.vn/tnpl", "kind": "legal terminology"},
    "thuvienphapluat-vn-htpl": {"revision": "043c8f2988e248f1123ead53a54e3cbf83a02e44", "licence": "other",
                                "publisher": "thuvienphapluat.vn", "kind": "legal news"},
    "anle-toaan-gov-vn": {"revision": "d6124923ddcba618811644f433de7c748a291e22", "licence": "cc-by-4.0",
                          "publisher": "anle.toaan.gov.vn", "kind": "court documents and precedents"},
    "cbba-toaan-gov-vn": {"revision": "8ace3afc9c974afd51e12dccbefd4b3ba54ce1ec", "licence": "cc-by-4.0",
                          "publisher": "congbobanan.toaan.gov.vn", "kind": "court judgments and rulings"},
}
for _ds, _s in SOURCES_ALL.items():
    _s["release"] = "2.0.0 (planned)" if _ds in COURT_DATASETS else "1.0.0"
# Sources of this build (v1: the four thuvienphapluat datasets) and the sources deferred to a later release.
SOURCES = {k: v for k, v in SOURCES_ALL.items() if INCLUDE_COURTS or k not in COURT_DATASETS}
DEFERRED_SOURCES = {k: v for k, v in SOURCES_ALL.items() if k not in SOURCES}


def rel(path):
    """A path as written into published text: relative to V (e.g. build/kg/documents.parquet), '$R/...' under the
    corpus root, else the file name. Published outputs never carry absolute build-machine paths."""
    p = os.path.abspath(path)
    v, r = os.path.abspath(V), os.path.abspath(R)
    if p == v:
        return "."
    if p.startswith(v + os.sep):
        return os.path.relpath(p, v)
    if p.startswith(r + os.sep):
        return "$R/" + os.path.relpath(p, r)
    return os.path.basename(p)


def snapshot(dataset):
    if dataset not in SOURCES:
        raise RuntimeError(f"{dataset} is not a source of this build (VLONTO_INCLUDE_COURTS={int(INCLUDE_COURTS)}); "
                           "court data is planned for v2")
    return os.path.join(HF_HUB, f"datasets--tmquan--{dataset}", "snapshots", SOURCES[dataset]["revision"])


def release_info():
    """Release scope recorded in the build report, stats and site data."""
    return {"version": VERSION, "release": RELEASE, "build_date": BUILD_DATE, "validity_as_of": VALIDITY_AS_OF,
            "courts_included": INCLUDE_COURTS, "sources": list(SOURCES),
            "deferred_sources": {k: {"revision": v["revision"], "planned_release": "2.0.0"} for k, v in DEFERRED_SOURCES.items()}}


PROCESSED = {
    "docs_clean": os.path.join(R, "data", "clean", "docs_clean.parquet"),
    "chunks": os.path.join(R, "data", "chunks", "chunks.parquet"),
    "doc_struct": os.path.join(R, "data", "chunks", "doc_struct.parquet"),
    "relations": os.path.join(R, "data", "validity", "relations.parquet"),
    "validity": os.path.join(R, "data", "validity", "validity.parquet"),
    "gold_all": os.path.join(R, "eval", "gold_all.parquet"),
}

# ------------------------------------------------------------------ namespaces and IRIs
VLO = "https://tmquan.github.io/VLOnto/ontology#"
ID = "https://tmquan.github.io/VLOnto/id/"


def iri_doc(doc_id):
    return f"{ID}document/{doc_id}"


def iri_article(article_id):
    """article_id '<doc>::dieu-35' or '<doc>::att1-dieu-3' -> .../document/<doc>/dieu-35"""
    doc, unit = article_id.split("::", 1)
    return f"{ID}document/{doc}/{unit}"


def iri_struct(struct_id):
    doc, path = struct_id.split("::", 1)
    return f"{ID}document/{doc}/{path}"


def iri_prov_ref(prov_id):
    """'<doc>::dieu-35::khoan-1::diem-a' -> .../document/<doc>/dieu-35/khoan-1/diem-a"""
    parts = prov_id.split("::")
    return f"{ID}document/{parts[0]}/" + "/".join(parts[1:])


def iri_issuer(code):
    return f"{ID}issuer/{code.lower()}"


def iri_area(slug):
    return f"{ID}area/{slug}"


def iri_change(change_id):
    return f"{ID}change/{change_id}"


def iri_court(court_id):
    return f"{ID}court/{court_id}"


def iri_decision(decision_id):
    src, name = decision_id.split(":", 1)
    return f"{ID}decision/{src}/{name}"


def iri_precedent(precedent_id):
    return f"{ID}precedent/{precedent_id}"


def iri_qa(qa_id):
    return f"{ID}qa/{qa_id}"


def iri_answer(qa_id):
    return f"{ID}qa/{qa_id}/answer"


def iri_term(term_id):
    return f"{ID}term/{term_id}"


def iri_news(news_id):
    return f"{ID}news/{news_id}"


def iri_news_category(slug):
    return f"{ID}news-category/{slug}"


def iri_source(dataset):
    return f"{ID}source/{dataset}"


def iri_edgeset(name):
    return f"{ID}edgeset/{name}"


def iri_build():
    return f"{ID}build/{VERSION}-{BUILD_DATE}"


# ------------------------------------------------------------------ text helpers
def nfc(s):
    return unicodedata.normalize("NFC", s) if s else s


def strip_diacritics(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def slugify(s):
    s = strip_diacritics(nfc(s or "")).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def cut(s, n):
    if s is None:
        return None
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ------------------------------------------------------------------ document types and ranks
DOC_TYPES = {  # Vietnamese type -> (class local name, concept local name, notation)
    "Hiến pháp": ("Constitution", "doctype-constitution", "HP"),
    "Bộ luật": ("Code", "doctype-code", "BL"),
    "Luật": ("Law", "doctype-law", "L"),
    "Pháp lệnh": ("Ordinance", "doctype-ordinance", "PL"),
    "Nghị quyết": ("Resolution", "doctype-resolution", "NQ"),
    "Nghị quyết liên tịch": ("JointResolution", "doctype-joint-resolution", "NQLT"),
    "Nghị định": ("Decree", "doctype-decree", "NĐ"),
    "Quyết định": ("Decision", "doctype-decision", "QĐ"),
    "Thông tư": ("Circular", "doctype-circular", "TT"),
    "Thông tư liên tịch": ("JointCircular", "doctype-joint-circular", "TTLT"),
}
DOC_TYPE_EN = {"Hiến pháp": "Constitution", "Bộ luật": "Code", "Luật": "Law", "Pháp lệnh": "Ordinance",
               "Nghị quyết": "Resolution", "Nghị quyết liên tịch": "Joint resolution", "Nghị định": "Decree",
               "Quyết định": "Decision", "Thông tư": "Circular", "Thông tư liên tịch": "Joint circular"}


def legal_force_rank(doc_type, number):
    """Rule 5 of validity.py v7 (0 = highest). Same code as validity._rank."""
    code = (number or "").split("/")[-1].upper()
    if doc_type == "Hiến pháp":
        return 0
    if doc_type in ("Bộ luật", "Luật"):
        return 1
    if doc_type == "Nghị quyết":
        return 2 if "UBTVQH" in code else (1 if re.search(r"(^|-)QH\d*$", code) else 3)
    if doc_type == "Pháp lệnh":
        return 2
    if doc_type in ("Nghị định", "Nghị quyết liên tịch"):
        return 3
    if doc_type == "Quyết định":
        return 4 if "TTG" in code else 5
    if doc_type in ("Thông tư", "Thông tư liên tịch"):
        return 5
    return 9


RANK_LABELS = {0: ("Constitution", "Hiến pháp"), 1: ("Codes, laws and National Assembly resolutions", "Bộ luật, luật, nghị quyết của Quốc hội"),
               2: ("Ordinances and Standing Committee resolutions", "Pháp lệnh, nghị quyết của Ủy ban Thường vụ Quốc hội"),
               3: ("Decrees, joint resolutions and other resolutions", "Nghị định, nghị quyết liên tịch và nghị quyết khác"),
               4: ("Prime Minister decisions", "Quyết định của Thủ tướng Chính phủ"),
               5: ("Circulars, joint circulars and other decisions", "Thông tư, thông tư liên tịch và quyết định khác")}

VALIDITY_CONCEPT = {"in_force": "validity-in-force", "in_force_amended": "validity-in-force-amended",
                    "presumed_in_force_amended": "validity-presumed-in-force-amended", "superseded": "validity-superseded",
                    "expired": "validity-expired", "not_yet_effective": "validity-not-yet-effective",
                    "not_applicable": "validity-not-applicable", "unknown": "validity-unknown"}
CHANGE_CONCEPT = {"replaced": "change-replaced", "amended": "change-amended", "repealed": "change-repealed",
                  "partially_repealed": "change-partially-repealed", "partially_expired": "change-partially-expired"}
CHANGE_PROPERTY = {"replaced": "replaces", "amended": "amends", "repealed": "repeals",
                   "partially_repealed": "partiallyRepeals", "partially_expired": "partiallyTerminates"}
COURT_LEVEL_CONCEPT = {"Supreme": "court-level-supreme", "High": "court-level-high", "Provincial": "court-level-provincial",
                       "District": "court-level-district", "Military": "court-level-military"}
INSTANCE_CONCEPT = {"First-instance": "instance-first-instance", "Appellate": "instance-appellate",
                    "Cassation": "instance-cassation", "Retrial": "instance-retrial"}
CASE_CONCEPT = {"Civil": "case-civil", "Criminal": "case-criminal", "Administrative": "case-administrative",
                "Commercial": "case-commercial", "Labor": "case-labour", "Marriage & Family": "case-marriage-family",
                "Bankruptcy": "case-bankruptcy", "Economic": "case-economic"}

# Legal areas: slug -> (Vietnamese label, English label). English labels written for VLOnto.
AREA_LABELS = {
    "bo-may-hanh-chinh": ("Bộ máy hành chính", "Administrative apparatus"),
    "giao-duc": ("Giáo dục", "Education"),
    "thue-phi-le-phi": ("Thuế - Phí - Lệ phí", "Taxes, fees and charges"),
    "lao-dong-tien-luong": ("Lao động - Tiền lương", "Labour and wages"),
    "doanh-nghiep": ("Doanh nghiệp", "Enterprises"),
    "bat-dong-san": ("Bất động sản", "Real estate"),
    "tai-nguyen-moi-truong": ("Tài nguyên - Môi trường", "Natural resources and environment"),
    "bao-hiem": ("Bảo hiểm", "Insurance"),
    "thuong-mai": ("Thương mại", "Commerce"),
    "giao-thong-van-tai": ("Giao thông - Vận tải", "Transport"),
    "quyen-dan-su": ("Quyền dân sự", "Civil rights"),
    "trach-nhiem-hinh-su": ("Trách nhiệm hình sự", "Criminal liability"),
    "van-hoa-xa-hoi": ("Văn hóa - Xã hội", "Culture and society"),
    "dau-tu": ("Đầu tư", "Investment"),
    "vi-pham-hanh-chinh": ("Vi phạm hành chính", "Administrative violations"),
    "the-thao-y-te": ("Thể thao - Y tế", "Sports and health"),
    "ke-toan-kiem-toan": ("Kế toán - Kiểm toán", "Accounting and auditing"),
    "cong-nghe-thong-tin": ("Công nghệ thông tin", "Information technology"),
    "tien-te-ngan-hang": ("Tiền tệ - Ngân hàng", "Currency and banking"),
    "xay-dung-do-thi": ("Xây dựng - Đô thị", "Construction and urban development"),
    "linh-vuc-khac": ("Lĩnh vực khác", "Other areas"),
    "thu-tuc-to-tung": ("Thủ tục tố tụng", "Litigation procedure"),
    "dich-vu-phap-ly": ("Dịch vụ pháp lý", "Legal services"),
    "tai-chinh-nha-nuoc": ("Tài chính nhà nước", "Public finance"),
    "xuat-nhap-khau": ("Xuất nhập khẩu", "Import and export"),
    "chung-khoan": ("Chứng khoán", "Securities"),
    "so-huu-tri-tue": ("Sở hữu trí tuệ", "Intellectual property"),
    # terminology-only areas (tnpl)
    "y-te": ("Y tế", "Health care"),
    "buu-chinh-vien-thong": ("Bưu chính - Viễn thông", "Post and telecommunications"),
    "tai-chinh": ("Tài chính", "Finance"),
    "dien": ("Điện", "Electricity"),
    "van-hoa-the-thao-du-lich": ("Văn hóa - Thể thao - Du lịch", "Culture, sports and tourism"),
    "nong-lam-ngu-nghiep": ("Nông - Lâm - Ngư nghiệp", "Agriculture, forestry and fisheries"),
    "quoc-phong-an-ninh": ("Quốc phòng - An ninh", "National defence and security"),
    "khoa-hoc-cong-nghe": ("Khoa học - Công nghệ", "Science and technology"),
    "dan-su": ("Dân sự", "Civil matters"),
    "dat-dai-nha-o": ("Đất đai - Nhà ở", "Land and housing"),
    "phong-chay-chua-chay": ("Phòng cháy chữa cháy", "Fire prevention and fighting"),
    "van-thu-luu-tru": ("Văn thư - Lưu trữ", "Records and archives"),
    "can-bo-cong-chuc-vien-chuc": ("Cán bộ - Công chức - Viên chức", "Officials, civil servants and public employees"),
    "dau-thau": ("Đấu thầu", "Public procurement"),
    "xang-dau": ("Xăng dầu", "Petroleum"),
    "hoa-chat": ("Hóa chất", "Chemicals"),
    "chinh-sach-xa-hoi": ("Chính sách xã hội", "Social policy"),
    "tu-phap-ho-tich": ("Tư pháp - Hộ tịch", "Justice and civil status"),
    "hon-nhan-gia-dinh-thua-ke": ("Hôn nhân - Gia đình - Thừa kế", "Marriage, family and inheritance"),
    "thu-tuc-hanh-chinh": ("Thủ tục hành chính", "Administrative procedures"),
    "xuat-nhap-canh": ("Xuất nhập cảnh", "Entry and exit"),
    "an-toan-thuc-pham": ("An toàn thực phẩm", "Food safety"),
    "khieu-nai-to-cao": ("Khiếu nại - Tố cáo", "Complaints and denunciations"),
    "bo-tro-tu-phap": ("Bổ trợ tư pháp", "Judicial support services"),
}

NEWS_CATEGORY_LABELS = {
    "chinh-sach-moi": ("Chính sách mới", "New policies"),
    "chi-dao-dieu-hanh": ("Chỉ đạo điều hành", "Government direction"),
    "bat-dong-san": ("Bất động sản", "Real estate"),
    "tu-van-cua-luat-su": ("Tư vấn của luật sư", "Lawyers' advice"),
    "tranh-chap": ("Tranh chấp", "Disputes"),
    "tham-nhung": ("Tham nhũng", "Corruption"),
    "tu-van-phap-luat": ("Tư vấn pháp luật", "Legal advice"),
}

# Issuer codes (ASCII upper case, as produced by issuer_codes()) -> (Vietnamese name, English name, kind)
# Alternative symbols found in document numbers -> canonical issuer code (one issuer node per body).
ISSUER_ALIASES = {"TC": "BTC", "YT": "BYT", "NV": "BNV", "GDDT": "BGDDT", "BGD": "BGDDT", "LDTBXH": "BLDTBXH",
                  "BNN": "BNNPTNT", "BKH": "BKHDT", "BLD": "LD", "TCCP": "BTCCBCP", "VKSTC": "VKSNDTC", "UBCK": "UBCKNN",
                  "TM": "BTM"}
ISSUERS = {
    "QH": ("Quốc hội", "National Assembly", "national-assembly"),
    "UBTVQH": ("Ủy ban Thường vụ Quốc hội", "Standing Committee of the National Assembly", "national-assembly"),
    "CTN": ("Chủ tịch nước", "President of the State", "state-president"),
    "CP": ("Chính phủ", "Government", "government"),
    "TTG": ("Thủ tướng Chính phủ", "Prime Minister", "government"),
    "HDBT": ("Hội đồng Bộ trưởng", "Council of Ministers (until 1992)", "government"),
    "HDTP": ("Hội đồng Thẩm phán Tòa án nhân dân tối cao", "Council of Judges of the Supreme People's Court", "judiciary"),
    "TANDTC": ("Tòa án nhân dân tối cao", "Supreme People's Court", "judiciary"),
    "VKSNDTC": ("Viện kiểm sát nhân dân tối cao", "Supreme People's Procuracy", "procuracy"),
    "KTNN": ("Kiểm toán nhà nước", "State Audit Office", "audit"),
    "BTC": ("Bộ Tài chính", "Ministry of Finance", "ministry"),
    "BYT": ("Bộ Y tế", "Ministry of Health", "ministry"),
    "BCA": ("Bộ Công an", "Ministry of Public Security", "ministry"),
    "BQP": ("Bộ Quốc phòng", "Ministry of National Defence", "ministry"),
    "BTP": ("Bộ Tư pháp", "Ministry of Justice", "ministry"),
    "BNG": ("Bộ Ngoại giao", "Ministry of Foreign Affairs", "ministry"),
    "BNV": ("Bộ Nội vụ", "Ministry of Home Affairs", "ministry"),
    "BGDDT": ("Bộ Giáo dục và Đào tạo", "Ministry of Education and Training", "ministry"),
    "BLDTBXH": ("Bộ Lao động - Thương binh và Xã hội", "Ministry of Labour, Invalids and Social Affairs", "ministry"),
    "BXD": ("Bộ Xây dựng", "Ministry of Construction", "ministry"),
    "BGTVT": ("Bộ Giao thông vận tải", "Ministry of Transport", "ministry"),
    "BCT": ("Bộ Công Thương", "Ministry of Industry and Trade", "ministry"),
    "BNNPTNT": ("Bộ Nông nghiệp và Phát triển nông thôn", "Ministry of Agriculture and Rural Development", "ministry"),
    "BNNMT": ("Bộ Nông nghiệp và Môi trường", "Ministry of Agriculture and Environment", "ministry"),
    "BTNMT": ("Bộ Tài nguyên và Môi trường", "Ministry of Natural Resources and Environment", "ministry"),
    "BKHDT": ("Bộ Kế hoạch và Đầu tư", "Ministry of Planning and Investment", "ministry"),
    "BKHCN": ("Bộ Khoa học và Công nghệ", "Ministry of Science and Technology", "ministry"),
    "BTTTT": ("Bộ Thông tin và Truyền thông", "Ministry of Information and Communications", "ministry"),
    "BVHTTDL": ("Bộ Văn hóa, Thể thao và Du lịch", "Ministry of Culture, Sports and Tourism", "ministry"),
    "BDTTG": ("Bộ Dân tộc và Tôn giáo", "Ministry of Ethnic and Religious Affairs", "ministry"),
    "NHNN": ("Ngân hàng Nhà nước Việt Nam", "State Bank of Viet Nam", "ministry"),
    "TTCP": ("Thanh tra Chính phủ", "Government Inspectorate", "ministry"),
    "UBDT": ("Ủy ban Dân tộc", "Committee for Ethnic Minority Affairs", "ministry"),
    "VPCP": ("Văn phòng Chính phủ", "Office of the Government", "ministry"),
    "BCN": ("Bộ Công nghiệp", "Ministry of Industry (until 2007)", "ministry"),
    "BTM": ("Bộ Thương mại", "Ministry of Trade (until 2007)", "ministry"),
    "BBCVT": ("Bộ Bưu chính, Viễn thông", "Ministry of Posts and Telematics (until 2007)", "ministry"),
    "BTS": ("Bộ Thủy sản", "Ministry of Fisheries (until 2007)", "ministry"),
    "BVHTT": ("Bộ Văn hóa - Thông tin", "Ministry of Culture and Information (until 2007)", "ministry"),
    "LD": ("Bộ Lao động", "Ministry of Labour (until 1987)", "ministry"),
    "UBCKNN": ("Ủy ban Chứng khoán Nhà nước", "State Securities Commission", "agency"),
    "TCHQ": ("Tổng cục Hải quan", "General Department of Customs", "agency"),
    "TCT": ("Tổng cục Thuế", "General Department of Taxation", "agency"),
    "BTCCBCP": ("Ban Tổ chức - Cán bộ Chính phủ", "Government Committee for Organisation and Personnel", "ministry"),
    "UBTDTT": ("Ủy ban Thể dục Thể thao", "Committee for Physical Training and Sports", "agency"),
    "BKHCNMT": ("Bộ Khoa học, Công nghệ và Môi trường", "Ministry of Science, Technology and Environment (1992-2002)", "ministry"),
    "TCBD": ("Tổng cục Bưu điện", "Department General of Posts and Telecommunications (1992-2002)", "agency"),
    "HDNN": ("Hội đồng Nhà nước", "Council of State (1981-1992)", "state-president"),
    "BVGCP": ("Ban Vật giá Chính phủ", "Government Pricing Committee", "agency"),
    "TCDL": ("Tổng cục Du lịch", "Viet Nam National Administration of Tourism", "agency"),
    "TCDC": ("Tổng cục Địa chính", "General Department of Land Administration (1994-2002)", "agency"),
    "QLD": ("Cục Quản lý Dược", "Drug Administration of Viet Nam", "agency"),
    "TBXH": ("Bộ Thương binh và Xã hội", "Ministry of War Invalids and Social Affairs (until 1987)", "ministry"),
    "DCSVN": ("Đảng Cộng sản Việt Nam", "Communist Party of Viet Nam", "other"),
    "MTTQVN": ("Ủy ban Trung ương Mặt trận Tổ quốc Việt Nam", "Central Committee of the Viet Nam Fatherland Front", "other"),
    "DCT": ("Đoàn Chủ tịch Ủy ban Trung ương Mặt trận Tổ quốc Việt Nam", "Presidium of the Viet Nam Fatherland Front", "other"),
    "TLD": ("Tổng Liên đoàn Lao động Việt Nam", "Viet Nam General Confederation of Labour", "other"),
    "HDND": ("Hội đồng nhân dân", "People's Council", "local"),
    "UBND": ("Ủy ban nhân dân", "People's Committee", "local"),
}
