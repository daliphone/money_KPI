import streamlit as st
import pandas as pd
from datetime import date
import calendar
import openpyxl
import os

def update_excel_accumulate(store, staff, date_obj, data_dict):
    """
    將資料寫回 Excel，並執行累加邏輯
    store: 門市名稱 (如 "東門店")
    staff: 人員名稱 (如 "小萬")
    date_obj: 日期物件
    data_dict: 要寫入的資料字典 {'毛利': 1000, '門號': 1...}
    """
    # 1. 組合物件路徑 (假設檔案都在同一層資料夾，檔名格式為 "門市業績日報表.xlsx")
    filename = f"{store}業績日報表.xlsx"
    
    if not os.path.exists(filename):
        return f"❌ 找不到檔案：{filename}，請確認檔案是否已上傳。"

    try:
        # 載入 Excel (data_only=False 以保留公式)
        wb = openpyxl.load_workbook(filename)
        
        # 檢查是否有該人員的分頁
        if staff not in wb.sheetnames:
            # 有些分頁可能是本名，若找不到需人工對應，這裡先假設名稱一致
            return f"❌ 找不到人員分頁：{staff}，請確認 Excel 分頁名稱。"
        
        ws = wb[staff]
        
        # 2. 計算寫入的列號 (Row)
        # 根據你的 Excel 結構：
        # Row 15 對應 "1號" (因為 Row 14 是標題或上一列，Row 15 A欄是 '1')
        # 公式：起始列 (15) + (日期 - 1)
        target_row = 15 + (date_obj.day - 1)
        
        # 雙重確認：檢查該列的 A 欄 (第1欄) 是否真的是該日期
        # openpyxl index 從 1 開始
        check_day = ws.cell(row=target_row, column=1).value
        if str(check_day) != str(date_obj.day):
            return f"⚠️ 日期定位錯誤！Excel 第 {target_row} 列是 {check_day} 號，但你要填 {date_obj.day} 號。"

        # 3. 定義欄位對應 (Column Map) - 根據你的 Excel 結構 (B欄是毛利...)
        # A=1, B=2, C=3...
        col_map = {
            '毛利': 2,           # B欄
            '門號': 3,           # C欄
            '保險營收': 4,       # D欄
            '配件營收': 5,       # E欄
            '庫存手機': 6,       # F欄
            '蘋果手機': 7,       # G欄
            '蘋果平板+手錶': 8,   # H欄
            'VIVO手機': 9,       # I欄
            '生活圈': 10,        # J欄
            'GOOGLE 評論': 11,   # K欄
            '來客數': 12,        # L欄
            '遠傳續約累積GAP': 13, # M欄 (覆蓋)
            '遠傳升續率': 14,     # N欄 (覆蓋)
            '遠傳平續率': 15      # O欄 (覆蓋)
        }

        # 4. 執行寫入 (含累加邏輯)
        # 這些欄位採取「覆蓋」模式 (Snapshot)，因為它們通常是當日最終狀態
        overwrite_fields = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率']

        updated_msg = [] # 紀錄更新了什麼

        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                cell = ws.cell(row=target_row, column=col_idx)
                
                # 取得舊數值 (若為 None 轉為 0)
                old_val = cell.value
                if old_val is None or not isinstance(old_val, (int, float)):
                    old_val = 0
                
                # 判斷是「累加」還是「覆蓋」
                if field in overwrite_fields:
                    final_val = new_val
                    op_msg = "(覆蓋)"
                else:
                    final_val = old_val + new_val
                    op_msg = f"(累加 {old_val} + {new_val})"

                # 寫入儲存格
                cell.value = final_val
                updated_msg.append(f"{field}: {final_val} {op_msg}")

        # 5. 存檔
        wb.save(filename)
        return f"✅ {date_obj} 資料已成功寫入並存檔！\n" + "\n".join(updated_msg)

    except Exception as e:
        return f"❌ 存檔失敗: {str(e)}"

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

# 模擬資料庫 (初始化 Session State)
if 'db' not in st.session_state:
    # 建立包含所有欄位的資料表
    columns = [
        '門市', '人員', '日期', 
        '毛利', '門號', '保險營收', '配件營收', 
        '庫存手機', '蘋果手機', '蘋果平板+手錶', 'VIVO手機',
        '生活圈', 'GOOGLE 評論', '來客數',
        '遠傳續約累積GAP', '遠傳升續率', '遠傳平續率', '綜合指標'
    ]
    st.session_state.records = pd.DataFrame(columns=columns)
    
    # 預設目標 (實際運作建議做一個目標設定頁面)
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

st.sidebar.markdown("---")
st.sidebar.caption(f"目前操作身份：\n**{selected_store}** - {selected_user}")

# --- 3. 邏輯核心：資料過濾與模式判斷 (修正 NameError 的關鍵) ---

# 判斷是否為輸入模式 (只有選到具體個人時才是 True)
is_input_mode = False
if selected_store != "(ALL) 全店總表" and selected_user != "該店總表":
    is_input_mode = True

# 根據選擇的層級，篩選資料 (用於儀表板顯示)
if selected_store == "(ALL) 全店總表":
    filtered_df = st.session_state.records
    view_title = "🏆 全公司 - 業績總表"
elif selected_user == "該店總表":
    filtered_df = st.session_state.records[st.session_state.records['門市'] == selected_store]
    view_title = f"🏪 {selected_store} - 門市總表"
else:
    filtered_df = st.session_state.records[
        (st.session_state.records['門市'] == selected_store) & 
        (st.session_state.records['人員'] == selected_user)
    ]
    view_title = f"👤 {selected_store} - {selected_user}"

# --- 4. 儀表板顯示區 (View) ---
st.title(view_title)

# 計算彙整數據 (Sum)
current_stats = {
    '毛利': filtered_df['毛利'].sum() if not filtered_df.empty else 0,
    '門號': filtered_df['門號'].sum() if not filtered_df.empty else 0,
    '保險': filtered_df['保險營收'].sum() if not filtered_df.empty else 0,
    '配件': filtered_df['配件營收'].sum() if not filtered_df.empty else 0,
}

# 動態目標設定 (為了讓儀表板有東西看，這裡做簡單的倍數放大)
multiplier = 1
if selected_store == "(ALL) 全店總表":
    multiplier = 8 # 假設有8間店
elif selected_user == "該店總表":
    multiplier = 4 # 假設平均一間店4人

target_stats = {
    '毛利': st.session_state.targets['毛利'] * multiplier,
    '門號': st.session_state.targets['門號'] * multiplier,
    '保險': st.session_state.targets['保險'] * multiplier,
    '配件': st.session_state.targets['配件'] * multiplier,
}

# 顯示上方 KPI 卡片
col1, col2, col3, col4 = st.columns(4)

# 時間動能參數
today = date.today()
last_day = calendar.monthrange(today.year, today.month)[1]
remaining_days = last_day - today.day
if remaining_days < 0: remaining_days = 0

def show_metric(col, label, current, target):
    gap = target - current
    achievement = (current / target) * 100 if target > 0 else 0
    # 動能公式：還缺多少 / 剩餘天數
    momentum = gap / remaining_days if remaining_days > 0 and gap > 0 else 0
    
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

# --- 5. 資料輸入區 (Input) - [核心修正部分] ---
if is_input_mode:
    st.markdown(f"### 📝 {selected_user} - 今日業績回報")
    st.info("💡 系統將自動計算「綜合指標分數」，請準確填寫。")

    with st.form("daily_input_full", clear_on_submit=True):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        
        st.markdown("---")

        # --- 第一區：核心營收 ---
        st.subheader("💰 財務與門號 (Core)")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100, help="權重 25%")
        in_number = c2.number_input("門號 (件)", min_value=0, step=1, help="權重 20%")
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100, help="權重 15%")
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100, help="權重 15%")

        # --- 第二區：硬體銷售 ---
        st.subheader("📱 硬體銷售 (Hardware)")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1, help="權重 15%")
        in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1, help="權重 10%")
        in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1, help="權重 10%")
        in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1, help="權重 5%")

        # --- 第三區：服務指標 ---
        st.subheader("🤝 顧客經營 (Service)")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (件)", min_value=0, step=1)
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

        # --- 第四區：遠傳電信指標 ---
        st.subheader("📡 遠傳專案指標")
        t1, t2, t3 = st.columns(3)
        in_gap = t1.number_input("遠傳續約累積 GAP", step=1)
        # 百分比輸入優化：讓使用者輸入 85，程式轉為 0.85
        in_up_rate_raw = t2.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        in_flat_rate_raw = t3.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        
        in_up_rate = in_up_rate_raw / 100
        in_flat_rate = in_flat_rate_raw / 100

        st.markdown("---")
        submit = st.form_submit_button("🚀 提交並計算分數", use_container_width=True)

        if submit:
            # 1. 綜合指標自動試算邏輯 (依據 115% 權重)
            targets = st.session_state.targets
            
            def calc_score(actual, target, weight):
                return (actual / target * weight) if target > 0 else 0

            score_profit = calc_score(in_profit, targets['毛利'], 0.25)
            score_number = calc_score(in_number, targets['門號'], 0.20)
            score_insur = calc_score(in_insur, targets['保險'], 0.15)
            score_acc = calc_score(in_acc, targets['配件'], 0.15)
            score_stock = calc_score(in_stock, targets['庫存'], 0.15)
            
            # 假設的固定目標 (實際應改為變數)
            score_apple = calc_score(in_apple, 10, 0.10)
            score_ipad = calc_score(in_ipad, 4, 0.05) 
            score_vivo = calc_score(in_vivo, 10, 0.10) 

            total_score = score_profit + score_number + score_insur + score_acc + score_stock + score_apple + score_ipad + score_vivo

            # 2. 建立資料物件
            new_data = {
                '門市': selected_store,
                '人員': selected_user,
                '日期': input_date,
                '毛利': in_profit,
                '門號': in_number,
                '保險營收': in_insur,
                '配件營收': in_acc,
                '庫存手機': in_stock,
                '蘋果手機': in_apple,
                '蘋果平板+手錶': in_ipad,
                'VIVO手機': in_vivo,
                '生活圈': in_life,
                'GOOGLE 評論': in_review,
                '來客數': in_traffic,
                '遠傳續約累積GAP': in_gap,
                '遠傳升續率': in_up_rate,
                '遠傳平續率': in_flat_rate,
                '綜合指標': total_score
            }

            # 3. 寫入模擬資料庫
            st.session_state.records = pd.concat(
                [st.session_state.records, pd.DataFrame([new_data])], 
                ignore_index=True
            )
            
            # 4. 回饋顯示
            st.success(f"✅ 資料已儲存！綜合指標得分：{total_score*100:.1f} 分")
            st.dataframe(pd.DataFrame([new_data]), hide_index=True)
            
            # 重新執行以更新上方儀表板數據
            # st.rerun() # 如果Streamlit版本較舊報錯，請註解掉這行
            if submit:
            # ... (原本的計算分數與建立 new_data 邏輯保持不變) ...

            # [新增] 呼叫存檔函式
            # 注意：這裡假設你的環境有權限寫入檔案 (本地執行 OK，Streamlit Cloud 需改用雲端 API)
            
            # 準備要寫入 Excel 的精簡資料 (排除日期、門市等非數值欄位)
            excel_data = {
                '毛利': in_profit,
                '門號': in_number,
                '保險營收': in_insur,
                '配件營收': in_acc,
                '庫存手機': in_stock,
                '蘋果手機': in_apple,
                '蘋果平板+手錶': in_ipad,
                'VIVO手機': in_vivo,
                '生活圈': in_life,
                'GOOGLE 評論': in_review,
                '來客數': in_traffic,
                '遠傳續約累積GAP': in_gap,
                '遠傳升續率': in_up_rate,
                '遠傳平續率': in_flat_rate
            }

            # 執行寫入
            save_msg = update_excel_accumulate(selected_store, selected_user, input_date, excel_data)
            
            # 顯示結果
            if "✅" in save_msg:
                st.success(save_msg)
                # 同步更新網頁上的 Session State，讓儀表板也累加
                # (這裡邏輯稍微複雜，簡單做法是直接重整頁面讀取新 Excel，或手動更新 Session)
            else:
                st.error(save_msg)
                
# --- 6. 總表分析區 (Dashboard) - 只有選總表時出現 ---
if not is_input_mode and not filtered_df.empty:
    st.subheader("📊 詳細數據分析")
    
    # 依照人員/門市分組顯示
    group_col = '人員' if selected_user == "該店總表" else '門市'
    # 只取數值欄位進行加總
    numeric_cols = ['毛利', '門號', '保險營收', '配件營收', '綜合指標']
    summary = filtered_df.groupby(group_col)[numeric_cols].sum().reset_index()
    
    st.bar_chart(summary, x=group_col, y=['毛利', '保險營收', '配件營收'])
    st.dataframe(summary, use_container_width=True)

elif not is_input_mode:
    st.info("尚無數據，請先至「個人頁面」輸入資料。")

