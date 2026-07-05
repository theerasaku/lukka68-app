"""ดึงข้อมูลบริษัทจาก DBD แบบ command line — ใช้ใน GitHub Actions หรือ cron

ใช้:  python3 dbd_fetch.py "ชื่อบริษัท หรือ เลขทะเบียน 13 หลัก"

ทำอะไรบ้าง:
1. เปิด Chromium (headless) เข้า datawarehouse.dbd.go.th ค้นหา แคปหน้าจอ แกะข้อมูล
2. บันทึกลง SQLite และอัปเดต dbd_data/seed.json (ไฟล์ที่ commit ได้ ให้แอพใช้ต่อ)
3. เขียนสรุปเป็น Markdown — ถ้ารันใน GitHub Actions จะไปโผล่ในหน้า Summary ของ run
"""
import json
import os
import sys

import dbd_browser
import dbd_store

SUMMARY_FIELDS = [
    ("revenue_main", "รายได้หลัก"),
    ("revenue_total", "รายได้รวม"),
    ("total_expense", "รายจ่ายรวม"),
    ("profit_before_tax", "กำไรก่อนภาษี"),
    ("net_profit", "กำไรสุทธิ"),
]


def save_result(result):
    """บันทึกผล lookup ลง SQLite (โค้ดเดียวกับปุ่มบันทึกในแอพ)"""
    tax_id = result["tax_id"]
    profile = result.get("profile") or {}
    dbd_store.upsert_company(
        tax_id=tax_id,
        company_name=profile.get("company_name") or f"(ไม่ทราบชื่อ) {tax_id}",
        juristic_type=profile.get("juristic_type"),
        registered_capital=profile.get("registered_capital"),
        registration_year=profile.get("registration_year"),
        address=profile.get("address"),
        directors=profile.get("directors"),
        source="datawarehouse.dbd.go.th (GitHub Actions)",
    )
    for row in result.get("financials") or []:
        row = dict(row)
        dbd_store.upsert_financial(tax_id, row.pop("fiscal_year"), **row)


def update_seed(tax_id):
    """เขียนข้อมูลบริษัทจาก SQLite กลับเข้า seed.json เพื่อให้ commit ติด repo ได้"""
    detail = dbd_store.get_company(tax_id)
    if not detail:
        return
    c = detail["company"]
    entry = {
        "tax_id": c["tax_id"],
        "company_name": c["company_name"],
        "juristic_type": c["juristic_type"],
        "registered_capital": c["registered_capital"],
        "registration_year": c["registration_year"],
        "address": c["address"],
        "directors": c["directors"],
        "source": c["source"],
        "financials": [{k: v for k, v in f.items() if k != "tax_id"} for f in detail["financials"]],
    }
    seed = {"companies": []}
    if os.path.exists(dbd_store.SEED_PATH):
        with open(dbd_store.SEED_PATH, encoding="utf-8") as f:
            seed = json.load(f)
    seed["companies"] = [x for x in seed.get("companies", []) if x.get("tax_id") != tax_id]
    seed["companies"].append(entry)
    with open(dbd_store.SEED_PATH, "w", encoding="utf-8") as f:
        json.dump(seed, f, ensure_ascii=False, indent=2)


def build_summary(result):
    """สรุปผลเป็น Markdown สำหรับหน้า GitHub Actions Summary (อ่านบนมือถือได้เลย)"""
    lines = []
    profile = result.get("profile") or {}
    name = profile.get("company_name") or result.get("tax_id") or "?"
    lines.append(f"# 🏛️ {name}")
    lines.append("")
    lines.append("| รายการ | ข้อมูล |")
    lines.append("|---|---|")
    lines.append(f"| เลขทะเบียน | {result.get('tax_id') or '-'} |")
    cap = profile.get("registered_capital")
    lines.append(f"| ทุนจดทะเบียน | {f'{cap:,.0f} บาท' if cap else '-'} |")
    year = profile.get("registration_year")
    lines.append(f"| ปีจดทะเบียน | {f'พ.ศ. {year}' if year else '-'} |")
    lines.append(f"| สถานะ | {profile.get('status') or '-'} |")
    lines.append(f"| กรรมการ | {profile.get('directors') or '-'} |")
    lines.append("")

    fin = result.get("financials") or []
    if fin:
        lines.append("## 📊 งบการเงิน (บาท)")
        lines.append("")
        lines.append("| ปี | " + " | ".join(label for _, label in SUMMARY_FIELDS) + " |")
        lines.append("|---|" + "---|" * len(SUMMARY_FIELDS))
        for row in fin:
            cells = [f"{row[k]:,.2f}" if row.get(k) is not None else "-" for k, _ in SUMMARY_FIELDS]
            lines.append(f"| {row['fiscal_year']} | " + " | ".join(cells) + " |")
    else:
        lines.append("> ⚠️ แกะตัวเลขงบการเงินไม่ได้ — ดูสกรีนช็อตใน Artifacts ของ run นี้")
    if result.get("error"):
        lines.append("")
        lines.append(f"> ⚠️ {result['error']}")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("ใช้: python3 dbd_fetch.py \"ชื่อบริษัท หรือ เลขทะเบียน 13 หลัก\"")
        return 2
    query = sys.argv[1].strip()

    dbd_store.seed_if_empty()
    print(f"กำลังค้นหา: {query}")
    result = dbd_browser.lookup(query, headless=True)

    summary = build_summary(result)
    print(summary)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(summary + "\n")

    has_data = result.get("tax_id") and (result.get("profile") or result.get("financials"))
    if not has_data:
        print("ERROR: ไม่ได้ข้อมูลจาก DBD", file=sys.stderr)
        return 1
    save_result(result)
    update_seed(result["tax_id"])
    print(f"\nบันทึกแล้ว: {result['tax_id']} -> dbd_data/seed.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
