"""แอพค้นหาข้อมูลบริษัทจาก DBD Datawarehouse
ดึง รายได้ กำไร ปีจดทะเบียน ทุนจดทะเบียน กรรมการ แล้วบันทึกลง SQLite เพื่อเรียกใช้ซ้ำ

รัน: streamlit run dbd_app.py
"""
import urllib.parse

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import dbd_client
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


def save_fetch_result(tax_id, result):
    """บันทึกผลจาก dbd_client.fetch_company ลง SQLite คืนจำนวนปีงบที่บันทึก"""
    profile = dbd_client.normalize_profile(result.get("profile") or {})
    dbd_store.upsert_company(
        tax_id=tax_id,
        company_name=profile.get("company_name") or f"(ไม่ทราบชื่อ) {tax_id}",
        juristic_type=profile.get("juristic_type"),
        registered_capital=profile.get("registered_capital"),
        registration_year=profile.get("registration_year"),
        address=profile.get("address"),
        directors=profile.get("directors"),
        source=result.get("profile_source") or "datawarehouse.dbd.go.th",
    )
    fin_rows = dbd_client.normalize_financials(result.get("financials"))
    for row in fin_rows:
        dbd_store.upsert_financial(tax_id, row.pop("fiscal_year"), **row)
    return len(fin_rows)


st.title("🏛️ DBD Company Lookup")
st.caption("ค้นหา รายได้ กำไร ปีจดทะเบียน ทุนจดทะเบียน กรรมการ จาก datawarehouse.dbd.go.th "
           "— ผลลัพธ์ถูกบันทึกลงฐานข้อมูลในเครื่อง (SQLite) เพื่อเรียกใช้ซ้ำได้แม้ DBD ล่ม")

tab_live, tab_saved = st.tabs(["🌐 ดึงข้อมูลสดจาก DBD", "💾 ฐานข้อมูลที่บันทึกไว้"])

# ---------------- ดึงสดจาก DBD ----------------
with tab_live:
    st.markdown("ใส่ **ชื่อบริษัท**, **เลขทะเบียนนิติบุคคล 13 หลัก** หรือวาง **URL หน้าโปรไฟล์ DBD** "
                "(เช่น `https://datawarehouse.dbd.go.th/company/profile/50105534106050`)")
    query = st.text_input("🔎 ค้นหา", placeholder="ธรรมสรณ์ หรือ 0105534106050 หรือ URL โปรไฟล์ DBD")

    if query:
        tax_id, _ = dbd_client.extract_juristic_id(query)

        # กรณีเป็นชื่อบริษัท: ค้นหาก่อนเพื่อให้เลือกเลขทะเบียน
        if not tax_id:
            if st.button("🔍 ค้นหาชื่อใน DBD", type="primary"):
                with st.spinner("กำลังค้นหาใน DBD..."):
                    session = dbd_client.make_session()
                    results, info = dbd_client.search_juristic(query, session)
                st.session_state.pop("dbd_search_results", None)
                if results:
                    st.session_state.dbd_search_results = results
                    st.caption(f"endpoint ที่ใช้: {info}")
                else:
                    st.error(f"ค้นหาไม่สำเร็จ: {info}")
                    st.markdown(
                        f"เปิดค้นหาบนเว็บ DBD โดยตรง: "
                        f"[คลิกที่นี่](https://datawarehouse.dbd.go.th/searchJuristic?juristicName={urllib.parse.quote(query)}) "
                        "แล้วนำเลขทะเบียน 13 หลัก หรือ URL โปรไฟล์ กลับมาวางในช่องค้นหา")
            results = st.session_state.get("dbd_search_results")
            if results:
                options = {}
                for r in results[:20]:
                    if isinstance(r, dict):
                        name = r.get("juristicName") or r.get("name") or str(r)[:60]
                        jid = r.get("juristicID") or r.get("juristicId") or r.get("id") or ""
                        options[f"{name} ({jid})"] = jid
                picked = st.selectbox("เลือกบริษัทจากผลค้นหา", list(options.keys()))
                tax_id, _ = dbd_client.extract_juristic_id(options[picked])

        if tax_id:
            st.info(f"เลขทะเบียนนิติบุคคล: **{tax_id}**")
            if st.button("⬇️ ดึงข้อมูลจาก DBD และบันทึก", type="primary"):
                with st.spinner(f"กำลังดึงข้อมูล {tax_id} จาก DBD..."):
                    result = dbd_client.fetch_company(tax_id)
                got_profile = result.get("profile") is not None
                got_fin = result.get("financials") is not None
                if got_profile or got_fin:
                    n_years = save_fetch_result(tax_id, result)
                    st.success(f"✅ บันทึกแล้ว (งบการเงิน {n_years} ปี)")
                    for err in result.get("errors", []):
                        st.warning(err)
                    with st.expander("Raw response (debug)"):
                        st.json({k: v for k, v in result.items() if k in ("profile", "financials",
                                 "profile_source", "financial_source")})
                    detail = dbd_store.get_company(tax_id)
                    if detail:
                        show_company(detail)
                else:
                    st.error("ไม่สามารถดึงข้อมูลจาก DBD ได้")
                    for err in result.get("errors", []):
                        st.caption(err)
                    st.markdown(f"""
**สาเหตุที่พบบ่อย:** DBD บล็อกการเรียกอัตโนมัติ / เปลี่ยน endpoint / เครือข่ายเข้าถึงไม่ได้

**ทางเลือก:** เปิด [หน้าโปรไฟล์บน DBD](https://datawarehouse.dbd.go.th/company/profile/5{tax_id})
ดูข้อมูลแล้วบันทึกด้วยตนเองในแท็บ "ฐานข้อมูลที่บันทึกไว้" — ข้อมูลจะถูกเก็บไว้เรียกใช้ซ้ำเหมือนกัน""")

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
