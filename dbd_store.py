"""ฐานข้อมูล SQLite เก็บข้อมูลบริษัทจาก DBD Datawarehouse (ทุนจดทะเบียน, กรรมการ, งบการเงินรายปี)
เพื่อเรียกใช้ซ้ำในแอป โดยไม่ต้องพึ่งการดึงข้อมูลสดจาก datawarehouse.dbd.go.th ซึ่งมักถูกบล็อก/ไม่เสถียร
"""
import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "dbd_data", "dbd.sqlite3")
SEED_PATH = os.path.join(os.path.dirname(__file__), "dbd_data", "seed.json")

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    tax_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    juristic_type TEXT,
    registered_capital REAL,
    registration_year INTEGER,
    address TEXT,
    directors TEXT,
    source TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS financials (
    tax_id TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    revenue_main REAL,
    revenue_total REAL,
    cost_of_sales REAL,
    gross_profit REAL,
    sga_expense REAL,
    total_expense REAL,
    interest_expense REAL,
    profit_before_tax REAL,
    income_tax REAL,
    net_profit REAL,
    PRIMARY KEY (tax_id, fiscal_year),
    FOREIGN KEY (tax_id) REFERENCES companies(tax_id)
);
"""


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert_company(tax_id, company_name, juristic_type=None, registered_capital=None,
                    registration_year=None, address=None, directors=None, source=None):
    conn = get_connection()
    conn.execute(
        """INSERT INTO companies
           (tax_id, company_name, juristic_type, registered_capital, registration_year, address, directors, source, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(tax_id) DO UPDATE SET
             company_name=excluded.company_name,
             juristic_type=excluded.juristic_type,
             registered_capital=excluded.registered_capital,
             registration_year=excluded.registration_year,
             address=excluded.address,
             directors=excluded.directors,
             source=excluded.source,
             updated_at=excluded.updated_at""",
        (tax_id, company_name, juristic_type, registered_capital, registration_year,
         address, directors, source, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def upsert_financial(tax_id, fiscal_year, **fields):
    """fields: revenue_main, revenue_total, cost_of_sales, gross_profit, sga_expense,
    total_expense, interest_expense, profit_before_tax, income_tax, net_profit"""
    cols = ["revenue_main", "revenue_total", "cost_of_sales", "gross_profit", "sga_expense",
            "total_expense", "interest_expense", "profit_before_tax", "income_tax", "net_profit"]
    values = [fields.get(c) for c in cols]
    conn = get_connection()
    conn.execute(
        f"""INSERT INTO financials (tax_id, fiscal_year, {", ".join(cols)})
            VALUES (?, ?, {", ".join(["?"] * len(cols))})
            ON CONFLICT(tax_id, fiscal_year) DO UPDATE SET
              {", ".join(f"{c}=excluded.{c}" for c in cols)}""",
        [tax_id, fiscal_year] + values,
    )
    conn.commit()
    conn.close()


def get_company(tax_id):
    conn = get_connection()
    company = conn.execute("SELECT * FROM companies WHERE tax_id = ?", (tax_id,)).fetchone()
    financials = conn.execute(
        "SELECT * FROM financials WHERE tax_id = ? ORDER BY fiscal_year", (tax_id,)
    ).fetchall()
    conn.close()
    if not company:
        return None
    return {"company": dict(company), "financials": [dict(f) for f in financials]}


def search_companies(keyword=""):
    conn = get_connection()
    if keyword:
        rows = conn.execute(
            "SELECT * FROM companies WHERE company_name LIKE ? OR tax_id LIKE ? ORDER BY company_name",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM companies ORDER BY company_name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_company(tax_id):
    """ลบบริษัทและงบการเงินทั้งหมดของบริษัทนั้น"""
    conn = get_connection()
    conn.execute("DELETE FROM financials WHERE tax_id = ?", (tax_id,))
    conn.execute("DELETE FROM companies WHERE tax_id = ?", (tax_id,))
    conn.commit()
    conn.close()


def seed_if_empty():
    """โหลดข้อมูลตั้งต้นจาก dbd_data/seed.json เข้า SQLite ถ้ายังไม่เคยมีบริษัทนั้นอยู่"""
    if not os.path.exists(SEED_PATH):
        return
    with open(SEED_PATH, encoding="utf-8") as f:
        seed = json.load(f)
    conn = get_connection()
    for c in seed.get("companies", []):
        exists = conn.execute("SELECT 1 FROM companies WHERE tax_id = ?", (c["tax_id"],)).fetchone()
        if exists:
            continue
        conn.close()
        upsert_company(
            tax_id=c["tax_id"],
            company_name=c["company_name"],
            juristic_type=c.get("juristic_type"),
            registered_capital=c.get("registered_capital"),
            registration_year=c.get("registration_year"),
            address=c.get("address"),
            directors=c.get("directors"),
            source=c.get("source"),
        )
        for fy in c.get("financials", []):
            upsert_financial(c["tax_id"], fy["fiscal_year"], **{k: v for k, v in fy.items() if k != "fiscal_year"})
        conn = get_connection()
    conn.close()
