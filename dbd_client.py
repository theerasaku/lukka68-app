"""ดึงข้อมูลนิติบุคคลจาก DBD

แหล่งข้อมูลหลัก: DBD Open API อย่างเป็นทางการ
    https://openapi.dbd.go.th/api/v1/juristic_person/{เลขทะเบียน 13 หลัก}
ให้ ชื่อ ประเภท สถานะ ทุนจดทะเบียน วันจดทะเบียน ที่อยู่ (ไม่มีงบการเงิน/กรรมการ)

งบการเงินอยู่บนหน้าเว็บ datawarehouse.dbd.go.th ซึ่งมี bot-protection (มัก 403)
จึงลอง endpoint ภายในแบบ best-effort เท่านั้น — ถ้าไม่ได้ให้กรอกด้วยตนเองในแอพ
"""
import re
import requests

BASE = "https://datawarehouse.dbd.go.th"
OPEN_API = "https://openapi.dbd.go.th/api/v1/juristic_person/{tax_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
    "Referer": BASE + "/",
}

# endpoint ภายในที่เคยพบว่าเว็บใช้ (อาจเปลี่ยนได้ — เรียงตามโอกาสสำเร็จ)
SEARCH_ENDPOINTS = [
    BASE + "/api/index/juristicSearch?searchText={q}",
    BASE + "/api/juristic/search?keyword={q}",
    BASE + "/searchJuristicData?juristicName={q}",
]
PROFILE_ENDPOINTS = [
    BASE + "/api/company/profile/{jid}",
    BASE + "/api/juristic/profile/{jid}",
    BASE + "/company/profile-json/{jid}",
]
FINANCIAL_ENDPOINTS = [
    BASE + "/api/company/profile/financial/{jid}",
    BASE + "/api/juristic/financial/{jid}",
    BASE + "/api/company/financial/{jid}",
]


def make_session():
    """สร้าง session พร้อม cookie จากหน้าแรก (บาง endpoint ต้องมี session cookie ก่อน)"""
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        s.get(BASE + "/", timeout=15)
    except requests.RequestException:
        pass  # ถ้าหน้าแรกล้ม ยังให้ลองยิง endpoint ตรงต่อได้
    return s


def extract_juristic_id(text):
    """รับได้ทั้งเลข 13 หลัก, เลขที่มี prefix 5 (14 หลัก) หรือ URL หน้าโปรไฟล์ DBD
    คืนค่า (tax_id_13, profile_id_14)"""
    m = re.search(r"(\d{13,14})", str(text).replace("-", ""))
    if not m:
        return None, None
    digits = m.group(1)
    if len(digits) == 14 and digits.startswith("5"):
        return digits[1:], digits
    return digits, "5" + digits


def _try_get_json(session, urls, timeout=15):
    """ยิง GET ทีละ URL คืน (json, url ที่สำเร็จ) ตัวแรกที่ได้ JSON กลับมา"""
    last_error = None
    for url in urls:
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                try:
                    return resp.json(), url
                except ValueError:
                    last_error = f"{url} -> ไม่ใช่ JSON"
            else:
                last_error = f"{url} -> HTTP {resp.status_code}"
        except requests.RequestException as e:
            last_error = f"{url} -> {e.__class__.__name__}"
    return None, last_error


def search_juristic(keyword, session=None):
    """ค้นหานิติบุคคลด้วยชื่อหรือเลขทะเบียน คืน (list ผลลัพธ์ดิบ, ข้อความสถานะ)"""
    session = session or make_session()
    from urllib.parse import quote
    urls = [u.format(q=quote(str(keyword))) for u in SEARCH_ENDPOINTS]
    data, info = _try_get_json(session, urls)
    if data is None:
        return None, info
    if isinstance(data, dict):
        for key in ("data", "result", "items", "juristicList", "list"):
            if isinstance(data.get(key), list):
                return data[key], info
        return [data], info
    return data, info


def fetch_open_api_profile(tax_id, session=None):
    """ดึงโปรไฟล์จาก DBD Open API อย่างเป็นทางการ คืน (json, url/สาเหตุที่ล้ม)"""
    session = session or requests.Session()
    session.headers.update(HEADERS)
    url = OPEN_API.format(tax_id=tax_id)
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code == 200:
            return resp.json(), url
        return None, f"{url} -> HTTP {resp.status_code}"
    except ValueError:
        return None, f"{url} -> ไม่ใช่ JSON"
    except requests.RequestException as e:
        return None, f"{url} -> {e.__class__.__name__}"


def fetch_company(juristic_id, session=None):
    """ดึงโปรไฟล์ + งบการเงินของนิติบุคคล คืน dict:
    {profile: ..., financials: ..., profile_source: url, financial_source: url, errors: [...]}"""
    session = session or make_session()
    tax_id, profile_id = extract_juristic_id(juristic_id)
    if not tax_id:
        return {"errors": ["ไม่พบเลขทะเบียนนิติบุคคลใน input"]}

    out = {"tax_id": tax_id, "profile_id": profile_id, "errors": []}

    # โปรไฟล์: Open API ทางการก่อน (เสถียรสุด) แล้วค่อย fallback endpoint ภายใน
    profile, info = fetch_open_api_profile(tax_id, session)
    if profile is not None:
        out["profile"], out["profile_source"] = profile, info
    else:
        out["errors"].append(f"Open API ไม่สำเร็จ: {info}")
        for jid in (profile_id, tax_id):
            profile, info = _try_get_json(session, [u.format(jid=jid) for u in PROFILE_ENDPOINTS])
            if profile is not None:
                out["profile"], out["profile_source"] = profile, info
                break
        else:
            out["errors"].append(f"ดึงโปรไฟล์จาก datawarehouse ไม่สำเร็จ: {info}")

    for jid in (profile_id, tax_id):
        fin, info = _try_get_json(session, [u.format(jid=jid) for u in FINANCIAL_ENDPOINTS])
        if fin is not None:
            out["financials"], out["financial_source"] = fin, info
            break
    else:
        out["errors"].append(
            f"ดึงงบการเงินไม่สำเร็จ ({info}) — งบการเงินไม่มีใน Open API ทางการ "
            "และหน้าเว็บ datawarehouse มีระบบกันบอท: เปิดดูบนเว็บแล้วกรอกในแอพแทน")

    return out


def _pick(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def _to_number(v):
    if v in (None, "", "N/A", "-"):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _flatten(obj, out=None):
    """เดินทุกชั้นของ JSON เก็บ (key ที่ตัด namespace เช่น 'cd:' และแปลงเป็นตัวพิมพ์เล็ก, ค่า)
    เรียงตามลำดับที่พบ เพื่อให้ค้นหา field ได้ไม่ว่าโครงสร้างจะซ้อนกี่ชั้น"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            norm = str(k).split(":")[-1].lower()
            out.append((norm, v))
            _flatten(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _flatten(item, out)
    return out


def _find_flat(flat, *substrings):
    """คืนค่าแรกที่ชื่อ key มี substring ใดตัวหนึ่ง (เรียงลำดับความสำคัญตาม args)
    ข้ามค่าที่เป็น dict/list/ว่าง"""
    for sub in substrings:
        for key, value in flat:
            if sub in key and not isinstance(value, (dict, list)) and value not in (None, ""):
                return value
    return None


def _address_text(flat):
    """ประกอบที่อยู่จาก subtree ที่ key มีคำว่า address (Open API เก็บที่อยู่แบบซ้อนหลายชั้น)"""
    for key, value in flat:
        if "address" in key:
            if isinstance(value, str) and len(value) > 10:
                return value
            if isinstance(value, dict):
                leaves = [v for _, v in _flatten(value) if isinstance(v, str) and v.strip()]
                if leaves:
                    seen = []
                    for leaf in leaves:
                        if leaf not in seen:
                            seen.append(leaf)
                    return " ".join(seen)
    return None


def normalize_profile(raw):
    """แปลง JSON โปรไฟล์เป็น dict สำหรับ dbd_store.upsert_company
    รองรับทั้ง Open API (key แบบ cd:OrganizationJuristicNameTH ซ้อนหลายชั้น)
    และ endpoint ภายในของ datawarehouse (key แบน ๆ เช่น juristicName)"""
    flat = _flatten(raw)
    reg_date = _find_flat(flat, "registerdate", "registrationdate")
    reg_year = None
    if reg_date:
        m = re.search(r"(\d{4})", str(reg_date))
        if m:
            y = int(m.group(1))
            reg_year = y if y > 2400 else y + 543  # ค.ศ. -> พ.ศ.

    directors = None
    for key, value in flat:
        if "director" in key or "committee" in key:
            if isinstance(value, list):
                names = [v for v in value if isinstance(v, str)]
                directors = ", ".join(names) if names else None
            elif isinstance(value, str):
                directors = value
            if directors:
                break

    return {
        "company_name": _find_flat(flat, "juristicnameth", "juristicname", "companyname", "nameth", "name"),
        "juristic_type": _find_flat(flat, "juristictype", "typename", "type"),
        "registered_capital": _to_number(_find_flat(flat, "registercapital", "registeredcapital", "capital")),
        "registration_year": reg_year,
        "status": _find_flat(flat, "juristicstatus", "status"),
        "address": _address_text(flat),
        "directors": directors,
    }


def normalize_financials(raw):
    """แปลง JSON งบการเงินเป็น list ของ dict ต่อปี สำหรับ dbd_store.upsert_financial"""
    if isinstance(raw, dict):
        for key in ("data", "result", "items", "financialList", "list"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raw = [raw]
    rows = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        year = _pick(item, "fiscalYear", "year", "yearTh", "accountYear")
        try:
            year = int(re.search(r"(\d{4})", str(year)).group(1))
        except (AttributeError, TypeError):
            continue
        if year < 2400:
            year += 543
        rows.append({
            "fiscal_year": year,
            "revenue_main": _to_number(_pick(item, "mainRevenue", "revenueMain", "saleRevenue")),
            "revenue_total": _to_number(_pick(item, "totalRevenue", "revenueTotal", "totalIncome")),
            "cost_of_sales": _to_number(_pick(item, "costOfSales", "saleCost", "costOfGoodsSold")),
            "gross_profit": _to_number(_pick(item, "grossProfit", "grossProfitLoss")),
            "sga_expense": _to_number(_pick(item, "sellingAdminExpense", "sgaExpense", "adminExpense")),
            "total_expense": _to_number(_pick(item, "totalExpense", "expenseTotal")),
            "interest_expense": _to_number(_pick(item, "interestExpense", "financeCost")),
            "profit_before_tax": _to_number(_pick(item, "profitBeforeTax", "earningBeforeTax", "ebt")),
            "income_tax": _to_number(_pick(item, "incomeTax", "tax")),
            "net_profit": _to_number(_pick(item, "netProfit", "netProfitLoss", "netIncome")),
        })
    rows.sort(key=lambda r: r["fiscal_year"])
    return rows
