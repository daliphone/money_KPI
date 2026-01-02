import streamlit as st
import pandas as pd
from datetime import datetime

# 設定頁面配置
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
    </style>
    """, unsafe_allow_html=True)

# --- 資料定義 ---

# 1. 全店總覽需要的 16 項指標
METRICS_ALL = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機", 
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論",
    "來客數", "遠傳續約", "累積GAP", "遠傳升續率", "遠傳平續率", "綜合指標"
]

# 2. 個人/門市人員填寫的 10 項目標
METRICS_STAFF = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機",
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論"
]

# 模擬資料 (實際運作時，這些資料應來自您的 Google Sheet)
MOCK_DATA = {
    "東門店": [150000, 20, 5000, 30000, 5, 10, 2, 5, 80, 4.9, 150, 10, 2, "80%", "90%", "A"],
    "西門店": [120000, 15, 3000, 25000, 3, 8, 1, 4, 70, 4.8, 120, 8, 1, "75%", "88%", "B+"],
    "北門店": [180000, 25, 6000, 35000, 6, 12, 3, 6, 90, 5.0, 180, 12, 0, "85%", "92%", "A+"],
}
# 計算全店總計 (這裡簡單模擬加總，文字類欄位略過)
TOTAL_DATA = [450000, 60, 14000, 90000, 14, 30, 6, 15, 240, 4.9, 450, 30, 3, "80%", "90%", "A"]

# --- 功能函式：顯示單一分店的內容 ---
def render_store_page(store_name, store_data_16_items):
    """
    產生單一分店的頁面內容，包含：
    1. 該店的 16 項指標看板
    2. 該店人員的個人目標填寫表
    """
    st.markdown(f"### 📍 {store_name} - 營運看板")
    
    # 區塊 1: 該店目前的 16 項指標數據展示
    with st.expander("📊 查看該店當月詳細指標 (16項)", expanded=True):
        # 將資料轉為 DataFrame 橫向顯示
        df_store = pd.DataFrame([store_data_16_items], columns=METRICS_ALL)
        st.dataframe(df_store, hide_index=True, use_container_width=True)
        
        # 顯示幾個重點數據 (Metric)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("本月毛利", f"${store_data_16_items[0]:,}")
        c2.metric("門號件數", f"{store_data_16_items[1]}")
        c3.metric("保險營收", f"${store_data_16_items[2]:,}")
        c4.metric("綜合指標", f"{store_data_16_items[-1]}")

    st.markdown("---")
    
    # 區塊 2: 人員目標填寫 (維持原本代碼)
    st.subheader(f"📝 {store_name} - 人員目標設定")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        # 使用 unique key 避免不同分頁衝突
        staff_name = st.text_input("人員姓名", placeholder="請輸入姓名", key=f"name_{store_name}")
        target_month = st.date_input("設定月份", value=datetime.now(), key=f"date_{store_name}")
    
    # 建立空的填寫表結構
    if f'data_{store_name}' not in st.session_state:
        st.session_state[f'data_{store_name}'] = pd.DataFrame({
            "評估項目": METRICS_STAFF,
            "目標設定值": [0] * len(METRICS_STAFF),
            "備註": [""] * len(METRICS_STAFF)
        })

    # 顯示可編輯表格
    column_config = {
        "評估項目": st.column_config.TextColumn("評估項目", disabled=True),
        "目標設定值": st.column_config.NumberColumn("目標數值", min_value=0, format="%d", required=True),
        "備註": st.column_config.TextColumn("備註說明")
    }

    edited_df = st.data_editor(
        st.session_state[f'data_{store_name}'],
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"editor_{store_name}" # 重要：每個分店要有獨立的 key
    )

    if st.button(f"確認儲存 ({store_name})", key=f"btn_{store_name}"):
        if not staff_name:
            st.warning("⚠️ 請填寫人員姓名")
        else:
            st.success(f"✅ 已儲存 {store_name} - {staff_name} 的目標！")
            # 這裡之後可以串接 Google Sheet 寫入功能

# --- 主程式 ---
def main():
    st.title("📱 馬尼通訊 - 營運管理系統")

    # 定義分頁：第一頁是總表，後面依序是各分店
    tabs_list = ["🏆 全店總表 (ALL)", "東門店", "西門店", "北門店"]
    tabs = st.tabs(tabs_list)

    # --- 分頁 1: 全店總表 ---
    with tabs[0]:
        st.header("🏆 全店營運總覽")
        st.write("各分店 16 項指標比較表")
        
        # 組合所有資料
        all_data_rows = []
        # 加入各店
        for store, data in MOCK_DATA.items():
            row = [store] + data
            all_data_rows.append(row)
        # 加入總計
        all_data_rows.append(["全店總計"] + TOTAL_DATA)
        
        df_all = pd.DataFrame(all_data_rows, columns=["門市"] + METRICS_ALL)
        
        # 顯示大表格
        st.dataframe(
            df_all,
            use_container_width=True,
            hide_index=True,
            column_config={
                "門市": st.column_config.TextColumn("門市", disabled=True),
                "毛利": st.column_config.NumberColumn("毛利", format="$%d"),
                "綜合指標": st.column_config.Column("綜合指標", width="small")
            }
        )
        
        # 總表下方的圖表分析 (可選)
        st.caption("💡 提示：點擊上方標題欄位可進行排序")

    # --- 分頁 2, 3, 4: 各分店內容 ---
    # 利用迴圈自動生成各店頁面
    store_names = ["東門店", "西門店", "北門店"]
    
    # 注意：tabs[0] 是總表，所以從 tabs[1] 開始對應 store_names[0]
    for i, store_name in enumerate(store_names):
        with tabs[i+1]:
            # 呼叫上面定義好的函式，傳入店名與該店數據
            render_store_page(store_name, MOCK_DATA[store_name])

if __name__ == "__main__":
    main()
