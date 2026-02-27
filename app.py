import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai

st.set_page_config(page_title="ระบบข้อมูลลูกค้า 68", page_icon="🏗️", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1H-MAlMRfzHhJQfHeCUj3_-smdxJcTmR9K2IvgL0vm8k/export?format=csv&gid=1958455392"

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

try:
    df = load_data()
    data_ok = True
except Exception as e:
    data_ok = False
    err_msg = str(e)

with st.sidebar:
    st.title("🏗️ ระบบลูกค้า 68")
    st.divider()
    page = st.radio("📌 เมนู", ["📊 Dashboard","🔍 ค้นหา","📋 สรุปกลุ่ม","💬 AI Chat"])
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
    st.plotly_chart(px.scatter(df,x='ทุนจดทะเบียน',y='รายได้รวม',color='ประเภท',hover_name='บริษัท',size='รายได้รวม',size_max=40,log_x=True,log_y=True,title='ทุน vs รายได้ (log scale)'), use_container_width=True)

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
                st.plotly_chart(px.scatter(df,x='รวมคะแนน',y='รายได้รวม',color='เกรด',hover_name='บริษัท',title='คะแนน vs รายได้',size='ทุนจดทะเบียน',size_max=40),use_container_width=True)
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

elif page == "💬 AI Chat":
    st.title("💬 ถามตอบ AI เกี่ยวกับข้อมูลลูกค้า")
    if not gemini_key:
        st.warning("⚠️ กรุณาใส่ Gemini API Key ในแถบซ้ายมือก่อน")
        st.markdown("""
**วิธีรับ Key ฟรี:**
1. ไปที่ [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Login ด้วย Google Account
3. กด **Create API key**
4. Copy มาวางในช่อง API Key ซ้ายมือ
        """)
        st.stop()
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"API Key ไม่ถูกต้อง: {e}")
        st.stop()
    top5 = df.nlargest(5,'รายได้รวม')[['บริษัท','รายได้รวม','เกรด' if 'เกรด' in df.columns else 'ประเภท']].to_string(index=False)
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
