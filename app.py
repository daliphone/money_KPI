import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, date
import calendar

# --- 1. 系統設定與模擬資料庫 ---
st.set_page_config(page_title="東門店業績管理系統", layout="wide", page_icon="📈")

# 初始化 Session State (模擬資料庫，讓網頁重新整理後資料還在)
# 未來這一步會換成連接 Google Sheets
if 'db' not in st.session_state:
    # 建立模擬的目標設定 (對應 Excel 上半部目標區)
    st.session_state.targets = {
        '小萬': {'毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21},
        '914':  {'毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21},
        '默默': {'毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21},
        '東門店': {'毛利': 462000, '門號': 84, '保險': 105000, '配件': 126000, '庫存': 56} # 店總目標
    }
    
    # 建立模擬的每日業績紀錄 (對應 Excel 下半部填寫區)
    # 格式: [日期, 毛利, 門號, 保險, 配件, 庫存]
    st.session_state.records = pd.DataFrame(columns=['人員', '日期', '毛利', '門號', '保險', '配件', '庫存'])

# --- 2. 左側導航：門市與人員選擇 ---
st.sidebar.title("🏢 門市管理系統")

# 定義組織架構
org_structure = {
    "台南區": {
        "東門店": ["小萬", "914", "默默", "人員4"],
        "西門店": ["店長A", "組員B"] # 範例，可擴充
    }
}

# 第一層：選擇區域 (預留擴充)
region = "台南區" 

# 第二層：選擇門市
selected_store = st.sidebar.selectbox("請選擇門市", list(org_structure[region].keys()))

# 第三層：選擇人員 (包含「全店總表」選項)
staff_list = ["全店總表"] + org_structure[region][selected_store]
selected_user = st.sidebar.selectbox("請選擇人員", staff_list)

st.sidebar.markdown("---")
st.sidebar.info(f"目前操作身份：\n**{selected_store} - {selected_user}**")

# --- 3. 頂部：資料輸入區 (針對個人) ---
# 只有選擇「個人」時才顯示輸入框，選「全店總表」時不顯示
if selected_user != "全店總表":
    with st.expander("📝 **每日業績回報 (點擊展開)**", expanded=True):
        st.write(f"正在填寫：**{selected_user}** 的業績紀錄")
        
        with st.form("daily_report_form"):
            col_date, col_1, col_2, col_3, col_4, col_5 = st.columns(6)
            
            with col_date:
                input_date = st.date_input("日期", date.today())
            with col_1:
                in_profit = st.number_input("毛利", min_value=0, step=100)
            with col_2:
                in_number = st.number_input("門號", min_value=0, step=1)
            with col_3:
                in_insur = st.number_input("保險營收", min_value=0, step=100)
            with col_4:
                in_acc = st.number_input("配件營收", min_value=0, step=100)
            with col_5:
                in_stock = st.number_input("庫存手機", min_value=0, step=1)
            
            submitted = st.form_submit_button("💾 提交日報表")
            
            if submitted:
                # 將資料寫入 Session State (模擬存檔)
                new_record = {
                    '人員': selected_user,
                    '日期': input_date,
                    '毛利': in_profit,
                    '門號': in_number,
                    '保險': in_insur,
                    '配件': in_acc,
                    '庫存': in_stock
                }
                st.session_state.records = pd.concat([st.session_state.records, pd.DataFrame([new_record])], ignore_index=True)
                st.success(f"{input_date} 業績已儲存！")

# --- 4. 核心邏輯運算 (Excel 公式移植) ---

# A. 取得該員(或該店)的目標
if selected_user == "全店總表":
    # 若選全店，目標是店總目標
    target_data = st.session_state.targets.get(selected_store, {'毛利': 1, '門號': 1, '保險': 1, '配件': 1, '庫存': 1})
    # 業績是所有人加總
    filtered_records = st.session_state.records # 這裡簡化，實際應篩選該店所有人
else:
    # 若選個人，目標是個人目標
    target_data = st.session_state.targets.get(selected_user, {'毛利': 1, '門號': 1, '保險': 1, '配件': 1, '庫存': 1})
    # 業績是個人篩選
    filtered_records = st.session_state.records[st.session_state.records['人員'] == selected_user]

# B. 計算累計業績 (SUM)
current_performance = {
    '毛利': filtered_records['毛利'].sum() if not filtered_records.empty else 0,
    '門號': filtered_records['門號'].sum() if not filtered_records.empty else 0,
    '保險': filtered_records['保險'].sum() if not filtered_records.empty else 0,
    '配件': filtered_records['配件'].sum() if not filtered_records.empty else 0,
    '庫存': filtered_records['庫存'].sum() if not filtered_records.empty else 0,
}

# C. 計算時間參數 (對應 Excel 左上角時間區)
today = date.today()
last_day_of_month = calendar.monthrange(today.year, today.month)[1]
remaining_days = last_day_of_month - today.day
if remaining_days < 0: remaining_days = 0

# --- 5. 儀表板呈現區 ---

st.title(f"📊 {selected_user} - 業績動態戰情室")
st.markdown("---")

# 定義一個顯示卡片的函式 (包含動能計算公式)
def display_kpi(label, current, target, unit=""):
    # 1. 達成率公式
    achievement_rate = (current / target) * 100 if target > 0 else 0
    
    # 2. GAP (落差) 公式
    gap = target - current
    
    # 3. 日動能 (Momentum) 公式： (目標 - 目前) / 剩餘天數
    momentum = gap / remaining_days if remaining_days > 0 and gap > 0 else 0
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.metric(
            label=f"{label} (目標: {target:,})",
            value=f"{current:,} {unit}",
            delta=f"{achievement_rate:.1f}% 達成 (GAP: {gap:,})"
        )
    with col2:
        if gap > 0:
            st.metric(
                label="🔥 每日需達 (動能)",
                value=f"{int(momentum):,} {unit}",
                delta="落後追趕中" if momentum > (target/last_day_of_month) else "進度安全",
                delta_color="inverse"
            )
        else:
             st.metric(label="✨ 狀態", value="已達標", delta="恭喜！")
    
    # 4. 進度條 (移植 115% 視覺化)
    st.progress(min(achievement_rate / 115, 1.0)) # 假設 115% 是滿條
    st.caption(f"目前達成率: {achievement_rate:.1f}% / 115% (超額激勵目標)")

# 顯示各項指標
kpi_col1, kpi_col2 = st.columns(2)

with kpi_col1:
    st.subheader("💰 營收核心")
    display_kpi("毛利", current_performance['毛利'], target_data['毛利'])
    st.divider()
    display_kpi("保險營收", current_performance['保險'], target_data['保險'])

with kpi_col2:
    st.subheader("📱 件數核心")
    display_kpi("門號數", current_performance['門號'], target_data['門號'], "件")
    st.divider()
    display_kpi("配件營收", current_performance['配件'], target_data['配件'])

# --- 6. 顯示詳細報表 (類似 Excel 表格) ---
with st.expander("🔎 查看詳細日報表 (Excel 檢視)", expanded=False):
    if not filtered_records.empty:
        st.dataframe(filtered_records.sort_values("日期", ascending=False), use_container_width=True)
    else:
        st.info("目前尚無資料，請於上方填寫日報表。")
