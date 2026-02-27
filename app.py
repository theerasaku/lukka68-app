import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai

st.set_page_config(page_title="ระบบข้อมูลลูกค้า 68", page_icon="🏗️", layout="wide")

@st.cache_data
def load_data():
    try:
        df = pd.read_csv("lukka68.csv", encoding="utf-8-sig", header=1)
    except:
        df = pd.read_csv("lukka68.csv", encoding="tis-620", header=1)
    cols = list(df.columns)
    rename = {}
    names = ['ลำดับ','บจก','หจก','บมจ','JV','บริษัท','ปีจดทะเบียน','ทุนจดทะเบียน','รายได้รวม','กำไรสุทธิ','pct1','pct2','pct3','pct4','รวมคะแนน','เกรด']
    for i, n in enumerate(names):
        if i < len(cols):
            rename[cols[i]] = n
    df = df.rename(columns=rename)
    df = df.dropna(subset=['บริษัท'])
    df['บริษัท'] = df['บริษัท'].astype(str).str.strip()
    df = df[df['บริษัท'].str.len() > 2]
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
    page = st.radio("เมนู", ["📊 Dashboard","🔍 ค้นหา","📋 สรุปกลุ่ม","💬 AI Chat"])
    st.divider()
    gemini_key = st.text_input("🔑 Gemini API Key", type="password")
    if gemini_key: st.success("✅ ใส่ Key แล้ว")
    else: st.info("ใส่ Key เพื่อใช้ AI")
    st.divider()
    if data_ok: st.success(f"✅ ข้อมูล {len(df)} ราย")
    else: st.error("❌ ไม่พบข้อมูล")

if not data_ok:
    st.error(f"ไม่สามารถโหลดข้อมูล: {err_msg}")
    st.stop()

if page == "📊 Dashboard":
    st.title("📊 Dashboard ภาพรวมลูกค้า")
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
        st.plotly_chart(px.pie(tc,values='จำนวน',names='ประเภท',title='สัดส่วนประเภทบริษัท',hole=0.4), use_container_width=True)
    with cb:
        if 'เกรด' in df.columns:
            gc = df['เกรด'].value_counts().reset_index()
            gc.columns=['เกรด','จำนวน']
            st.plotly_chart(px.bar(gc,x='เกรด',y='จำนวน',title='จำนวนตามเกรด',color='จำนวน',text='จำนวน'), use_container_width=True)
    cc,cd = st.columns(2)
    with cc:
        top10 = df.nlargest(10,'รายได้รวม')[['บริษัท','รายได้รวม']].copy()
        top10['บริษัท'] = top10['บริษัท'].str[:20]
        fig = px.bar(top10,x='รายได้รวม',y='บริษัท',orientation='h',title='Top10 รายได้สูงสุด',color='รายได้รวม')
        fig.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    with cd:
        yc = df.groupby('ปีจดทะเบียน').size().reset_index(name='จำนวน').dropna()
        st.plotly_chart(px.area(yc,x='ปีจดทะเบียน',y='จำนวน',title='บริษัทที่จดทะเบียนแต่ละปี'), use_container_width=True)
    st.subheader("ความสัมพันธ์ ทุน vs รายได้")
    st.plotly_chart(px.scatter(df,x='ทุนจดทะเบียน',y='รายได้รวม',color='ประเภท',hover_name='บริษัท',log_x=True,log_y=True,title='ทุน vs รายได้ (log scale)'), use_container_width=True)

elif page == "🔍 ค้นหา":
    st.title("🔍 ค้นหาลูกค้า")
    c1,c2,c3 = st.columns([2,1,1])
    search = c1.text_input("ค้นหาชื่อบริษัท")
    tf = c2.multiselect("ประเภท", df['ประเภท'].unique(), default=list(df['ประเภท'].unique()))
    gf = c3.multiselect("เกรด", df['เกรด'].dropna().unique() if 'เกรด' in df.columns else [])
    c4,c5 = st.columns(2)
    min_r = c4.number_input("รายได้ขั้นต่ำ (ล้าน)", 0.0, value=0.0)
    filt = df.copy()
    if search: filt = filt[filt['บริษัท'].str.contains(search,na=False,case=False)]
    if tf: filt = filt[filt['ประเภท'].isin(tf)]
    if gf: filt = filt[filt['เกรด'].isin(gf)]
    if min_r > 0: filt = filt[filt['รายได้รวม'] >= min_r]
    st.write(f"พบ **{len(filt)}** รายการ")
    dcols = [c for c in ['ลำดับ','ประเภท','บริษัท','ปีจดทะเบียน','ทุนจดทะเบียน','รายได้รวม','กำไรสุทธิ','รวมคะแนน','เกรด'] if c in filt.columns]
    st.dataframe(filt[dcols].reset_index(drop=True), use_container_width=True, height=450)
    st.download_button("⬇️ ดาวน์โหลด CSV", filt[dcols].to_csv(index=False,encoding='utf-8-sig'), "result.csv", "text/csv")

elif page == "📋 สรุปกลุ่ม":
    st.title("📋 สรุปตามกลุ่ม")
    t1,t2,t3 = st.tabs(["แยกประเภท","แยกเกรด","แยกยุค"])
    with t1:
        s = df.groupby('ประเภท').agg(จำนวน=('บริษัท','count'),รายได้รวม=('รายได้รวม','sum'),รายได้เฉลี่ย=('รายได้รวม','mean'),ทุนเฉลี่ย=('ทุนจดทะเบียน','mean')).round(1).reset_index()
        st.dataframe(s, use_container_width=True)
        st.plotly_chart(px.bar(s,x='ประเภท',y='รายได้รวม',title='รายได้รวมแยกตามประเภท',color='ประเภท',text='รายได้รวม'), use_container_width=True)
    with t2:
        if 'เกรด' in df.columns:
            gs = df.groupby('เกรด').agg(จำนวน=('บริษัท','count'),รายได้เฉลี่ย=('รายได้รวม','mean'),ทุนเฉลี่ย=('ทุนจดทะเบียน','mean')).round(1).reset_index()
            st.dataframe(gs, use_container_width=True)
            if 'รวมคะแนน' in df.columns:
                st.plotly_chart(px.scatter(df,x='รวมคะแนน',y='รายได้รวม',color='เกรด',hover_name='บริษัท',title='คะแนน vs รายได้'), use_container_width=True)
    with t3:
        de = df.dropna(subset=['ปีจดทะเบียน']).copy()
        de['ยุค'] = pd.cut(de['ปีจดทะเบียน'],bins=[2499,2519,2539,2559,2570],labels=['ก่อน2520','2520-2539','2540-2559','2560+'])
        es = de.groupby('ยุค',observed=True).agg(จำนวน=('บริษัท','count'),รายได้เฉลี่ย=('รายได้รวม','mean')).round(1).reset_index()
        st.dataframe(es, use_container_width=True)
        ca,cb = st.columns(2)
        with ca: st.plotly_chart(px.pie(es,values='จำนวน',names='ยุค',title='สัดส่วนตามยุค'), use_container_width=True)
        with cb: st.plotly_chart(px.bar(es,x='ยุค',y='รายได้เฉลี่ย',title='รายได้เฉลี่ยตามยุค',color='ยุค'), use_container_width=True)

elif page == "💬 AI Chat":
    st.title("💬 ถามตอบ AI เกี่ยวกับข้อมูลลูกค้า")
    if not gemini_key:
        st.warning("⚠️ กรุณาใส่ Gemini API Key ในแถบซ้ายมือ")
        st.markdown("รับ Key ฟรีที่: https://aistudio.google.com/apikey")
        st.stop()
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        st.error(f"API Key ไม่ถูกต้อง: {e}")
        st.stop()
    top5 = df.nlargest(5,'รายได้รวม')[['บริษัท','รายได้รวม']].to_string(index=False)
    ctx = f"""คุณคือ AI วิเคราะห์ข้อมูลลูกค้าบริษัทรับเหมาก่อสร้าง ตอบภาษาไทยเสมอ
ข้อมูลสรุป {len(df)} ราย:
- ประเภท: {df['ประเภท'].value_counts().to_dict()}
- เกรด: {df['เกรด'].value_counts().to_dict() if 'เกรด' in df.columns else 'N/A'}
- รายได้รวมทั้งหมด: {df['รายได้รวม'].sum():,.0f} ล้าน
- รายได้เฉลี่ย: {df['รายได้รวม'].mean():,.1f} ล้าน
- ทุนเฉลี่ย: {df['ทุนจดทะเบียน'].mean():,.1f} ล้าน
Top5 รายได้: {top5}"""
    if "msgs" not in st.session_state:
        st.session_state.msgs = [{"role":"assistant","content":f"สวัสดีครับ! มีข้อมูลลูกค้า {len(df)} ราย ถามได้เลย เช่น 'บริษัทไหนรายได้สูงสุด?' หรือ 'สรุปเกรด A++'"}]
    for m in st.session_state.msgs:
        with st.chat_message(m["role"]): st.markdown(m["content"])
    if q := st.chat_input("ถามเกี่ยวกับข้อมูลลูกค้า..."):
        st.session_state.msgs.append({"role":"user","content":q})
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("กำลังคิด..."):
                try:
                    r = model.generate_content(ctx + f"\n\nคำถาม: {q}")
                    ans = r.text
                    st.markdown(ans)
                    st.session_state.msgs.append({"role":"assistant","content":ans})
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาด: {e}")
    if st.button("🗑️ ล้างประวัติ"): st.session_state.msgs = []; st.rerun()
