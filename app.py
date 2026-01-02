import streamlit as st

import pandas as pd

from datetime import datetime



# 設定頁面配置

st.set_page_config(

    page_title="馬尼通訊 - 目標分配系統",

    page_icon="📈",

    layout="centered"

)



# --- 樣式設定 (可選) ---

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



# --- 主程式 ---

def main():

    st.title("🎯 馬尼通訊 - 門市人員目標分配")

    st.write("請依照下方項目填寫本月個人目標。")



    # 1. 基本資料區

    with st.container():

        col1, col2 = st.columns(2)

        with col1:

            staff_name = st.text_input("人員姓名", placeholder="請輸入姓名")

        with col2:

            current_month = datetime.now().strftime("%Y-%m")

            target_month = st.date_input("設定月份", value=datetime.now())



    st.markdown("---")



    # 2. 定義目標項目 (您指定的新增項目)

    kpi_items = [

        "毛利",

        "門號",

        "保險營收",

        "配件營收",

        "庫存手機",

        "蘋果手機",

        "蘋果平板+手錶",

        "VIVO手機",

        "生活圈",

        "GOOGLE 評論"

    ]



    # 3. 建立資料結構

    # 如果還沒有儲存過資料，建立一個預設的 DataFrame

    if 'goal_data' not in st.session_state:

        st.session_state.goal_data = pd.DataFrame({

            "評估項目": kpi_items,

            "目標設定值": [0] * len(kpi_items), # 預設值為 0

            "備註": [""] * len(kpi_items)      # 預留備註欄位

        })



    # 4. 顯示輸入介面 (使用 Data Editor)

    st.subheader("📝 目標數值填寫")

    

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

        st.session_state.goal_data,

        column_config=column_config,

        hide_index=True, # 隱藏索引列

        use_container_width=True,

        num_rows="fixed" # 固定行數，不讓使用者新增或刪除項目

    )



    # 5. 統計預覽 (選用功能，讓填寫者更有感)

    # 簡單區分一下金額類和件數類 (這裡做個簡單的加總示範，您可以根據實際單位調整)

    st.info("💡 提示：輸入完畢後請按下方按鈕送出。")



    # 6. 送出按鈕與處理邏輯

    if st.button("確認儲存目標", use_container_width=True):

        if not staff_name:

            st.warning("⚠️ 請務必填寫人員姓名！")

        else:

            # 這裡模擬資料處理

            st.success(f"✅ {staff_name} 的 {target_month.strftime('%Y年%m月')} 目標已成功設定！")

            

            # 顯示最終確認的資料

            st.write("---")

            st.markdown("### 📊 設定結果預覽")

            

            # 將資料轉置顯示，方便手機截圖或查看

            # 這裡將 DataFrame 轉為類似清單的顯示方式

            result_view = edited_df.set_index("評估項目")["目標設定值"]

            

            # 使用 metric 顯示重點 (範例：前三項)

            c1, c2, c3 = st.columns(3)

            with c1:

                st.metric("預估毛利", f"{result_view['毛利']:,}")

            with c2:

                st.metric("門號件數", f"{result_view['門號']}")

            with c3:

                st.metric("保險營收", f"{result_view['保險營收']:,}")



            # 顯示完整表格供截圖

            st.table(edited_df)



            # (進階) 這裡可以加入程式碼將 edited_df 存入 CSV 或 Google Sheets

            # save_to_database(staff_name, target_month, edited_df)



if __name__ == "__main__":

    main()
