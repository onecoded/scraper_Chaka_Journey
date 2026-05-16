"""
teaser_parser.py
Parse business opportunity teasers from BIZBROKER/TEASERS.
Match deals to buyers from BIZBROKER/buyers_db.py.
"""
import re
import sys
from pathlib import Path

BIZBROKER   = Path(r"C:\Users\schne\OneDrive\Documents\~Projects\BIZBROKER")
TEASERS_DIR = BIZBROKER / "TEASERS"

_buyers_cache = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_dollars(s) -> float:
    if not s:
        return 0.0
    s = re.sub(r"[,$\s]", "", str(s)).upper()
    m = re.search(r"([\d.]+)([MKB]?)", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    if m.group(2) == "M": val *= 1_000_000
    elif m.group(2) == "K": val *= 1_000
    elif m.group(2) == "B": val *= 1_000_000_000
    return val

def _fmt_dollars(n: float) -> str:
    if not n:
        return ""
    if n >= 1_000_000:
        return f"${n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n/1_000:.0f}K"
    return f"${n:,.0f}"


# ── buyers ────────────────────────────────────────────────────────────────────

def load_buyers() -> list:
    global _buyers_cache
    if _buyers_cache is not None:
        return _buyers_cache
    try:
        if str(BIZBROKER) not in sys.path:
            sys.path.insert(0, str(BIZBROKER))
        import buyers_db as _bdb
        _buyers_cache = _bdb.BUYERS
    except Exception as e:
        print(f"[TEASERS] buyers_db load error: {e}")
        _buyers_cache = []
    return _buyers_cache


# ── parsers ───────────────────────────────────────────────────────────────────

def parse_msc_txt(path: Path) -> list:
    """Parse the structured MSC Deals text file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"━{10,}", text)
    deals = []

    for block in blocks:
        block = block.strip()
        if not block.upper().startswith("PROJECT "):
            continue
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]

        # Header: PROJECT NAME — Industry | Geography
        header = lines[0]
        nm = re.match(r"PROJECT\s+(\w+)\s+[—–-]\s+(.+?)(?:\s*\|\s*(.+))?$", header)
        if not nm:
            continue
        project_name  = f"PROJECT {nm.group(1)}"
        industry      = nm.group(2).strip()
        geography     = (nm.group(3) or "").strip()

        # Financials line
        revenue = ebitda = 0.0
        for line in lines[1:6]:
            if "EBITDA" in line.upper() and "REVENUE" in line.upper():
                rm = re.search(r"Revenue:?\s*(\$[\d.,]+\s*[MmKk]?)", line, re.I)
                em = re.search(r"EBITDA:?\s*(\$[\d.,]+\s*[MmKk]?)", line, re.I)
                if rm: revenue = _parse_dollars(rm.group(1))
                if em: ebitda  = _parse_dollars(em.group(1))
                break

        # MSC broker contact
        broker_name = broker_email = broker_phone = ""
        for line in lines:
            mc = re.search(r"MSC Contact:\s*(.+?)\s*[—–-]\s*([\w.+%-]+@[\w.-]+)", line)
            if mc:
                broker_name  = mc.group(1).strip()
                broker_email = mc.group(2).strip()
                break

        note = ""
        for line in lines:
            ls = line.strip()
            if ls.startswith("⚠") or ls.upper().startswith("NOTE:"):
                note = ls; break

        deals.append({
            "project_name": project_name,
            "title": header,
            "industry":   industry,
            "geography":  geography,
            "revenue":    revenue,
            "ebitda":     ebitda,
            "revenue_raw": _fmt_dollars(revenue),
            "ebitda_raw":  _fmt_dollars(ebitda),
            "broker_name":  broker_name,
            "broker_email": broker_email,
            "broker_phone": broker_phone,
            "source":       "msc_txt",
            "source_file":  path.name,
            "note":         note,
        })

    return deals


def parse_xlsx_listings(path: Path) -> list:
    """Parse seller listings spreadsheet."""
    try:
        import openpyxl
    except ImportError:
        return []
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = [r for r in ws.iter_rows(values_only=True) if any(c for c in r)]
    except Exception:
        return []

    if len(rows) < 2:
        return []

    # Detect header row (first row with recognizable column names)
    header = None
    data_start = 1
    for i, row in enumerate(rows[:5]):
        cells = [str(c or "").lower().strip() for c in row]
        if any(kw in " ".join(cells) for kw in ["company","name","industry","revenue","ebitda","deal"]):
            header = cells
            data_start = i + 1
            break
    if header is None:
        return []

    def _col(row, *names):
        for n in names:
            for idx, h in enumerate(header):
                if n in h and idx < len(row) and row[idx] is not None:
                    return str(row[idx]).strip()
        return ""

    results = []
    for row in rows[data_start:]:
        name = _col(row, "company","name","deal","project","business") or _col(row, "title")
        if not name or name.lower() in ("none","n/a",""):
            continue
        rev_raw  = _col(row, "revenue","sales","gross")
        ebit_raw = _col(row, "ebitda","cash flow","cashflow","sde","net income")
        results.append({
            "project_name":  name,
            "title":         name,
            "industry":      _col(row, "industry","sector","category","type"),
            "geography":     _col(row, "geography","location","state","region","geo"),
            "revenue":       _parse_dollars(rev_raw),
            "ebitda":        _parse_dollars(ebit_raw),
            "revenue_raw":   rev_raw,
            "ebitda_raw":    ebit_raw,
            "broker_name":   _col(row, "broker","agent","contact","rep"),
            "broker_email":  _col(row, "email","mail"),
            "broker_phone":  _col(row, "phone","tel"),
            "source":        "xlsx",
            "source_file":   path.name,
            "note":          _col(row, "note","comment","status","flag"),
        })
    return results


def scan_pdf_teasers() -> list:
    """
    Scan PDF teasers. Uses pdfplumber if available.
    Skips 'No Contact Teasers' subfolder.
    """
    try:
        import pdfplumber
        has_plumber = True
    except ImportError:
        has_plumber = False

    results = []
    for pdf_path in TEASERS_DIR.rglob("*.pdf"):
        # Skip explicitly no-contact teasers
        if "No Contact" in str(pdf_path):
            continue

        title = pdf_path.stem.replace("_", " ").replace("-", " ").strip()
        deal = {
            "project_name": title,
            "title": title,
            "industry": "", "geography": "",
            "revenue": 0.0, "ebitda": 0.0,
            "revenue_raw": "", "ebitda_raw": "",
            "broker_name": "", "broker_email": "", "broker_phone": "",
            "source": "pdf", "source_file": pdf_path.name,
            "pdf_path": str(pdf_path), "note": "",
        }

        if has_plumber:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    text = "".join(p.extract_text() or "" for p in pdf.pages[:3])

                rm = re.search(r"revenue[:\s]+(\$[\d.,]+\s*[MmKk]?)", text, re.I)
                em = re.search(r"ebitda[:\s]+(\$[\d.,]+\s*[MmKk]?)", text, re.I)
                gm = re.search(r"(?:location|geography|based in|headquartered)[:\s]+([A-Za-z ,]+)", text, re.I)
                im = re.search(r"(?:industry|sector|business type)[:\s]+([A-Za-z /&,-]+)", text, re.I)
                xm = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)

                if rm: deal["revenue"] = _parse_dollars(rm.group(1)); deal["revenue_raw"] = rm.group(1)
                if em: deal["ebitda"]  = _parse_dollars(em.group(1)); deal["ebitda_raw"]  = em.group(1)
                if gm: deal["geography"] = gm.group(1).strip()[:60]
                if im: deal["industry"]  = im.group(1).strip()[:60]
                if xm: deal["broker_email"] = xm.group(0)
            except Exception:
                pass

        results.append(deal)
    return results


# ── load all ──────────────────────────────────────────────────────────────────

def scan_all_teasers() -> list:
    """Load all deals from all sources under TEASERS_DIR."""
    deals = []
    seen  = set()

    # 1. MSC Deals text file
    msc = TEASERS_DIR / "3-9-26" / "MSC Deals - Buyer Matches & Emails.txt"
    if msc.exists():
        try:
            parsed = parse_msc_txt(msc)
            deals.extend(parsed)
        except Exception as e:
            print(f"[TEASERS] MSC parse error: {e}")

    # 2. XLSX files
    for xlsx in TEASERS_DIR.rglob("*.xlsx"):
        if xlsx.name.startswith("~$"):
            continue
        try:
            parsed = parse_xlsx_listings(xlsx)
            deals.extend(parsed)
        except Exception as e:
            print(f"[TEASERS] XLSX error {xlsx.name}: {e}")

    # 3. PDF teasers
    try:
        deals.extend(scan_pdf_teasers())
    except Exception as e:
        print(f"[TEASERS] PDF scan error: {e}")

    # Deduplicate
    deduped = []
    for d in deals:
        key = (d.get("project_name") or d.get("title") or "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(d)

    return deduped


# ── scoring ───────────────────────────────────────────────────────────────────

_GEO_REGIONS = {
    "southeast": {"FL","GA","NC","SC","TN","AL","MS","AR","VA","KY"},
    "midwest":   {"OH","IN","IL","MI","MN","MO","WI","IA","KS","NE","ND","SD"},
    "northeast": {"NY","NJ","PA","CT","MA","RI","VT","NH","ME","MD","DE"},
    "southwest": {"TX","AZ","NM","OK"},
    "west":      {"CA","OR","WA","CO","NV","UT","ID","MT","WY","AK","HI"},
}

def _geo_matches(deal_geo: str, buyer_geos: list) -> int:
    dg = deal_geo.upper()
    for g in [x.lower() for x in buyer_geos]:
        gu = g.upper()
        if gu in ("US","NATIONAL","NATIONWIDE","UNITED STATES"):
            return 15
        if gu in dg or dg in gu:
            return 25
        # region keyword
        for region, states in _GEO_REGIONS.items():
            if region in g and any(s in dg for s in states):
                return 20
        # state abbrev in deal geo
        if len(gu) == 2 and gu in dg:
            return 25
    return 0

def score_teaser_buyer(deal: dict, buyer: dict) -> int:
    """Score deal↔buyer match. Returns 0-100."""
    score = 0

    # Industry (0–40)
    di = (deal.get("industry") or "").lower()
    bi = " ".join(buyer.get("industries", [])).lower()
    di_words = set(re.split(r"[\s/&,-]+", di))
    bi_words = set(re.split(r"[\s/&,-]+", bi))
    overlap  = di_words & bi_words - {"", "and", "or", "the"}
    score += min(40, len(overlap) * 15)
    if "general" in bi:
        score += 10

    # EBITDA (0–35)
    ebitda = deal.get("ebitda") or 0.0
    b_min  = buyer.get("ebitda_min") or 0
    b_max  = buyer.get("ebitda_max") or 999_000_000
    if ebitda > 0:
        if b_min <= ebitda <= b_max:
            score += 35
        elif ebitda < b_min and ebitda > b_min * 0.5:
            score += 15
        elif ebitda > b_max and ebitda < b_max * 2.0:
            score += 15
    else:
        score += 15  # unknown EBITDA — partial credit

    # Geography (0–25)
    score += _geo_matches(
        deal.get("geography") or deal.get("location") or "",
        buyer.get("geography") or [],
    )

    return min(100, score)


def match_teasers(deals: list) -> list:
    """
    Return list of {deal, buyer, match_score} sorted by score desc.
    Only includes buyers with email or website (contact filter).
    Only includes matches scoring >= 30.
    """
    buyers = load_buyers()
    matches = []
    for deal in deals:
        for buyer in buyers:
            if not (buyer.get("email") or buyer.get("website")):
                continue
            s = score_teaser_buyer(deal, buyer)
            if s >= 30:
                matches.append({"deal": deal, "buyer": buyer, "match_score": s})
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches
