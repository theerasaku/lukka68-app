import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import requests
import urllib.parse
import json
import time
import io
from boq_shelter import (
    PROJECT_INFO, SECTIONS, build_boq_df, compute_summary,
    CONTINGENCY_PCT, VAT_PCT,
)

st.set_page_config(page_title="ระบบข้อมูลลูกค้า 68", page_icon="🏗️", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1H-MAlMRfzHhJQfHeCUj3_-smdxJcTmR9K2IvgL0vm8k/export?format=csv&gid=1958455392"
DBD_API = "https://datawarehouse.dbd.go.th/api/juristic/search"

@st.cache_data(ttl=3600)
def load_data():
    df = pd.read_csv(SHEET_URL, header=1)
    cols = list(df.columns)
    names = ['ลำดับ','บจก','หจก','บมจ','JV','บริษัท','ปีจดทะเบียน','ทุนจดทะเบียน','รายได้รวม','กำไรสุทธิ','pct1','pct2','pct3','pct4','รวมคะแนน','เกรด']
    rename = {cols[i]: names[i] for i in range(min(len(cols), len(names)))}
    df = df.rename(columns=rename)
    df = df.dropna(subset=['บริษัท'])
    df['บริษัท'] = df['บริษัท'].astype(str).str.strip()
    df = df[df['บริษัท'].str.len() > 2]
    df = df[~df['บริษัท'].isin(['nan','None','บริษัท'])]
    for col in ['ทุนจดทะเบียน','รายได้รวม','กำไรสุทธิ','รวมคะแนน']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df['ปีจดทะเบียน'] = pd.to_numeric(df['ปีจดทะเบียน'], errors='coerce')
    def get_type(row):
        if str(row.get('บจก','')).strip() in ['บจก.','บจก']: return 'บจก.'
        if str(row.get('หจก','')).strip() in ['หจก.','หจก']: return 'หจก.'
        if str(row.get('บมจ','')).strip() in ['บมจ.','บมจ']: return 'บมจ.'
        if str(row.get('JV','')).strip() == 'JV': return 'JV'
        return 'อื่นๆ'
    df['ประเภท'] = df.apply(get_type, axis=1)
    return df

def search_dbd(company_name):
    """ค้นหาบริษัทจาก DBD Open Data API"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Referer': 'https://datawarehouse.dbd.go.th/'
        }
        # ลอง DBD search API
        params = {'keyword': company_name, 'limit': 10}
        resp = requests.get(DBD_API, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data
    except Exception as e:
        pass
    
    # Fallback: ลอง open API อีกตัว
    try:
        url = f"https://datawarehouse.dbd.go.th/api/companyInfo/search?name={urllib.parse.quote(company_name)}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    
    return None

def get_dbd_link(company_name):
    """สร้าง URL ค้นหาตรงใน DBD Datawarehouse"""
    encoded = urllib.parse.quote(company_name)
    return f"https://datawarehouse.dbd.go.th/searchJuristic?juristicName={encoded}"

try:
    df = load_data()
    data_ok = True
except Exception as e:
    data_ok = False
    err_msg = str(e)

with st.sidebar:
    st.title("🏗️ ระบบลูกค้า 68")
    st.divider()
    page = st.radio("📌 เมนู", ["📊 Dashboard","🔍 ค้นหา","📋 สรุปกลุ่ม","🏛️ ค้นหา DBD","💬 AI Chat","🏭 BOQ โรงคลุม Generator"])
    st.divider()
    gemini_key = st.text_input("🔑 Gemini API Key", type="password", help="รับฟรีที่ aistudio.google.com")
    if gemini_key: st.success("✅ ใส่ Key แล้ว")
    else: st.info("ใส่ Key เพื่อใช้ AI Chat")
    st.divider()
    if data_ok:
        st.success(f"✅ ข้อมูล {len(df)} ราย")
        if st.button("🔄 รีเฟรชข้อมูล"):
            st.cache_data.clear()
            st.rerun()
    else:
        st.error("❌ โหลดข้อมูลไม่ได้")

if not data_ok:
    st.error(f"ไม่สามารถโหลดข้อมูล: {err_msg}")
    st.stop()

# ========================== DASHBOARD ==========================
if page == "📊 Dashboard":
    st.title("📊 Dashboard ภาพรวมลูกค้า")
    st.caption(f"ข้อมูลจาก Google Sheet | {len(df):,} บริษัท")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("🏢 ลูกค้าทั้งหมด", f"{len(df):,} ราย")
    c2.metric("💰 รายได้รวม", f"{df['รายได้รวม'].sum():,.0f} ล้าน")
    c3.metric("📈 รายได้เฉลี่ย", f"{df['รายได้รวม'].mean():,.1f} ล้าน")
    c4.metric("🏆 เกรด A++", f"{len(df[df['เกรด']=='A++']) if 'เกรด' in df.columns else '-'} ราย")
    st.divider()
    ca,cb = st.columns(2)
    with ca:
        tc = df['ประเภท'].value_counts().reset_index()
        tc.columns=['ประเภท','จำนวน']
        st.plotly_chart(px.pie(tc,values='จำนวน',names='ประเภท',title='🏢 สัดส่วนประเภทบริษัท',hole=0.4,color_discrete_sequence=px.colors.qualitative.Set3), use_container_width=True)
    with cb:
        if 'เกรด' in df.columns:
            gc = df['เกรด'].value_counts().reset_index()
            gc.columns=['เกรด','จำนวน']
            fig = px.bar(gc,x='เกรด',y='จำนวน',title='🏆 จำนวนตามเกรด',color='จำนวน',color_continuous_scale='Blues',text='จำนวน')
            fig.update_traces(texttemplate='%{text}',textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
    cc,cd = st.columns(2)
    with cc:
        top10 = df.nlargest(10,'รายได้รวม')[['บริษัท','รายได้รวม']].copy()
        top10['บริษัท'] = top10['บริษัท'].str[:22]
        fig = px.bar(top10,x='รายได้รวม',y='บริษัท',orientation='h',title='🥇 Top 10 รายได้สูงสุด (ล้านบาท)',color='รายได้รวม',color_continuous_scale='Greens',text='รายได้รวม')
        fig.update_traces(texttemplate='%{text:,.0f}',textposition='outside')
        fig.update_layout(yaxis={'categoryorder':'total ascending'},height=400)
        st.plotly_chart(fig, use_container_width=True)
    with cd:
        yc = df.groupby('ปีจดทะเบียน').size().reset_index(name='จำนวน').dropna()
        st.plotly_chart(px.area(yc,x='ปีจดทะเบียน',y='จำนวน',title='📅 บริษัทที่จดทะเบียนแต่ละปี',color_discrete_sequence=['#667eea']), use_container_width=True)
    st.subheader("💡 ความสัมพันธ์ ทุนจดทะเบียน vs รายได้รวม")
    # FIX: fillna ก่อนใช้ size เพื่อป้องกัน NaN error
    df_plot = df.copy()
    df_plot['ทุนจดทะเบียน'] = df_plot['ทุนจดทะเบียน'].fillna(1)
    df_plot['รายได้รวม_plot'] = df_plot['รายได้รวม'].fillna(1)
    df_plot = df_plot[df_plot['ทุนจดทะเบียน'] > 0]
    df_plot = df_plot[df_plot['รายได้รวม_plot'] > 0]
    st.plotly_chart(px.scatter(df_plot,x='ทุนจดทะเบียน',y='รายได้รวม',color='ประเภท',hover_name='บริษัท',size='รายได้รวม_plot',size_max=40,log_x=True,log_y=True,title='ทุน vs รายได้ (log scale)'), use_container_width=True)

# ========================== ค้นหา ==========================
elif page == "🔍 ค้นหา":
    st.title("🔍 ค้นหาลูกค้า")
    c1,c2,c3 = st.columns([2,1,1])
    search = c1.text_input("🔎 ค้นหาชื่อบริษัท",placeholder="พิมพ์ชื่อบริษัท...")
    tf = c2.multiselect("ประเภท", df['ประเภท'].unique(), default=list(df['ประเภท'].unique()))
    gf = c3.multiselect("เกรด", df['เกรด'].dropna().unique().tolist() if 'เกรด' in df.columns else [])
    c4,c5 = st.columns(2)
    min_r = c4.number_input("รายได้ขั้นต่ำ (ล้านบาท)", 0.0, value=0.0, step=10.0)
    min_c = c5.number_input("ทุนจดทะเบียนขั้นต่ำ (ล้านบาท)", 0.0, value=0.0, step=10.0)
    filt = df.copy()
    if search: filt = filt[filt['บริษัท'].str.contains(search,na=False,case=False)]
    if tf: filt = filt[filt['ประเภท'].isin(tf)]
    if gf: filt = filt[filt['เกรด'].isin(gf)]
    if min_r > 0: filt = filt[filt['รายได้รวม'] >= min_r]
    if min_c > 0: filt = filt[filt['ทุนจดทะเบียน'] >= min_c]
    st.markdown(f"### พบ **{len(filt)}** รายการ")
    dcols = [c for c in ['ลำดับ','ประเภท','บริษัท','ปีจดทะเบียน','ทุนจดทะเบียน','รายได้รวม','กำไรสุทธิ','รวมคะแนน','เกรด'] if c in filt.columns]
    st.dataframe(filt[dcols].reset_index(drop=True), use_container_width=True, height=450)
    st.download_button("⬇️ ดาวน์โหลดผลการค้นหา CSV", filt[dcols].to_csv(index=False,encoding='utf-8-sig'), "result.csv", "text/csv")

# ========================== สรุปกลุ่ม ==========================
elif page == "📋 สรุปกลุ่ม":
    st.title("📋 สรุปตามกลุ่ม")
    t1,t2,t3,t4 = st.tabs(["🏢 แยกประเภท","🏆 แยกเกรด","📅 แยกยุค","🔬 เปรียบเทียบ"])
    with t1:
        s = df.groupby('ประเภท').agg(จำนวน=('บริษัท','count'),รายได้รวม=('รายได้รวม','sum'),รายได้เฉลี่ย=('รายได้รวม','mean'),ทุนเฉลี่ย=('ทุนจดทะเบียน','mean'),กำไรเฉลี่ย=('กำไรสุทธิ','mean')).round(1).reset_index()
        st.dataframe(s,use_container_width=True)
        fig = px.bar(s,x='ประเภท',y='รายได้รวม',title='รายได้รวมแยกตามประเภท',color='ประเภท',text='รายได้รวม')
        fig.update_traces(texttemplate='%{text:,.0f}',textposition='outside')
        st.plotly_chart(fig,use_container_width=True)
    with t2:
        if 'เกรด' in df.columns:
            gs = df.groupby('เกรด').agg(จำนวน=('บริษัท','count'),รายได้เฉลี่ย=('รายได้รวม','mean'),รายได้รวม=('รายได้รวม','sum'),ทุนเฉลี่ย=('ทุนจดทะเบียน','mean')).round(1).reset_index()
            st.dataframe(gs,use_container_width=True)
            if 'รวมคะแนน' in df.columns:
                # FIX: fillna สำหรับ scatter size
                df_s2 = df.dropna(subset=['รวมคะแนน','รายได้รวม']).copy()
                df_s2['ทุน_plot'] = df_s2['ทุนจดทะเบียน'].fillna(1).clip(lower=1)
                st.plotly_chart(px.scatter(df_s2,x='รวมคะแนน',y='รายได้รวม',color='เกรด',hover_name='บริษัท',title='คะแนน vs รายได้',size='ทุน_plot',size_max=40),use_container_width=True)
    with t3:
        de = df.dropna(subset=['ปีจดทะเบียน']).copy()
        de['ยุค'] = pd.cut(de['ปีจดทะเบียน'],bins=[2499,2519,2539,2559,2570],labels=['ก่อน 2520','2520-2539','2540-2559','2560+'])
        es = de.groupby('ยุค',observed=True).agg(จำนวน=('บริษัท','count'),รายได้เฉลี่ย=('รายได้รวม','mean'),ทุนเฉลี่ย=('ทุนจดทะเบียน','mean')).round(1).reset_index()
        st.dataframe(es,use_container_width=True)
        ca2,cb2 = st.columns(2)
        with ca2: st.plotly_chart(px.pie(es,values='จำนวน',names='ยุค',title='สัดส่วนตามยุค',hole=0.3),use_container_width=True)
        with cb2: st.plotly_chart(px.bar(es,x='ยุค',y='รายได้เฉลี่ย',title='รายได้เฉลี่ยตามยุค',color='ยุค',text='รายได้เฉลี่ย'),use_container_width=True)
    with t4:
        st.subheader("เปรียบเทียบบริษัท (สูงสุด 5 บริษัท)")
        sel = st.multiselect("เลือกบริษัท",df['บริษัท'].tolist(),max_selections=5)
        if sel:
            cdf = df[df['บริษัท'].isin(sel)]
            mets = [m for m in ['ทุนจดทะเบียน','รายได้รวม','กำไรสุทธิ','รวมคะแนน'] if m in cdf.columns]
            fig = go.Figure()
            for _,row in cdf.iterrows():
                fig.add_trace(go.Bar(name=row['บริษัท'][:15],x=mets,y=[row.get(m,0) for m in mets]))
            fig.update_layout(barmode='group',title='เปรียบเทียบข้อมูล')
            st.plotly_chart(fig,use_container_width=True)
            st.dataframe(cdf[['บริษัท','ประเภท']+mets].reset_index(drop=True),use_container_width=True)
        else:
            st.info("เลือกบริษัทที่ต้องการเปรียบเทียบด้านบน")

# ========================== ค้นหา DBD ==========================
elif page == "🏛️ ค้นหา DBD":
    st.title("🏛️ ค้นหาข้อมูลบริษัทจาก DBD")
    st.markdown("""
    ค้นหาข้อมูล **ทุนจดทะเบียน, ปีจดทะเบียน, ประเภทบริษัท, สถานะ** จากกรมพัฒนาธุรกิจการค้า (DBD)
    """)
    st.divider()

    company_input = st.text_input("🔎 พิมพ์ชื่อบริษัทที่ต้องการค้นหา", placeholder="เช่น ซิโน-ไทย, กาญจนสิงขร, CPRAM")

    if company_input:
        col1, col2 = st.columns([1,1])
        with col1:
            search_btn = st.button("🔍 ค้นหาใน DBD", type="primary", use_container_width=True)
        with col2:
            dbd_link = get_dbd_link(company_input)
            st.link_button("🌐 เปิดหน้า DBD โดยตรง", dbd_link, use_container_width=True)

        if search_btn:
            with st.spinner(f"กำลังค้นหา '{company_input}' ใน DBD..."):
                result = search_dbd(company_input)

            if result:
                st.success("✅ พบข้อมูล")
                # แสดงผล raw JSON สำหรับ debug
                if isinstance(result, dict):
                    items = result.get('data', result.get('result', result.get('items', [])))
                elif isinstance(result, list):
                    items = result
                else:
                    items = []

                if items:
                    rows = []
                    for item in items[:10]:
                        row = {
                            'ชื่อบริษัท': item.get('juristicName', item.get('name', item.get('companyName', ''))),
                            'เลขทะเบียน': item.get('juristicId', item.get('registrationNumber', item.get('id', ''))),
                            'ประเภท': item.get('juristicType', item.get('type', '')),
                            'ทุนจดทะเบียน': item.get('registerCapital', item.get('capital', '')),
                            'วันจดทะเบียน': item.get('registerDate', item.get('registrationDate', '')),
                            'สถานะ': item.get('statusCode', item.get('status', '')),
                        }
                        rows.append(row)
                    result_df = pd.DataFrame(rows)
                    st.dataframe(result_df, use_container_width=True)

                    # บันทึกลง session state เพื่อเลือกบันทึก
                    if 'dbd_results' not in st.session_state:
                        st.session_state.dbd_results = []
                    st.session_state.dbd_results = rows

                    st.subheader("💾 บันทึกข้อมูลลง Google Sheet")
                    st.info("ฟีเจอร์นี้กำลังพัฒนา — ขณะนี้สามารถ Export ข้อมูลเป็น CSV ได้")
                    st.download_button(
                        "⬇️ ดาวน์โหลดข้อมูล DBD (CSV)",
                        pd.DataFrame(rows).to_csv(index=False, encoding='utf-8-sig'),
                        f"dbd_{company_input}.csv",
                        "text/csv"
                    )
                else:
                    st.warning("ไม่พบข้อมูลที่ตรงกัน ลองกด 'เปิดหน้า DBD โดยตรง' แล้วค้นหาด้วยตนเอง")
                    with st.expander("🔍 Raw API Response (Debug)"):
                        st.json(result)
            else:
                st.warning("⚠️ ไม่สามารถเชื่อมต่อ DBD API ได้โดยตรง")
                st.markdown(f"""
**วิธีแก้ไข:** กดลิงก์ด้านบนเพื่อค้นหาใน DBD โดยตรง หรือลองค้นหาด้วยชื่อย่อ

🔗 [คลิกค้นหา '{company_input}' ใน DBD Datawarehouse]({dbd_link})
                """)

    st.divider()
    st.subheader("📋 บริษัทในฐานข้อมูลที่ยังไม่มีข้อมูล DBD")
    missing = df[df['ทุนจดทะเบียน'].isna() | (df['ทุนจดทะเบียน'] == 0)][['บริษัท','ประเภท','เกรด']].head(20)
    if len(missing) > 0:
        st.caption(f"พบ {len(df[df['ทุนจดทะเบียน'].isna() | (df['ทุนจดทะเบียน'] == 0)])} บริษัทที่ไม่มีข้อมูลทุนจดทะเบียน")
        for _, row in missing.iterrows():
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"🏢 {row['บริษัท']} ({row['ประเภท']})")
            with col2:
                st.link_button("ค้นหา DBD", get_dbd_link(row['บริษัท']), use_container_width=True)
    else:
        st.success("✅ บริษัททุกรายมีข้อมูลทุนจดทะเบียนครบ")

# ========================== AI CHAT ==========================
elif page == "💬 AI Chat":
    st.title("💬 ถามตอบ AI เกี่ยวกับข้อมูลลูกค้า")
    if not gemini_key:
        st.warning("⚠️ กรุณาใส่ Gemini API Key ในแถบซ้ายมือก่อน")
        st.markdown("รับ Key ฟรีที่: https://aistudio.google.com/apikey")
        st.stop()
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"API Key ไม่ถูกต้อง: {e}")
        st.stop()
    gcol = 'เกรด' if 'เกรด' in df.columns else 'ประเภท'
    top5 = df.nlargest(5,'รายได้รวม')[['บริษัท','รายได้รวม',gcol]].to_string(index=False)
    ctx = f"""คุณคือ AI วิเคราะห์ข้อมูลลูกค้าบริษัทรับเหมาก่อสร้าง ตอบภาษาไทยเสมอ กระชับ ชัดเจน มีประโยชน์
ข้อมูลสรุป {len(df)} ราย:
- ประเภทบริษัท: {df['ประเภท'].value_counts().to_dict()}
- เกรด: {df['เกรด'].value_counts().to_dict() if 'เกรด' in df.columns else 'ไม่มีข้อมูล'}
- รายได้รวมทั้งหมด: {df['รายได้รวม'].sum():,.0f} ล้านบาท
- รายได้เฉลี่ย: {df['รายได้รวม'].mean():,.1f} ล้านบาท
- ทุนจดทะเบียนเฉลี่ย: {df['ทุนจดทะเบียน'].mean():,.1f} ล้านบาท
- ปีก่อตั้งเฉลี่ย: พ.ศ. {df['ปีจดทะเบียน'].mean():.0f}
Top 5 รายได้สูงสุด:
{top5}"""
    if "msgs" not in st.session_state:
        st.session_state.msgs = [{"role":"assistant","content":f"สวัสดีครับ! ผมวิเคราะห์ข้อมูลลูกค้า **{len(df)} ราย** ถามได้เลยครับ เช่น\n- บริษัทไหนรายได้สูงสุด?\n- สรุปลูกค้าเกรด A++\n- บริษัทที่ก่อตั้งนานที่สุด?\n- เปรียบเทียบ บจก. กับ หจก."}]
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    if q := st.chat_input("ถามเกี่ยวกับข้อมูลลูกค้า..."):
        st.session_state.msgs.append({"role":"user","content":q})
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("กำลังวิเคราะห์..."):
                try:
                    r = model.generate_content(ctx + f"\n\nคำถาม: {q}")
                    ans = r.text
                    st.markdown(ans)
                    st.session_state.msgs.append({"role":"assistant","content":ans})
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    col1,col2 = st.columns([1,4])
    with col1:
        if st.button("🗑️ ล้างประวัติ"):
            st.session_state.msgs = []
            st.rerun()

# ========================== BOQ โรงคลุม Generator ==========================
elif page == "🏭 BOQ โรงคลุม Generator":
    st.title("🏭 BOQ โรงคลุมเครื่อง Generator")
    st.caption("ใบถอดแบบปริมาณงานและประมาณราคาก่อสร้าง")

    # ---- ข้อมูลโครงการ ----
    st.subheader("📐 ข้อมูลโครงการ")
    pi_cols = st.columns(len(PROJECT_INFO))
    for col, (k, v) in zip(pi_cols, PROJECT_INFO.items()):
        col.metric(k, v)

    st.divider()

    boq_df = build_boq_df()
    section_totals, subtotal, contingency, before_vat, vat, grand_total = compute_summary(boq_df)

    # ---- แสดงรายการแยกหมวด ----
    st.subheader("📋 รายละเอียด BOQ")
    for sec_code, sec_name, _ in SECTIONS:
        sec_df = boq_df[boq_df["หมวด"] == sec_code].copy()
        sec_total = section_totals.get(sec_code, 0)
        with st.expander(f"**{sec_code} — {sec_name}**　　รวม {sec_total:,.2f} บาท", expanded=True):
            display_df = sec_df[["รหัส","รายการ","หน่วย","ปริมาณ","ราคาต่อหน่วย","จำนวนเงิน","หมายเหตุ"]].copy()
            display_df["ปริมาณ"] = display_df["ปริมาณ"].apply(lambda x: f"{x:,.2f}")
            display_df["ราคาต่อหน่วย"] = display_df["ราคาต่อหน่วย"].apply(lambda x: f"{x:,.2f}")
            display_df["จำนวนเงิน"] = display_df["จำนวนเงิน"].apply(lambda x: f"{x:,.2f}")
            st.dataframe(display_df.reset_index(drop=True), use_container_width=True, hide_index=True)

    st.divider()

    # ---- สรุปยอดรวม ----
    st.subheader("💰 สรุปงบประมาณ")
    sum_col1, sum_col2 = st.columns([1, 1])
    with sum_col1:
        summary_rows = [(sec_code, sec_name, section_totals.get(sec_code, 0)) for sec_code, sec_name, _ in SECTIONS]
        summary_df = pd.DataFrame(summary_rows, columns=["หมวด","รายการ","จำนวนเงิน (บาท)"])
        summary_df["จำนวนเงิน (บาท)"] = summary_df["จำนวนเงิน (บาท)"].apply(lambda x: f"{x:,.2f}")
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
    with sum_col2:
        m1, m2 = st.columns(2)
        m1.metric("รวมก่อน Contingency", f"{subtotal:,.2f} บาท")
        m2.metric(f"สำรองเผื่อ ({int(CONTINGENCY_PCT*100)}%)", f"{contingency:,.2f} บาท")
        m3, m4 = st.columns(2)
        m3.metric("รวมก่อน VAT", f"{before_vat:,.2f} บาท")
        m4.metric(f"VAT ({int(VAT_PCT*100)}%)", f"{vat:,.2f} บาท")
        st.metric("💵 ราคารวมทั้งสิ้น (รวม VAT)", f"{grand_total:,.2f} บาท", delta=None)

    st.divider()

    # ---- กราฟสัดส่วนค่าใช้จ่าย ----
    st.subheader("📊 สัดส่วนค่าใช้จ่ายแต่ละหมวด")
    chart_df = pd.DataFrame([
        {"หมวด": f"{sc} {sn.split('(')[0].strip()}", "จำนวนเงิน": section_totals.get(sc, 0)}
        for sc, sn, _ in SECTIONS
    ])
    pie_fig = px.pie(
        chart_df, values="จำนวนเงิน", names="หมวด",
        title="สัดส่วนงบประมาณแต่ละหมวดงาน",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    pie_fig.update_traces(textposition="inside", textinfo="percent+label")
    pie_fig.update_layout(showlegend=False)
    bar_fig = px.bar(
        chart_df.sort_values("จำนวนเงิน", ascending=True),
        x="จำนวนเงิน", y="หมวด", orientation="h",
        title="ค่าใช้จ่ายแต่ละหมวดงาน (บาท)",
        color="จำนวนเงิน", color_continuous_scale="Blues",
        text="จำนวนเงิน",
    )
    bar_fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    bar_fig.update_layout(height=420, coloraxis_showscale=False)
    gc1, gc2 = st.columns(2)
    with gc1:
        st.plotly_chart(pie_fig, use_container_width=True)
    with gc2:
        st.plotly_chart(bar_fig, use_container_width=True)

    st.divider()

    # ---- Export Excel ----
    st.subheader("⬇️ ดาวน์โหลด BOQ")

    @st.cache_data
    def to_excel_bytes(df, sec_totals, subtotal_, contingency_, before_vat_, vat_, grand_total_):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            # Sheet 1: รายละเอียดทั้งหมด
            detail = df[["หมวด","รหัส","รายการ","หน่วย","ปริมาณ","ราคาต่อหน่วย","จำนวนเงิน","หมายเหตุ"]].copy()
            detail.to_excel(writer, index=False, sheet_name="BOQ รายละเอียด", startrow=5)
            ws = writer.sheets["BOQ รายละเอียด"]
            ws["A1"] = "BOQ โรงคลุมเครื่อง Generator"
            ws["A2"] = "ขนาด 2.00 × 8.00 m สูง 2.30 m"
            ws["A3"] = f"ราคารวม VAT: {grand_total_:,.2f} บาท"
            ws["A4"] = ""

            # Sheet 2: สรุปหมวด
            sum_rows = [{"หมวด": sc, "รายการ": sn, "จำนวนเงิน (บาท)": sec_totals.get(sc, 0)} for sc, sn, _ in SECTIONS]
            sum_rows.append({"หมวด": "", "รายการ": "รวมทั้งหมด", "จำนวนเงิน (บาท)": subtotal_})
            sum_rows.append({"หมวด": "", "รายการ": f"สำรองเผื่อ {int(CONTINGENCY_PCT*100)}%", "จำนวนเงิน (บาท)": contingency_})
            sum_rows.append({"หมวด": "", "รายการ": "รวมก่อน VAT", "จำนวนเงิน (บาท)": before_vat_})
            sum_rows.append({"หมวด": "", "รายการ": f"VAT {int(VAT_PCT*100)}%", "จำนวนเงิน (บาท)": vat_})
            sum_rows.append({"หมวด": "", "รายการ": "ราคารวมทั้งสิ้น (รวม VAT)", "จำนวนเงิน (บาท)": grand_total_})
            pd.DataFrame(sum_rows).to_excel(writer, index=False, sheet_name="สรุปงบประมาณ")
        return buf.getvalue()

    excel_bytes = to_excel_bytes(boq_df, section_totals, subtotal, contingency, before_vat, vat, grand_total)
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 ดาวน์โหลด BOQ (.xlsx)",
            data=excel_bytes,
            file_name="BOQ_Generator_Shelter_2x8m.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with dl2:
        csv_bytes = boq_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "📥 ดาวน์โหลด BOQ (.csv)",
            data=csv_bytes,
            file_name="BOQ_Generator_Shelter_2x8m.csv",
            mime="text/csv",
            use_container_width=True,
        )
