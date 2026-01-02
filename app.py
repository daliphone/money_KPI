import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(
    page_title="馬尼通訊 - 營運管理系統",
    page_icon="📱",
    layout="wide"
)

# --- 樣式設定 ---
st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .stButton>button { width: 100%; background-color: #FF4B4B; color: white; }
    /* 調整 Sidebar 樣式 */
    section[data-testid="stSidebar"] {
        background-color: #f0f2f6;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. 資料定義與設定 (請在此修改人員名單)
# ==========================================

# (1) 定義分店名稱
STORE_LIST = ["東門店", "小西門店", "文賢店"]

# (2) 定義各分店的人員名單 (模擬從報表讀取)
# 這裡設定好後，選擇分店時下拉選單會自動跳出對應的人
STORE_STAFF_DATA = {
    "東門店": ["小萬", "默默", "914", "人員4"], 
    "小西門店": ["店長A", "店員B", "店員C"],
    "文賢店": ["店長X", "店員Y", "店員Z"]
}

# (3) 定義 16 項指標
KPI_ITEMS = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機",
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論",
    "來客數", "遠傳續約", "累積GAP", "遠傳升續率", "遠傳平續率", "綜合指標"
]

# (4) 模擬各店雲端報表連結 (請替換為真實連結)
STORE_LINKS = {
    "東門店": "https://docs.google.com/spreadsheets/d/LINK_DONGMEN",
    "小西門店": "https://docs.google.com/spreadsheets/d/LINK_XIAOXIMEN",
    "文賢店": "https://docs.google.com/spreadsheets/d/LINK_WENXIAN"
}

# ==========================================
# 3. 頁面功能函式
# ==========================================

def render_goal_setting(selected_store):
    """頁面 1: 門市人員目標分配"""
    st.title(f"🎯 {selected_store} - 人員目標分配")
    
    # 顯示雲端連結按鈕
    if selected_store in STORE_LINKS:
        st.link_button(f"🔗 開啟 {selected_store} 雲端報表", STORE_LINKS[selected_store])

    st.markdown("---")
    st.write("請選擇人員並填寫本月目標。")

    # 1. 基本資料區 (自動讀取該店人員)
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            # 取得該店人員清單，若無則顯示預設
            staff_list = STORE_STAFF_DATA.get(selected_store, ["未定義人員"])
            
            # 使用 Selectbox 讓使用者選擇，而非手動輸入
            selected_staff = st.selectbox("選擇人員", staff_list, key="staff_select")
            
        with col2:
            target_month = st.date_input("設定月份", value=datetime.now())

    # 2. 建立資料結構
    # 使用 unique key 避免切換分店時資料混亂
    data_key = f'goal_data_{selected_store}'
    if data_key not in st.session_state:
        st.session_state[data_key] = pd.DataFrame({
            "評估項目": KPI_ITEMS,
            "目標設定值": [0] * len(KPI_ITEMS),
            "備註": [""] * len(KPI_ITEMS)
        })

    # 3. 顯示輸入介面 (Data Editor)
    st.subheader("📝 目標數值填寫")
    
    column_config = {
        "評估項目": st.column_config.TextColumn("評估項目", disabled=True, width="medium"),
        "目標設定值": st.column_config.NumberColumn(
            "目標數值",
            help="金額、件數或百分比 (如 80 代表 80%)",
            min_value=0,
            step=1,
            required=True
        ),
        "備註": st.column_config.TextColumn("備註說明", width="large")
    }

    edited_df = st.data_editor(
        st.session_state[data_key],
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        height=600,
        key=f"editor_{selected_store}"
    )

    # 4. 送出按鈕
    if st.button(f"確認上傳 ({selected_store})", use_container_width=True):
        st.success(f"✅ {selected_store} - {selected_staff} 的 {target_month.strftime('%Y年%m月')} 目標已成功設定！")
        
        # 結果預覽
        st.markdown("### 📊 上傳內容預覽")
        result_view = edited_df.set_index("評估項目")["目標設定值"]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("預估毛利", f"${result_view['毛利']:,}")
        c2.metric("門號件數", f"{result_view['門號']}")
        c3.metric("遠傳升續率", f"{result_view['遠傳升續率']}%")
        c4.metric("綜合指標", f"{result_view['綜合指標']}")

def render_all_overview():
    """頁面 2: (ALL) 全店總表"""
    st.title("📊 (ALL) 全店總表 - 營運總覽")
    st.caption("顯示所有分店的 16 項指標總計")

    # 模擬全店數據 (欄位對應 16 項指標)
    # 這裡的 key 必須跟 STORE_LIST 一致
    mock_data_rows = [
        # 門市, 毛利, 門號, 保險, 配件, 庫存, 蘋果, 平板, VIVO, 生活, 評論, 來客, 續約, GAP, 升續, 平續, 綜合
        ["東門店", 150000, 20, 5000, 30000, 5, 10, 2, 5, 80, 4.9, 150, 10, 2, 80, 90, 95],
        ["小西門店", 120000, 15, 3000, 25000, 3, 8, 1, 4, 70, 4.8, 120, 8, 1, 75, 88, 88],
        ["文賢店", 180000, 25, 6000, 35000, 6, 12, 3, 6, 90, 5.0, 180, 12, 0, 85, 92, 98],
    ]
    
    # 建立總表
    cols = ["門市"] + KPI_ITEMS
    df_all = pd.DataFrame(mock_data_rows, columns=cols)

    # 計算全店總計
    total_row = ["全店總計"] + [0]*16
    for col_idx in range(1, 17): # 針對數值欄位加總
        # 簡單累加，實際應用可以針對百分比做平均
        total_row[col_idx] = df_all.iloc[:, col_idx].sum()
        # 若是百分比或分數，這裡取平均比較合理，這裡先示範簡單加總/平均邏輯
        if cols[col_idx] in ["GOOGLE 評論", "遠傳升續率", "遠傳平續率", "綜合指標"]:
             total_row[col_idx] = int(df_all.iloc[:, col_idx].mean())

    # 將總計加入 DataFrame
    df_all.loc[len(df_all)] = total_row

    # 設定顯示格式
    column_config = {
        "門市": st.column_config.TextColumn("門市", disabled=True),
        "毛利": st.column_config.NumberColumn("毛利", format="$%d"),
        "遠傳升續率": st.column_config.ProgressColumn("升續率", format="%d%%", min_value=0, max_value=100),
        "遠傳平續率": st.column_config.ProgressColumn("平續率", format="%d%%", min_value=0, max_value=100),
        "綜合指標": st.column_config.NumberColumn("綜合指標", format="%d 分"),
    }

    st.dataframe(
        df_all,
        column_config=column_config,
        use_container_width=True,
        hide_index=True
    )

# ==========================================
# 4. 主程式 (導覽與邏輯控制)
# ==========================================
def main():
    # --- 側邊欄 Sidebar ---
    with st.sidebar:
        st.header("馬尼通訊系統")
        
        # 1. 功能頁面選擇
        page = st.radio(
            "功能切換",
            ["🎯 目標設定", "📊 全店總表"],
            index=0
        )
        
        st.markdown("---")
        
        # 2. 分店選擇 (若是全店總表則不顯示或 disable)
        # 這裡將分店選擇放在側邊欄，讓選擇更直覺
        selected_store = st.selectbox(
            "📍 選擇門市",
            STORE_LIST,
            index=0 # 預設選第一個 (東門店)
        )
        
        st.markdown("---")
        st.caption(f"目前操作：{selected_store}")

    # --- 主畫面渲染 ---
    if page == "🎯 目標設定":
        # 傳入在 Sidebar 選到的分店名稱
        render_goal_setting(selected_store)
        
    elif page == "📊 全店總表":
        render_all_overview()

if __name__ == "__main__":
    main()
