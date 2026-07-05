"""เปิด Chrome จริงเข้า datawarehouse.dbd.go.th พิมพ์ค้นหา แคปหน้าจอ แล้วแกะข้อมูลจากหน้าเว็บ

ใช้ Playwright ขับ Chrome ที่ติดตั้งในเครื่อง (channel="chrome") — เป็นเบราว์เซอร์จริง
จึงผ่านระบบกันบอทของ DBD ได้ ต่างจากการยิง API ตรงที่โดน 403

ติดตั้งครั้งแรก:
    pip install playwright
    (ถ้าไม่มี Chrome ในเครื่อง: python3 -m playwright install chromium)
"""
import os
import re

import dbd_client

BASE = "https://datawarehouse.dbd.go.th"
SHOTS_DIR = os.path.join(os.path.dirname(__file__), "dbd_data", "screenshots")

# แผนที่ label บนหน้างบการเงิน -> คอลัมน์ใน dbd_store (เช็คตามลำดับ ข้อความเฉพาะกว่าต้องมาก่อน)
FIN_LABEL_RULES = [
    ("รายได้หลัก", "revenue_main"),
    ("รายได้รวม", "revenue_total"),
    ("ต้นทุนขาย", "cost_of_sales"),
    ("ค่าใช้จ่ายในการขาย", "sga_expense"),
    ("รายจ่ายรวม", "total_expense"),
    ("ดอกเบี้ย", "interest_expense"),
    ("ก่อนภาษี", "profit_before_tax"),
    ("ภาษีเงินได้", "income_tax"),
    ("ขั้นต้น", "gross_profit"),
    ("สุทธิ", "net_profit"),
]

NUM_RE = re.compile(r"-?[\d,]+\.\d+|-?[\d,]{4,}|N/A")


def _launch(p, headless):
    """เปิด Chrome ของเครื่องก่อน ถ้าไม่มีค่อยใช้ Chromium ของ Playwright"""
    exe = os.environ.get("DBD_CHROMIUM_PATH")  # override สำหรับทดสอบ/เครื่องพิเศษ
    if exe:
        return p.chromium.launch(executable_path=exe, headless=headless)
    try:
        return p.chromium.launch(channel="chrome", headless=headless)
    except Exception:
        return p.chromium.launch(headless=headless)


def _parse_number(tok):
    if tok is None or "N/A" in tok:
        return None
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def parse_financial_text(text):
    """แกะตัวเลขงบการเงินจากข้อความบนหน้า 'ข้อมูลงบการเงิน'
    โครงหน้า: แถวปี (เช่น 2567 2568 2569) แล้วตามด้วยหัวข้อ+ตัวเลขทีละรายการ
    คืน list ของ dict ต่อปี พร้อมคีย์ตรงกับ dbd_store.upsert_financial"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    years = []
    for ln in lines:
        toks = ln.split()
        found = [int(t) for t in toks if re.fullmatch(r"25\d\d", t)]
        if len(found) >= 2:
            years = found
            break
    if not years:
        return []

    data = {y: {} for y in years}
    current_field = None
    collected = []

    def flush():
        if current_field:
            for i, y in enumerate(years):
                if i < len(collected) and current_field not in data[y]:
                    data[y][current_field] = _parse_number(collected[i])

    for ln in lines:
        matched = None
        for label, field in FIN_LABEL_RULES:
            if label in ln:
                matched = field
                break
        if matched:
            flush()
            current_field = matched
            collected = NUM_RE.findall(ln)  # เผื่อเลขอยู่บรรทัดเดียวกับ label (layout เดสก์ท็อป)
        elif current_field and len(collected) < len(years):
            collected += NUM_RE.findall(ln)
    flush()

    rows = []
    for y in years:
        if any(v is not None for v in data[y].values()):
            rows.append({"fiscal_year": y, **data[y]})
    return rows


def parse_profile_text(text):
    """แกะข้อมูลนิติบุคคลจากข้อความบนหน้าโปรไฟล์ DBD"""
    out = {}
    m = re.search(r"เลขทะเบียน(?:นิติบุคคล)?\D*(\d{13})", text)
    if m:
        out["tax_id"] = m.group(1)
    m = re.search(r"(บริษัท|ห้างหุ้นส่วน|บมจ\.?)[^\n]{2,80}(จำกัด(?:\s*\(มหาชน\))?)", text)
    if m:
        out["company_name"] = m.group(0).strip()
    m = re.search(r"ทุนจดทะเบียน\D*([\d,]+(?:\.\d+)?)", text)
    if m:
        out["registered_capital"] = _parse_number(m.group(1))
    m = re.search(r"(?:วันที่จดทะเบียน|จดทะเบียนจัดตั้ง|วันที่จัดตั้ง)[^\n]*?(?<!\d)(25\d\d)(?!\d)", text)
    if m:
        out["registration_year"] = int(m.group(1))
    m = re.search(r"สถานะ\W*([^\n]+)", text)
    if m:
        out["status"] = m.group(1).strip()
    m = re.search(r"กรรมการ[^\n]*\n((?:\s*(?:นาย|นาง|นางสาว|น\.ส\.)[^\n]+\n?)+)", text)
    if m:
        names = [n.strip() for n in m.group(1).splitlines() if n.strip()]
        out["directors"] = ", ".join(names)
    if "บริษัทจำกัด" in text or (out.get("company_name", "").startswith("บริษัท")):
        out["juristic_type"] = "บจก."
    elif "ห้างหุ้นส่วน" in text:
        out["juristic_type"] = "หจก."
    return out


def _dismiss_popups(page):
    """ปิด popup เตือนมิจฉาชีพ (#btnWarning) และแบนเนอร์คุกกี้ ถ้าโผล่ขึ้นมา"""
    for selector in ("#btnWarning", "button:has-text('ยอมรับ')", "button:has-text('ปิด')"):
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible():
                btn.click()
                page.wait_for_timeout(500)
        except Exception:
            pass


def _goto_first_profile(page, result, shots_dir, wait_ms):
    """หลังค้นหา: กดลิงก์โปรไฟล์บริษัทตัวแรกที่เจอ (ทั้งใน dropdown แนะนำและหน้าผลค้นหา)
    คืน True ถ้าไปถึงหน้าโปรไฟล์"""
    if "/company/profile/" in page.url:
        return True
    link = page.locator("a[href*='/company/profile/']").first
    if link.count() == 0:
        shot = os.path.join(shots_dir, "search_results.png")
        page.screenshot(path=shot, full_page=True)
        result["screenshots"].append(shot)
        return False
    link.click()
    page.wait_for_timeout(wait_ms)
    _dismiss_popups(page)
    return "/company/profile/" in page.url


def lookup(query, headless=False, shots_dir=SHOTS_DIR, wait_ms=6000):
    """เปิด Chrome เข้า datawarehouse.dbd.go.th พิมพ์ค้นหาในช่องค้นหาหน้าแรกเหมือนคนใช้จริง
    กดค้นหา เข้าโปรไฟล์บริษัท แคปหน้าจอ และแกะข้อมูล

    query: ชื่อบริษัท / เลขทะเบียน 13 หลัก / URL หน้าโปรไฟล์
    headless=False จะเห็นหน้าต่าง Chrome ทำงานจริง (แนะนำ — ผ่านกันบอทง่ายกว่า)
    คืน dict: {tax_id, profile, financials, screenshots, profile_text, financial_text, error}
    """
    from playwright.sync_api import sync_playwright

    os.makedirs(shots_dir, exist_ok=True)
    tax_id, profile_id = dbd_client.extract_juristic_id(query)
    is_profile_url = "/company/profile/" in str(query)
    result = {"tax_id": tax_id, "screenshots": [], "error": None}

    with sync_playwright() as p:
        browser = _launch(p, headless)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            if not is_profile_url:
                # เข้าเว็บหน้าแรก ปิด popup แล้วพิมพ์ค้นหาในช่องค้นหาเหมือนคนใช้จริง
                page.goto(BASE, timeout=60000)
                page.wait_for_timeout(wait_ms)
                _dismiss_popups(page)

                box = page.locator("input[placeholder*='ค้นหาด้วยชื่อ']").first
                if box.count() == 0:
                    box = page.locator("input[placeholder*='ค้นหา']").first
                box.click()
                box.type(str(query), delay=60)  # พิมพ์ทีละตัวเหมือนมนุษย์ ให้ dropdown แนะนำทำงาน
                page.wait_for_timeout(2500)

                shot = os.path.join(shots_dir, "search_typing.png")
                page.screenshot(path=shot, full_page=True)
                result["screenshots"].append(shot)

                # ทางที่ 1: dropdown แนะนำ (#suggestionContent) มีลิงก์โปรไฟล์ให้กดเลย
                suggestion = page.locator("#suggestionContent a[href*='/company/profile/']").first
                if suggestion.count() > 0:
                    suggestion.click()
                else:
                    # ทางที่ 2: กด Enter/ปุ่มแว่นขยาย เพื่อไปหน้าผลค้นหา แล้วกดผลตัวแรก
                    box.press("Enter")
                page.wait_for_timeout(wait_ms)
                _dismiss_popups(page)

                if not _goto_first_profile(page, result, shots_dir, wait_ms):
                    result["error"] = ("ค้นหาแล้วไม่พบลิงก์โปรไฟล์บริษัท — ดูสกรีนช็อตว่าเว็บแสดงอะไร "
                                       "แล้วลองพิมพ์ชื่อให้ตรงกับชื่อจดทะเบียน หรือใช้เลขทะเบียน 13 หลัก")
                    return result

                tax_id, profile_id = dbd_client.extract_juristic_id(page.url)
                result["tax_id"] = tax_id
            else:
                page.goto(f"{BASE}/company/profile/{profile_id}", timeout=60000)
                page.wait_for_timeout(wait_ms)
                _dismiss_popups(page)

            shot = os.path.join(shots_dir, f"{tax_id}_profile.png")
            page.screenshot(path=shot, full_page=True)
            result["screenshots"].append(shot)
            result["profile_text"] = page.inner_text("body")
            result["profile"] = parse_profile_text(result["profile_text"])

            # เปิดแท็บงบการเงิน
            fin_tab = page.get_by_text("ข้อมูลงบการเงิน").first
            if fin_tab.count() > 0:
                fin_tab.click()
                page.wait_for_timeout(int(wait_ms * 0.7))
                shot = os.path.join(shots_dir, f"{tax_id}_financial.png")
                page.screenshot(path=shot, full_page=True)
                result["screenshots"].append(shot)
                result["financial_text"] = page.inner_text("body")
                result["financials"] = parse_financial_text(result["financial_text"])
            else:
                result["error"] = "ไม่พบแท็บ 'ข้อมูลงบการเงิน' บนหน้าโปรไฟล์"
        except Exception as e:
            result["error"] = f"{e.__class__.__name__}: {e}"
            try:
                shot = os.path.join(shots_dir, "error.png")
                page.screenshot(path=shot, full_page=True)
                result["screenshots"].append(shot)
            except Exception:
                pass
        finally:
            browser.close()
    return result
