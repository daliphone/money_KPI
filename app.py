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

# ==========================================
# ⚙️ 系統設定區 (請依照您的檔案名稱修改這裡)
# ==========================================

# 1. 分店名稱清單
# 請將這裡的名稱改為您實際檔案中的分店名稱
# 例如：如果您的檔案是 "2025_12_大灣店業績.xlsx"，這裡就填 "大灣店"
STORE_LIST = ["東門店", "小西門店", "文賢店", "歸仁店", "永康店", "安中店", "鹽行店", "五甲店", "鳳山店"] 

# 2. 全店總覽需要的 16 項指標 (對應總表)
METRICS_ALL = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機", 
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論",
    "來客數", "遠傳續約", "累積GAP", "遠傳升續率", "遠傳平續率", "綜合指標"
]

# 3. 個人/門市人員填寫的 10 項目標 (對應人員填寫)
METRICS_STAFF = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機",
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論"
]

# 4. 模擬資料 (實際運作時，這些 KEY 名稱要跟上面的 STORE_LIST 一致)
MOCK_DATA = {
    "東門店": [150000, 20, 5000, 30000, 5, 10, 2, 5, 80, 4.9, 150, 10, 2, "80%", "90%", "A"],
    "西門店": [120000, 15, 3000, 25000, 3, 8, 1, 4, 70, 4.8, 120, 8, 1, "75%", "88%", "B+"],
    "南門店": [130000, 18, 4000, 28000, 4, 9, 2, 4, 75, 4.7, 130, 9, 1, "78%", "89%", "A-"],
    "北門店": [180000, 25, 6000, 35000, 6, 12, 3, 6, 90, 5.0, 180, 12, 0, "85%", "92%", "A+"],
}

# 計算全店總計 (這裡簡單模擬加總，文字類欄位略過)
TOTAL_DATA = [580000, 78, 18000, 118000, 18, 39, 8, 19, 315, 4.85, 580, 39, 4, "80%", "90%", "A"]

# ==========================================
# 程式邏輯區
# ==========================================

def render_store_page(store_name, store_data_16_items):
    """
    產生單一分店的頁面內容
    """
    st.markdown(f"### 📍 {store_name} - 營運看板")
    
    # 若該店沒有資料 (例如新加的店)，給予預設空值以免報錯
    if store_data_16_items is None:
        store_data_16_items = [0] * 13 + ["0%", "0%", "N/A"]

    # 區塊 1: 該店目前的 16 項指標數據展示
    with st.expander(f"📊 {store_name} 當月詳細指標 (16項)", expanded=True):
        df_store = pd.DataFrame([store_data_16_items], columns=METRICS_ALL)
        st.dataframe(df_store, hide_index=True, use_container_width=True)
        
        # 重點數據 Metric
        c1, c2, c3, c4 = st.columns(4)
        # 確保資料存在才顯示
        if len(store_data_16_items) >= 16:
            c1.metric("本月毛利", f"${store_data_16_items[0]:,}")
            c2.metric("門號件數", f"{store_data_16_items[1]}")
            c3.metric("保險營收", f"${store_data_16_items[2]:,}")
            c4.metric("綜合指標", f"{store_data_16_items[-1]}")

    st.markdown("---")
    
    # 區塊 2: 人員目標填寫
    st.subheader(f"📝 {store_name} - 人員目標設定")
    
    c1, c2 = st.columns([1, 2])
    with c1:
        staff_name = st.text_input("人員姓名", placeholder="請輸入姓名", key=f"name_{store_name}")
        target_month = st.date_input("設定月份", value=datetime.now(), key=f"date_{store_name}")
    
    # 建立空的填寫表結構
    if f'data_{store_name}' not in st.session_state:
        st.session_state[f'data_{store_name}'] = pd.DataFrame({
            "評估項目": METRICS_STAFF,
            "目標設定值": [0] * len(METRICS_STAFF),
            "備註": [""] * len(METRICS_STAFF)
        })

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
        key=f"editor_{store_name}"
    )

    if st.button(f"確認儲存 ({store_name})", key=f"btn_{store_name}"):
        if not staff_name:
            st.warning("⚠️ 請填寫人員姓名")
        else:
            st.success(f"✅ 已儲存 {store_name} - {staff_name} 的目標！")

def main():
    st.title("📱 馬尼通訊 - 營運管理系統")

    # 動態建立分頁標籤：[全店總表] + [各分店名稱]
    tabs_list = ["🏆 全店總表 (ALL)"] + STORE_LIST
    tabs = st.tabs(tabs_list)

    # --- 分頁 1: 全店總表 ---
    with tabs[0]:
        st.header("🏆 全店營運總覽")
        st.write("各分店 16 項指標比較表")
        
        # 組合資料
        all_data_rows = []
        for store in STORE_LIST:
            # 取得該店資料，若無資料則給空值
            data = MOCK_DATA.get(store, [0]*16) 
            row = [store] + data
            all_data_rows.append(row)
            
        # 加入總計
        all_data_rows.append(["全店總計"] + TOTAL_DATA)
        
        df_all = pd.DataFrame(all_data_rows, columns=["門市"] + METRICS_ALL)
        
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

    # --- 後續分頁: 各分店 ---
    # 使用 STORE_LIST 自動產生對應分頁
    for i, store_name in enumerate(STORE_LIST):
        # tabs[0] 是總表，所以分店從 tabs[i+1] 開始
        with tabs[i+1]:
            # 從資料庫(MOCK_DATA)抓取該店資料
            store_data = MOCK_DATA.get(store_name, None)
            render_store_page(store_name, store_data)

if __name__ == "__main__":
    main()
