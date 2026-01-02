import streamlit as st
import pandas as pd
from datetime import datetime

# 設定頁面配置
st.set_page_config(
    page_title="馬尼通訊 - 營運管理系統",
    page_icon="📱",
    layout="wide" # 改為寬版面，方便顯示總表
)

# --- 樣式設定 ---
st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .stButton>button { width: 100%; background-color: #FF4B4B; color: white; }
    </style>
    """, unsafe_allow_html=True)

def main():
    st.title("📱 馬尼通訊 - 營運管理系統")
    
    # 建立分頁：區隔「個人填寫」與「總表查看」
    tab1, tab2 = st.tabs(["🎯 個人目標填寫", "📊 全店總覽 (ALL)"])

    # ==========================================
    # 分頁 1: 個人目標填寫 (維持原本代碼邏輯)
    # ==========================================
    with tab1:
        st.header("門市人員目標設定")
        st.write("請依照下方項目填寫本月個人目標。")

        # 1. 基本資料區
        col1, col2 = st.columns(2)
        with col1:
            staff_name = st.text_input("人員姓名", placeholder="請輸入姓名", key="staff_name")
        with col2:
            target_month = st.date_input("設定月份", value=datetime.now(), key="target_month")

        st.markdown("---")

        # 2. 定義個人目標項目 (原本的10項)
        personal_kpi_items = [
            "毛利", "門號", "保險營收", "配件營收", "庫存手機",
            "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論"
        ]

        # 3. 建立資料結構
        if 'goal_data' not in st.session_state:
            st.session_state.goal_data = pd.DataFrame({
                "評估項目": personal_kpi_items,
                "目標設定值": [0] * len(personal_kpi_items),
                "備註": [""] * len(personal_kpi_items)
            })

        # 4. 顯示輸入介面
        column_config = {
            "評估項目": st.column_config.TextColumn("評估項目", disabled=True),
            "目標設定值": st.column_config.NumberColumn("目標數值", min_value=0, format="%d", required=True),
            "備註": st.column_config.TextColumn("備註說明")
        }

        edited_df = st.data_editor(
            st.session_state.goal_data,
            column_config=column_config,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key="editor_personal"
        )

        if st.button("確認儲存目標", key="btn_save"):
            if not staff_name:
                st.warning("⚠️ 請務必填寫人員姓名！")
            else:
                st.success(f"✅ {staff_name} 目標已設定！")
                st.balloons()

    # ==========================================
    # 分頁 2: 全店總覽 (ALL) - 新增功能
    # ==========================================
    with tab2:
        st.header("🏆 全店營運總覽 (ALL)")
        st.write("顯示各門市與全公司的綜合績效指標。")

        # 定義總表所需的 16 項指標
        all_metrics = [
            "毛利", "門號", "保險營收", "配件營收", "庫存手機", 
            "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論",
            "來客數", "遠傳續約", "累積GAP", "遠傳升續率", "遠傳平續率", "綜合指標"
        ]

        # 模擬從 Google Sheet 讀取到的資料 (這裡先用假資料呈現格式)
        # 未來您可以將這裡替換成 pd.read_csv() 或 Google Sheets API 的資料
        mock_data = {
            "門市": ["東門店", "西門店", "北門店", "全店總計"],
            "毛利": [150000, 120000, 180000, 450000],
            "門號": [20, 15, 25, 60],
            "保險營收": [5000, 3000, 6000, 14000],
            "配件營收": [30000, 25000, 35000, 90000],
            "庫存手機": [5, 3, 6, 14],
            "蘋果手機": [10, 8, 12, 30],
            "蘋果平板+手錶": [2, 1, 3, 6],
            "VIVO手機": [5, 4, 6, 15],
            "生活圈": [80, 70, 90, 240],
            "GOOGLE 評論": [4.9, 4.8, 5.0, 4.9],
            "來客數": [150, 120, 180, 450],
            "遠傳續約": [10, 8, 12, 30],
            "累積GAP": [2, 1, 0, 3],
            "遠傳升續率": ["80%", "75%", "85%", "80%"],
            "遠傳平續率": ["90%", "88%", "92%", "90%"],
            "綜合指標": ["A", "B+", "A+", "A"]
        }

        # 建立 DataFrame
        df_all = pd.DataFrame(mock_data)

        # 顯示互動式表格
        st.dataframe(
            df_all,
            use_container_width=True,
            hide_index=True,
            column_config={
                "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                # 您可以針對特定欄位設定顯示格式，例如百分比或貨幣
                "毛利": st.column_config.NumberColumn("毛利", format="$%d"),
                "保險營收": st.column_config.NumberColumn("保險營收", format="$%d"),
                "配件營收": st.column_config.NumberColumn("配件營收", format="$%d"),
                "GOOGLE 評論": st.column_config.NumberColumn("評論星級", format="%.1f ⭐"),
            }
        )

        # 額外功能：重點指標卡片 (Metric Cards)
        st.subheader("📊 重點指標速覽")
        m1, m2, m3, m4 = st.columns(4)
        
        # 這裡假設抓取「全店總計」那一行 (最後一行) 的資料
        total_row = df_all.iloc[-1]
        
        with m1:
            st.metric("全店總毛利", f"${total_row['毛利']:,}")
        with m2:
            st.metric("總門號數", f"{total_row['門號']} 件")
        with m3:
            st.metric("平均評論", f"{total_row['GOOGLE 評論']} ⭐")
        with m4:
            st.metric("綜合指標", f"{total_row['綜合指標']}")

if __name__ == "__main__":
    main()
