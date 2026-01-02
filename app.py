import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 系統設定與資料定義
# ==========================================

# 設定頁面配置
st.set_page_config(
    page_title="馬尼通訊 - 營運管理系統",
    page_icon="📈",
    layout="wide" # 改為寬版面以容納總表
)

# --- 樣式設定 (保留您原本的樣式) ---
st.markdown("""
    <style>
    .big-font {
        font-size:20px !important;
        font-weight: bold;
    }
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# 分店清單 (請依照您的檔案名稱設定)
STORE_LIST = ["東門店", "西門店", "南門店", "北門店"]

# 全店總覽需要的 16 項指標 (Dashboard 用)
METRICS_ALL = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機", 
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論",
    "來客數", "遠傳續約", "累積GAP", "遠傳升續率", "遠傳平續率", "綜合指標"
]

# 個人/門市人員填寫的 10 項目標 (Input 用)
METRICS_STAFF = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機",
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論"
]

# 模擬資料 (Dashboard 顯示用，未來可替換為讀取 Google Sheet)
MOCK_DATA = {
    "東門店": [150000, 20, 5000, 30000, 5, 10, 2, 5, 80, 4.9, 150, 10, 2, "80%", "90%", "A"],
    "西門店": [120000, 15, 3000, 25000, 3, 8, 1, 4, 70, 4.8, 120, 8, 1, "75%", "88%", "B+"],
    "南門店": [130000, 18, 4000, 28000, 4, 9, 2, 4, 75, 4.7, 130, 9, 1, "78%", "89%", "A-"],
    "北門店": [180000, 25, 6000, 35000, 6, 12, 3, 6, 90, 5.0, 180, 12, 0, "85%", "92%", "A+"],
}
# 模擬總計
TOTAL_DATA = [580000, 78, 18000, 118000, 18, 39, 8, 19, 315, 4.85, 580, 39, 4, "80%", "90%", "A"]

# ==========================================
# 2. 核心功能函式
# ==========================================

def render_input_form(store_name):
    """
    渲染單一分店的「目標填寫」表單
    (邏輯源自您原本的程式碼，並加入 key 區隔不同分店)
    """
    st.subheader(f"📝 {store_name} - 人員目標設定")
    st.write("請依照下方項目填寫本月個人目標。")

    # 1. 基本資料區
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            # 加入 key 以區分不同分店的輸入框
            staff_name = st.text_input("人員姓名", placeholder="請輸入姓名", key=f"staff_{store_name}")
        with col2:
            current_month = datetime.now().strftime("%Y-%m")
            target_month = st.date_input("設定月份", value=datetime.now(), key=f"date_{store_name}")

    st.markdown("---")

    # 3. 建立資料結構 (使用 session_state 綁定分店)
    data_key = f'goal_data_{store_name}'
    
    if data_key not in st.session_state:
        st.session_state[data_key] = pd.DataFrame({
            "評估項目": METRICS_STAFF,
            "目標設定值": [0] * len(METRICS_STAFF), # 預設值為 0
            "備註": [""] * len(METRICS_STAFF)      # 預留備註欄位
        })

    # 4. 顯示輸入介面 (使用 Data Editor)
    # 配置欄位屬性
    column_config = {
        "評估項目": st.column_config.TextColumn(
            "評估項目",
            help="公司指定的KPI項目",
            disabled=True, # 禁止修改項目名稱
            width="medium"
        ),
        "目標設定值": st.column_config.NumberColumn(
            "目標數值",
            help="請輸入本月目標數字 (金額或件數)",
            min_value=0,
            step=1,
            format="%d", # 設定為整數顯示
            required=True
        ),
        "備註": st.column_config.TextColumn(
            "備註說明",
            help="如有特殊狀況請填寫",
            width="large"
        )
    }

    # 顯示可編輯表格
    edited_df = st.data_editor(
        st.session_state[data_key],
        column_config=column_config,
        hide_index=True, # 隱藏索引列
        use_container_width=True,
        num_rows="fixed", # 固定行數
        key=f"editor_{store_name}" # 重要：每個 Data Editor 必須有唯一的 key
    )

    # 5. 統計預覽
    st.info("💡 提示：輸入完畢後請按下方按鈕送出。")

    # 6. 送出按鈕與處理邏輯
    if st.button(f"確認儲存目標 ({store_name})", use_container_width=True, key=f"btn_{store_name}"):
        if not staff_name:
            st.warning("⚠️ 請務必填寫人員姓名！")
        else:
            # 這裡模擬資料處理
            st.success(f"✅ {store_name} - {staff_name} 的 {target_month.strftime('%Y年%m月')} 目標已成功設定！")
            
            # 顯示最終確認的資料
            st.write("---")
            st.markdown("### 📊 設定結果預覽")
            
            # 將資料轉置顯示
            result_view = edited_df.set_index("評估項目")["目標設定值"]
            
            # 使用 metric 顯示重點
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("預估毛利", f"{result_view['毛利']:,}")
            with c2:
                st.metric("門號件數", f"{result_view['門號']}")
            with c3:
                st.metric("保險營收", f"{result_view['保險營收']:,}")

            # 顯示完整表格供截圖
            st.table(edited_df)

def render_store_dashboard(store_name, data_16_items):
    """
    顯示該分店的 16 項指標看板 (唯讀)
    """
    st.markdown(f"### 📍 {store_name} - 營運看板")
    
    # 處理空資料狀況
    if data_16_items is None:
        data_16_items = [0] * 16

    with st.expander(f"📊 {store_name} 當月詳細指標 (16項)", expanded=True):
        # 轉為 DataFrame 顯示
        df_store = pd.DataFrame([data_16_items], columns=METRICS_ALL)
        
        st.dataframe(
            df_store, 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "毛利": st.column_config.NumberColumn(format="$%d"),
                "保險營收": st.column_config.NumberColumn(format="$%d"),
                "配件營收": st.column_config.NumberColumn(format="$%d"),
            }
        )

# ==========================================
# 3. 主程式邏輯
# ==========================================

def main():
    st.title("🎯 馬尼通訊 - 門市人員目標分配系統")
    
    # 建立分頁標籤：[全店總表] + [各分店]
    tabs_list = ["🏆 全店總表 (ALL)"] + STORE_LIST
    tabs = st.tabs(tabs_list)

    # --- 分頁 1: 全店總表 (ALL) ---
    with tabs[0]:
        st.header("🏆 全店營運總覽")
        st.write("各分店 16 項指標比較表")
        
        # 組合資料
        all_data_rows = []
        for store in STORE_LIST:
            data = MOCK_DATA.get(store, [0]*16) 
            row = [store] + data
            all_data_rows.append(row)
            
        # 加入總計
        all_data_rows.append(["全店總計"] + TOTAL_DATA)
        
        df_all = pd.DataFrame(all_data_rows, columns=["門市"] + METRICS_ALL)
        
        # 顯示總表
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

    # --- 分頁 2~N: 各分店 (Dashboard + Input Form) ---
    for i, store_name in enumerate(STORE_LIST):
        # tabs[0] 是總表，所以從 tabs[i+1] 開始
        with tabs[i+1]:
            # 1. 上半部：顯示該店 Dashboard
            store_data = MOCK_DATA.get(store_name, None)
            render_store_dashboard(store_name, store_data)
            
            st.markdown("---")
            
            # 2. 下半部：顯示人員輸入表單 (原本的程式碼邏輯)
            render_input_form(store_name)

if __name__ == "__main__":
    main()
