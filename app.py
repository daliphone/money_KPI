import streamlit as st
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 系統設定
# ==========================================
st.set_page_config(
    page_title="馬尼通訊 - 營運管理系統",
    page_icon="📈",
    layout="wide"  # 改為寬螢幕模式以容納總表
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
# 2. 資料定義 (16項完整指標)
# ==========================================
KPI_ITEMS = [
    "毛利",
    "門號",
    "保險營收",
    "配件營收",
    "庫存手機",
    "蘋果手機",
    "蘋果平板+手錶",
    "VIVO手機",
    "生活圈",
    "GOOGLE 評論",
    "來客數",       # 新增
    "遠傳續約",     # 新增
    "累積GAP",      # 新增
    "遠傳升續率",   # 新增
    "遠傳平續率",   # 新增
    "綜合指標"      # 新增
]

# 模擬雲端檔案連結 (請替換成您真實的 Google Drive 連結)
GOOGLE_DRIVE_LINK = "https://docs.google.com/spreadsheets/d/YOUR_FILE_ID_HERE"

# ==========================================
# 3. 頁面功能函式
# ==========================================

def render_goal_setting():
    """頁面 1: 門市人員目標分配"""
    st.title("🎯 馬尼通訊 - 門市人員目標分配")
    st.write("請依照下方項目填寫本月個人目標。")

    # 1. 基本資料區
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            staff_name = st.text_input("人員姓名", placeholder="請輸入姓名")
        with col2:
            target_month = st.date_input("設定月份", value=datetime.now())

    st.markdown("---")

    # 2. 建立資料結構
    if 'goal_data' not in st.session_state:
        st.session_state.goal_data = pd.DataFrame({
            "評估項目": KPI_ITEMS,
            "目標設定值": [0] * len(KPI_ITEMS),
            "備註": [""] * len(KPI_ITEMS)
        })

    # 3. 顯示輸入介面 (Data Editor)
    st.subheader("📝 目標數值填寫")
    
    column_config = {
        "評估項目": st.column_config.TextColumn(
            "評估項目", disabled=True, width="medium"
        ),
        "目標設定值": st.column_config.NumberColumn(
            "目標數值 / 百分比",
            help="金額、件數或百分比 (如 80 代表 80%)",
            min_value=0,
            step=1,
            required=True
        ),
        "備註": st.column_config.TextColumn(
            "備註說明", width="large"
        )
    }

    edited_df = st.data_editor(
        st.session_state.goal_data,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        height=600 # 拉高表格以容納 16 個項目
    )

    st.info("💡 提示：百分比項目 (如升續率) 請直接輸入數字 (例如 80)。")

    # 4. 送出按鈕
    if st.button("確認儲存目標", use_container_width=True):
        if not staff_name:
            st.warning("⚠️ 請務必填寫人員姓名！")
        else:
            st.success(f"✅ {staff_name} 的 {target_month.strftime('%Y年%m月')} 目標已成功設定！")
            
            # 結果預覽
            st.markdown("### 📊 設定結果預覽")
            result_view = edited_df.set_index("評估項目")["目標設定值"]
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("預估毛利", f"{result_view['毛利']:,}")
            c2.metric("門號件數", f"{result_view['門號']}")
            c3.metric("遠傳升續率", f"{result_view['遠傳升續率']}%")
            c4.metric("綜合指標", f"{result_view['綜合指標']}")

            with st.expander("查看完整列表"):
                st.table(edited_df)

def render_all_overview():
    """頁面 2: (ALL) 全店總表"""
    st.title("📊 (ALL) 全店總表 - 營運總覽")
    
    # 功能列：開啟雲端檔案
    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        st.link_button("🔗 開啟雲端原始檔", GOOGLE_DRIVE_LINK, use_container_width=True)
    with col_info:
        st.caption("點擊按鈕可直接前往 Google Drive 查看詳細報表與公式。")

    st.markdown("---")

    # 模擬全店數據 (實際應用時這裡應從 Google Sheet 讀取)
    # 這裡建立一個包含所有 16 項指標的範例資料
    mock_data = {
        "門市": ["東門店", "西門店", "南門店", "北門店", "全店總計"],
        "毛利": [150000, 120000, 130000, 180000, 580000],
        "門號": [20, 15, 18, 25, 78],
        "保險營收": [5000, 3000, 4000, 6000, 18000],
        "配件營收": [30000, 25000, 28000, 35000, 118000],
        "庫存手機": [5, 3, 4, 6, 18],
        "蘋果手機": [10, 8, 9, 12, 39],
        "蘋果平板+手錶": [2, 1, 2, 3, 8],
        "VIVO手機": [5, 4, 4, 6, 19],
        "生活圈": [80, 70, 75, 90, 315],
        "GOOGLE 評論": [4.9, 4.8, 4.7, 5.0, 4.85],
        "來客數": [150, 120, 130, 180, 580],
        "遠傳續約": [10, 8, 9, 12, 39],
        "累積GAP": [2, 1, 1, 0, 4],
        "遠傳升續率": [80, 75, 78, 85, 80], # 顯示為數字，呈現時加 %
        "遠傳平續率": [90, 88, 89, 92, 90],
        "綜合指標": [95, 88, 90, 98, 93]    # 假設為分數
    }
    
    df_all = pd.DataFrame(mock_data)

    # 顯示總表 (DataFrame)
    st.subheader("各門市詳細數據")
    
    # 設定欄位顯示格式
    column_config = {
        "門市": st.column_config.TextColumn("門市名稱", disabled=True),
        "毛利": st.column_config.NumberColumn("毛利", format="$%d"),
        "保險營收": st.column_config.NumberColumn("保險營收", format="$%d"),
        "配件營收": st.column_config.NumberColumn("配件營收", format="$%d"),
        "遠傳升續率": st.column_config.ProgressColumn("升續率", format="%d%%", min_value=0, max_value=100),
        "遠傳平續率": st.column_config.ProgressColumn("平續率", format="%d%%", min_value=0, max_value=100),
        "綜合指標": st.column_config.NumberColumn("綜合指標", format="%d 分"),
    }

    st.dataframe(
        df_all,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=300
    )

    # 重點指標 Dashboard
    st.subheader("重點指標速覽")
    total_row = df_all.iloc[-1] # 取最後一行總計
    
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("全店總毛利", f"${total_row['毛利']:,}")
    m2.metric("總來客數", f"{total_row['來客數']} 人")
    m3.metric("總門號數", f"{total_row['門號']} 件")
    m4.metric("平均升續率", f"{total_row['遠傳升續率']}%")
    m5.metric("綜合指標", f"{total_row['綜合指標']} 分")

# ==========================================
# 4. 主程式 (導覽控制)
# ==========================================
def main():
    # 側邊導覽列
    with st.sidebar:
        st.header("馬尼通訊系統")
        page = st.radio(
            "請選擇功能頁面：",
            ["🎯 門市目標分配", "📊 (ALL) 全店總表"]
        )
        st.markdown("---")
        st.caption("Version 2.0")

    # 根據選擇渲染對應頁面
    if page == "🎯 門市目標分配":
        render_goal_setting()
    elif page == "📊 (ALL) 全店總表":
        render_all_overview()

if __name__ == "__main__":
    main()
