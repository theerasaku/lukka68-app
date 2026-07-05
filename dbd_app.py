"""แอพค้นหาข้อมูลบริษัทจาก DBD Datawarehouse
ดึง รายได้ กำไร ปีจดทะเบียน ทุนจดทะเบียน กรรมการ แล้วบันทึกลง SQLite เพื่อเรียกใช้ซ้ำ

รัน: streamlit run dbd_app.py
"""
import glob
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dbd_store

st.set_page_config(page_title="DBD Company Lookup", page_icon="🏛️", layout="wide")
dbd_store.seed_if_empty()

FIN_LABELS = {
    "fiscal_year": "ปี", "revenue_main": "รายได้หลัก", "revenue_total": "รายได้รวม",
    "cost_of_sales": "ต้นทุนขาย", "gross_profit": "กำไรขั้นต้น",
    "sga_expense": "ค่าใช้จ่ายขายและบริการ", "total_expense": "รายจ่ายรวม",
    "interest_expense": "ดอกเบี้ยจ่าย", "profit_before_tax": "กำไรก่อนภาษี",
    "income_tax": "ภาษีเงินได้", "net_profit": "กำไรสุทธิ",
}


def show_company(detail):
    """แสดงข้อมูลบริษัท + งบการเงินจาก dict ของ dbd_store.get_company"""
    c = detail["company"]
    st.subheader(f"🏢 {c['company_name']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ทุนจดทะเบียน", f"{(c['registered_capital'] or 0):,.0f} บาท")
    m2.metric("ปีจดทะเบียน", f"พ.ศ. {c['registration_year']}" if c["registration_year"] else "-")
    m3.metric("ประเภท", c["juristic_type"] or "-")
    m4.metric("เลขทะเบียน", c["tax_id"])
    st.write(f"**กรรมการ:** {c['directors'] or '-'}")
    if c.get("address"):
        st.write(f"**ที่อยู่:** {c['address']}")
    if c.get("source"):
        st.caption(f"แหล่งข้อมูล: {c['source']} | อัปเดตล่าสุด: {c.get('updated_at', '-')}")

    fin = detail["financials"]
    if not fin:
        st.info("ยังไม่มีข้อมูลงบการเงินของบริษัทนี้")
        return
    st.markdown("#### 📊 งบการเงินรายปี")
    fin_df = pd.DataFrame(fin).drop(columns=["tax_id"]).rename(columns=FIN_LABELS)
    st.dataframe(fin_df, use_container_width=True)

    g1, g2 = st.columns(2)
    with g1:
        fig = go.Figure()
        fig.add_trace(go.Bar(name="รายได้รวม", x=fin_df["ปี"], y=fin_df["รายได้รวม"]))
        fig.add_trace(go.Bar(name="กำไรสุทธิ", x=fin_df["ปี"], y=fin_df["กำไรสุทธิ"]))
        fig.update_layout(barmode="group", title="รายได้รวม vs กำไรสุทธิ")
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        margin = (fin_df["กำไรสุทธิ"] / fin_df["รายได้รวม"] * 100).round(2)
        fig2 = go.Figure(go.Scatter(x=fin_df["ปี"], y=margin, mode="lines+markers+text",
                                    text=[f"{v}%" for v in margin], textposition="top center"))
        fig2.update_layout(title="อัตรากำไรสุทธิ (%)", yaxis_title="%")
        st.plotly_chart(fig2, use_container_width=True)

    st.download_button(
        "⬇️ ดาวน์โหลดงบการเงิน (CSV)",
        fin_df.to_csv(index=False, encoding="utf-8-sig"),
        f"dbd_{c['tax_id']}_financials.csv", "text/csv",
    )

    shots = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "dbd_data", "screenshots",
                                          f"{c['tax_id']}_*.png")))
    if shots:
        with st.expander(f"📸 สกรีนช็อตจากเว็บ DBD ({len(shots)} รูป)"):
            for shot in shots:
                st.image(shot, caption=os.path.basename(shot), use_container_width=True)


def save_browser_result(result):
    """บันทึกผลจาก dbd_browser.lookup ลง SQLite คืนจำนวนปีงบที่บันทึก"""
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
        source="datawarehouse.dbd.go.th (Chrome)",
    )
    fin_rows = result.get("financials") or []
    for row in fin_rows:
        row = dict(row)
        dbd_store.upsert_financial(tax_id, row.pop("fiscal_year"), **row)
    return len(fin_rows)


st.title("🏛️ DBD Company Lookup")
st.caption("ค้นหา รายได้ กำไร ปีจดทะเบียน ทุนจดทะเบียน กรรมการ จาก datawarehouse.dbd.go.th "
           "— ผลลัพธ์ถูกบันทึกลงฐานข้อมูลในเครื่อง (SQLite) เพื่อเรียกใช้ซ้ำได้แม้ DBD ล่ม")

tab_live, tab_saved = st.tabs(["🖥️ ดึงข้อมูลผ่าน Chrome", "💾 ฐานข้อมูลที่บันทึกไว้"])

# ---------------- ดึงผ่าน Chrome ----------------
with tab_live:
    st.markdown("""แอพจะ**เปิด Chrome จริง** เข้าเว็บ DBD พิมพ์ค้นหา แคปหน้าจอ แล้วแกะข้อมูลบันทึกลงฐานข้อมูลอัตโนมัติ
(เบราว์เซอร์จริงผ่านระบบกันบอทของ DBD ได้ ต่างจากการยิง API ที่โดน 403)

ใส่ **ชื่อบริษัท**, **เลขทะเบียน 13 หลัก** หรือวาง **URL โปรไฟล์ DBD** ก็ได้""")
    query = st.text_input("🔎 ค้นหา", placeholder="ธรรมสรณ์ หรือ 0105534106050 หรือ URL โปรไฟล์ DBD")
    show_window = st.checkbox("แสดงหน้าต่าง Chrome ขณะทำงาน", value=True,
                              help="เปิดไว้จะเห็น Chrome ทำงานจริง และช่วยผ่านระบบกันบอทได้ดีกว่า")

    if query and st.button("🖥️ เปิด Chrome ดึงข้อมูลและบันทึก", type="primary"):
        try:
            import dbd_browser
        except ImportError:
            st.error("ยังไม่ได้ติดตั้ง Playwright — รันคำสั่งนี้ใน Terminal ก่อน:")
            st.code("python3 -m pip install playwright", language="bash")
            st.stop()
        with st.spinner("Chrome กำลังเข้าเว็บ DBD ค้นหา และแคปหน้าจอ... (ราว 15-30 วินาที)"):
            try:
                result = dbd_browser.lookup(query, headless=not show_window)
            except Exception as e:
                st.error(f"เปิด Chrome ไม่สำเร็จ: {e}")
                st.markdown("ถ้าข้อความบอกว่าหา Chrome/Chromium ไม่เจอ รันคำสั่งนี้แล้วลองใหม่:")
                st.code("python3 -m playwright install chromium", language="bash")
                st.stop()

        if result.get("error"):
            st.warning(f"⚠️ {result['error']}")

        if result.get("tax_id") and (result.get("profile") or result.get("financials")):
            n_years = save_browser_result(result)
            st.success(f"✅ บันทึกลงฐานข้อมูลแล้ว (งบการเงิน {n_years} ปี)")
            if result.get("profile", {}).get("status"):
                st.info(f"สถานะนิติบุคคล: {result['profile']['status']}")

            if result.get("screenshots"):
                st.markdown("#### 📸 หน้าจอที่แคปจากเว็บ DBD")
                for shot in result["screenshots"]:
                    st.image(shot, caption=os.path.basename(shot), use_container_width=True)

            with st.expander("ข้อมูลดิบที่แกะได้ (debug)"):
                st.json({"profile": result.get("profile"), "financials": result.get("financials")})

            detail = dbd_store.get_company(result["tax_id"])
            if detail:
                show_company(detail)
        elif not result.get("error"):
            st.error("แกะข้อมูลจากหน้าเว็บไม่ได้ — ดูสกรีนช็อตด้านล่างว่าหน้าเว็บแสดงอะไร")
            for shot in result.get("screenshots", []):
                st.image(shot, caption=os.path.basename(shot), use_container_width=True)

# ---------------- ฐานข้อมูลที่บันทึกไว้ ----------------
with tab_saved:
    kw = st.text_input("🔎 ค้นหาในฐานข้อมูล", placeholder="ชื่อบริษัท หรือ เลขทะเบียน", key="saved_search")
    companies = dbd_store.search_companies(kw)
    if companies:
        st.caption(f"พบ {len(companies)} บริษัทในฐานข้อมูล")
        names = [f"{c['company_name']} ({c['tax_id']})" for c in companies]
        picked = st.selectbox("เลือกบริษัท", names)
        detail = dbd_store.get_company(companies[names.index(picked)]["tax_id"])
        show_company(detail)
    else:
        st.info("ไม่พบบริษัทในฐานข้อมูล — ดึงข้อมูลจากแท็บแรก หรือเพิ่มด้วยตนเองด้านล่าง")

    with st.expander("➕ เพิ่ม / แก้ไขข้อมูลด้วยตนเอง"):
        with st.form("manual_company"):
            st.markdown("**ข้อมูลนิติบุคคล**")
            f_tax = st.text_input("เลขทะเบียนนิติบุคคล (13 หลัก)")
            f_name = st.text_input("ชื่อบริษัท")
            f_type = st.selectbox("ประเภท", ["บจก.", "หจก.", "บมจ.", "JV", "อื่นๆ"])
            f_cap = st.number_input("ทุนจดทะเบียน (บาท)", min_value=0.0, step=100000.0)
            f_year = st.number_input("ปีจดทะเบียน (พ.ศ.)", min_value=2400, max_value=2600, value=2534)
            f_dir = st.text_input("กรรมการ")
            f_addr = st.text_input("ที่อยู่")
            if st.form_submit_button("💾 บันทึกข้อมูลนิติบุคคล"):
                if f_tax and f_name:
                    dbd_store.upsert_company(
                        tax_id=f_tax.strip(), company_name=f_name.strip(), juristic_type=f_type,
                        registered_capital=f_cap or None, registration_year=int(f_year),
                        address=f_addr or None, directors=f_dir or None, source="กรอกด้วยตนเอง")
                    st.success("บันทึกแล้ว")
                    st.rerun()
                else:
                    st.error("กรุณากรอกเลขทะเบียนและชื่อบริษัท")
        st.markdown("---")
        with st.form("manual_fin"):
            st.markdown("**งบการเงินรายปี**")
            g_tax = st.text_input("เลขทะเบียนนิติบุคคล")
            g_year = st.number_input("ปี (พ.ศ.)", min_value=2400, max_value=2600, value=2568)
            g_rev = st.number_input("รายได้รวม (บาท)", step=1000.0, format="%.2f")
            g_net = st.number_input("กำไรสุทธิ (บาท)", step=1000.0, format="%.2f")
            if st.form_submit_button("💾 บันทึกงบการเงิน"):
                if g_tax:
                    dbd_store.upsert_financial(g_tax.strip(), int(g_year),
                                               revenue_total=g_rev or None, net_profit=g_net or None)
                    st.success("บันทึกแล้ว")
                    st.rerun()
                else:
                    st.error("กรุณากรอกเลขทะเบียนนิติบุคคล")
