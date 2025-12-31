import streamlit as st
import pandas as pd
from datetime import date
import calendar

# --- 1. 系統初始化與組織設定 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="🏢")

# 定義組織與人員結構 (依據你的檔案)
STORES = {
    "(ALL) 全店總表": [],
    "文賢店": ["慧婷", "阿緯", "子翔", "默默"],
    "東門店": ["小萬", "914", "默默", "人員4"],
    "永康店": ["宗憲", "筑君", "澤偉", "翰霖", "77", "支援"],
    "歸仁店": ["配飯", "誌廷", "阿孝", "支援", "人員2"],
    "安中店": ["宗憲", "大俗", "翰霖", "澤偉"],
    "小西門店": ["豆豆", "秀秀", "人員3", "人員4"],
    "鹽行店": ["配飯", "薪融", "脆迪", "誌廷", "人員2"],
    "五甲店": ["阿凱", "孟婧", "支援", "人員2"],
    "鳳山店": []
}

# 模擬資料庫 (實際運作需連接 Google Sheets)
if 'db' not in st.session_state:
    # 建立一個包含 '門市' 欄位的資料表
    st.session_state.records = pd.DataFrame(
        columns=['門市', '人員', '日期', '毛利', '門號', '保險', '配件', '庫存', '蘋果', 'VIVO']
    )
    # 預設目標 (簡化版，實際應從 Excel 讀取)
    st.session_state.targets = {
        '毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21
    }

# --- 2. 側邊欄：導航中心 ---
st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("選擇門市", list(STORES.keys()))

# 根據門市選擇人員
if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
    st.sidebar.info("目前檢視：全公司彙整數據")
else:
    # 加上 "該店總表" 選項
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("選擇人員 / 檢視層級", staff_options)

# --- 3. 邏輯核心：資料過濾與運算 ---

# 根據選擇的層級，篩選資料
if selected_store == "(ALL) 全店總表":
    # 抓取所有資料
    filtered_df = st.session_state.records
    view_title = "🏆 全公司 - 業績總表"
    is_input_mode = False
elif selected_user == "該店總表":
    # 抓取該分店所有人的資料
    filtered_df = st.session_state.records[st.session_state.records['門市'] == selected_store]
    view_title = f"🏪 {selected_store} - 門市總表"
    is_input_mode = False
else:
    # 抓取該員工資料
    filtered_df = st.session_state.records[
        (st.session_state.records['門市'] == selected_store) & 
        (st.session_state.records['人員'] == selected_user)
    ]
    view_title = f"👤 {selected_store} - {selected_user}"
    is_input_mode = True

# 計算當前彙整數據 (Sum)
current_stats = {
    '毛利': filtered_df['毛利'].sum() if not filtered_df.empty else 0,
    '門號': filtered_df['門號'].sum() if not filtered_df.empty else 0,
    '保險': filtered_df['保險'].sum() if not filtered_df.empty else 0,
    '配件': filtered_df['配件'].sum() if not filtered_df.empty else 0,
}

# 目標設定 (若是總表，目標要放大)
multiplier = 1
if selected_store == "(ALL) 全店總表":
    multiplier = 8 # 假設有8間店
elif selected_user == "該店總表":
    multiplier = 4 # 假設平均一間店4人
    
target_stats = {k: v * multiplier for k, v in st.session_state.targets.items()}

# --- 4. 儀表板顯示區 (View) ---
st.title(view_title)

# 動能計算
today = date.today()
last_day = calendar.monthrange(today.year, today.month)[1]
remaining_days = last_day - today.day
if remaining_days < 0: remaining_days = 0

col1, col2, col3, col4 = st.columns(4)

def show_metric(col, label, current, target):
    gap = target - current
    momentum = gap / remaining_days if remaining_days > 0 and gap > 0 else 0
    achievement = (current / target) * 100 if target > 0 else 0
    
    with col:
        st.metric(
            label=label,
            value=f"{current:,}",
            delta=f"{achievement:.1f}% (GAP: {gap:,})"
        )
        if gap > 0:
            st.caption(f"🔥 每日需達: {int(momentum):,}")

show_metric(col1, "💰 毛利", current_stats['毛利'], target_stats['毛利'])
show_metric(col2, "📱 門號", current_stats['門號'], target_stats['門號'])
show_metric(col3, "🛡️ 保險", current_stats['保險'], target_stats['保險'])
show_metric(col4, "🔌 配件", current_stats['配件'], target_stats['配件'])

st.divider()

# --- 5. 資料輸入區 (Input) - 只有選個人時才出現 ---
if is_input_mode:
    st.subheader(f"📝 {selected_user} - 今日業績回報")
    with st.form("daily_input"):
        d_col1, d_col2 = st.columns([1, 2])
        input_date = d_col1.date_input("日期", date.today())
        
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利", step=100)
        in_number = c2.number_input("門號", step=1)
        in_insur = c3.number_input("保險", step=100)
        in_acc = c4.number_input("配件", step=100)
        
        # 這裡可以加入更多 Excel 中的欄位 (庫存、蘋果、VIVO...)
        
        submit = st.form_submit_button("提交日報表", use_container_width=True)
        
        if submit:
            new_data = {
                '門市': selected_store,
                '人員': selected_user,
                '日期': input_date,
                '毛利': in_profit,
                '門號': in_number,
                '保險': in_insur,
                '配件': in_acc,
                '庫存': 0, '蘋果': 0, 'VIVO': 0 # 範例預設
            }
            # 寫入 Session State (實際應寫入 Google Sheets)
            st.session_state.records = pd.concat(
                [st.session_state.records, pd.DataFrame([new_data])], 
                ignore_index=True
            )
            st.success("✅ 資料已儲存！上方儀表板已更新。")
            st.rerun()

# --- 6. 總表分析區 (Dashboard) - 只有選總表時出現 ---
if not is_input_mode and not filtered_df.empty:
    st.subheader("📊 詳細數據分析")
    
    # 依照人員/門市分組顯示
    group_col = '人員' if selected_user == "該店總表" else '門市'
    summary = filtered_df.groupby(group_col)[['毛利', '門號', '保險', '配件']].sum().reset_index()
    
    st.bar_chart(summary, x=group_col, y=['毛利', '保險', '配件'])
    st.dataframe(summary, use_container_width=True)

elif not is_input_mode:
    st.info("尚無數據，請先至「個人頁面」輸入資料。")
