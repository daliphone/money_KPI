import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# --- 1. 頁面設定 ---
st.set_page_config(page_title="東門店業績戰情室", layout="wide", page_icon="🏆")

# 自訂 CSS 美化
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
    }
    .stMetric {
        background-color: transparent !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("🏆 東門店 - 業績動能戰情室")
st.markdown(f"**資料更新時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
st.markdown("---")

# --- 2. 讀取資料函數 ---
@st.cache_data  # 加入快取機制，讓網頁跑更快
def load_data():
    # 這裡預設讀取同目錄下的 data.xlsx
    # 在實際 Excel 中，請確保有一個總表 Sheet 或是已經合併好的結構
    # 這裡我們模擬一個 DataFrame 結構，因為我沒有你合併後的真實檔案
    # ★重要★：實際上線時，請把下面這段註解掉，改用 pd.read_excel('data.xlsx')
    
    # 模擬數據 (請用你的 pd.read_excel('data.xlsx') 取代)
    data = {
        '人員': ['東門店(全店)', '914', '默默', '小萬', '人員4'],
        '毛利_目標': [462000, 140000, 140000, 140000, 42000],
        '毛利_目前': [158000, 52000, 31000, 65000, 10000],
        '門號_目標': [84, 24, 24, 24, 12],
        '門號_目前': [30, 10, 5, 12, 3],
        '生活圈_目標': [90, 25, 25, 25, 15],
        '生活圈_目前': [45, 15, 10, 15, 5]
    }
    df = pd.DataFrame(data)
    
    # 計算全月天數與剩餘天數 (自動化)
    today = datetime.now()
    # 假設目標是本月
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    remaining_days = last_day - today.day
    if remaining_days < 0: remaining_days = 0 # 防止月底變成負數
    
    return df, remaining_days

try:
    # 嘗試讀取資料
    df, remaining_days = load_data()
except Exception as e:
    st.error(f"資料讀取失敗，請檢查 Excel 檔案是否上傳。錯誤訊息: {e}")
    st.stop()

# --- 3. 側邊欄篩選 ---
st.sidebar.header("🔍 戰情室篩選")
selected_user = st.sidebar.selectbox("選擇人員 / 店鋪", df['人員'])

# 篩選該員數據
user_data = df[df['人員'] == selected_user].iloc[0]

# --- 4. 核心指標區 ---
col1, col2, col3, col4 = st.columns(4)

# 計算達成率
毛利達成率 = (user_data['毛利_目前'] / user_data['毛利_目標']) * 100
門號達成率 = (user_data['門號_目前'] / user_data['門號_目標']) * 100

# 動能計算 (動態)
毛利缺口 = user_data['毛利_目標'] - user_data['毛利_目前']
if 毛利缺口 < 0: 毛利缺口 = 0
每日需達毛利 = 毛利缺口 / remaining_days if remaining_days > 0 else 毛利缺口

with col1:
    st.metric(label="💰 目前毛利", value=f"${user_data['毛利_目前']:,}", delta=f"{毛利達成率:.1f}% 達成")
with col2:
    st.metric(label="📱 目前門號", value=f"{user_data['門號_目前']} 件", delta=f"{門號達成率:.1f}% 達成")
with col3:
    st.metric(label="🔥 今日動能 (毛利)", value=f"${int(每日需達毛利):,}", delta="每日必達", delta_color="inverse")
with col4:
    st.metric(label="📅 本月剩餘天數", value=f"{remaining_days} 天")

st.markdown("---")

# --- 5. 視覺化儀表板 (Bullet Chart) ---
st.subheader(f"📊 {selected_user} - 關鍵指標達成進度 (目標 115%)")

def create_bullet_chart(title, value, target):
    score = (value / target) * 100
    fig = go.Figure(go.Indicator(
        mode = "number+gauge+delta", value = score,
        delta = {'reference': 100, 'position': "top"},
        title = {'text': title},
        gauge = {
            'shape': "bullet",
            'axis': {'range': [0, 130]},
            'threshold': {'line': {'color': "red", 'width': 2}, 'thickness': 0.75, 'value': 100},
            'steps': [
                {'range': [0, 80], 'color': "lightgray"},
                {'range': [80, 100], 'color': "gray"},
                {'range': [100, 115], 'color': "#90EE90"}, # 淺綠色激勵區
                {'range': [115, 130], 'color': "#FFD700"}], # 金色榮耀區
            'bar': {'color': "black"}
        }
    ))
    fig.update_layout(height=250, margin={'t':20, 'b':20, 'l':20, 'r':20})
    return fig

c1, c2, c3 = st.columns(3)
with c1:
    st.plotly_chart(create_bullet_chart("毛利達成率", user_data['毛利_目前'], user_data['毛利_目標']), use_container_width=True)
with c2:
    st.plotly_chart(create_bullet_chart("門號達成率", user_data['門號_目前'], user_data['門號_目標']), use_container_width=True)
with c3:
    st.plotly_chart(create_bullet_chart("生活圈達成率", user_data['生活圈_目前'], user_data['生活圈_目標']), use_container_width=True)

# --- 6. 原始數據區 ---
with st.expander("查看原始報表數據"):
    st.dataframe(df)