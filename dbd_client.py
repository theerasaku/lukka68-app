"""ดึงข้อมูลนิติบุคคลและงบการเงินจาก datawarehouse.dbd.go.th

DBD ไม่มี public API อย่างเป็นทางการ — โมดูลนี้ใช้ endpoint ภายในของหน้าเว็บ
ซึ่งอาจเปลี่ยนได้ทุกเมื่อ จึงลองหลาย endpoint ตามลำดับและคืนผลจากตัวแรกที่ตอบ JSON
ต้องรันจากเครื่อง/เซิร์ฟเวอร์ที่เข้าถึง datawarehouse.dbd.go.th ได้จริง
"""
import re
import requests

BASE = "https://datawarehouse.dbd.go.th"

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


def fetch_company(juristic_id, session=None):
    """ดึงโปรไฟล์ + งบการเงินของนิติบุคคล คืน dict:
    {profile: ..., financials: ..., profile_source: url, financial_source: url, errors: [...]}"""
    session = session or make_session()
    tax_id, profile_id = extract_juristic_id(juristic_id)
    if not tax_id:
        return {"errors": ["ไม่พบเลขทะเบียนนิติบุคคลใน input"]}

    out = {"tax_id": tax_id, "profile_id": profile_id, "errors": []}

    for jid in (profile_id, tax_id):
        profile, info = _try_get_json(session, [u.format(jid=jid) for u in PROFILE_ENDPOINTS])
        if profile is not None:
            out["profile"], out["profile_source"] = profile, info
            break
    else:
        out["errors"].append(f"ดึงโปรไฟล์ไม่สำเร็จ: {info}")

    for jid in (profile_id, tax_id):
        fin, info = _try_get_json(session, [u.format(jid=jid) for u in FINANCIAL_ENDPOINTS])
        if fin is not None:
            out["financials"], out["financial_source"] = fin, info
            break
    else:
        out["errors"].append(f"ดึงงบการเงินไม่สำเร็จ: {info}")

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


def normalize_profile(raw):
    """แปลง JSON โปรไฟล์ (โครงสร้างไม่แน่นอน) เป็น dict สำหรับ dbd_store.upsert_company"""
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if isinstance(raw, dict) and isinstance(raw.get("data"), (dict, list)):
        return normalize_profile(raw["data"])
    reg_date = _pick(raw, "registerDate", "registrationDate", "juristicRegisterDate")
    reg_year = None
    if reg_date:
        m = re.search(r"(\d{4})", str(reg_date))
        if m:
            y = int(m.group(1))
            reg_year = y if y > 2400 else y + 543  # ค.ศ. -> พ.ศ.
    return {
        "company_name": _pick(raw, "juristicName", "juristicNameTH", "companyName", "name"),
        "juristic_type": _pick(raw, "juristicType", "juristicTypeName", "type"),
        "registered_capital": _to_number(_pick(raw, "registerCapital", "registeredCapital", "capital")),
        "registration_year": reg_year,
        "address": _pick(raw, "address", "fullAddress", "juristicAddress"),
        "directors": ", ".join(raw.get("directors", [])) if isinstance(raw.get("directors"), list)
                     else _pick(raw, "directors", "committee", "directorList"),
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
