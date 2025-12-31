import streamlit as st
import pandas as pd
import openpyxl
import os
from datetime import date
import calendar

# --- [新增] 存檔與累加功能函式 ---
def update_excel_accumulate(store, staff, date_obj, data_dict):
    """
    將資料寫回 Excel，並執行累加邏輯
    """
    # 組合檔名 (假設檔案都在同一層資料夾)
    # 若你的檔名是 "東門店業績日報表.xlsx"，請確保 store 變數是 "東門店"
    filename = f"{store}業績日報表.xlsx"
    
    # 簡單防呆：如果是 "(ALL) 全店總表" 這種名稱，不執行存檔
    if "全店" in store or "總表" in store:
        return "⚠️ 總表模式無法存檔，請選擇具體門市與人員。"

    if not os.path.exists(filename):
        return f"❌ 找不到檔案：{filename}，請確認 Excel 檔案是否已上傳到同目錄。"

    try:
        # 載入 Excel (data_only=False 以保留公式)
        wb = openpyxl.load_workbook(filename)
        
        # 檢查是否有該人員的分頁
        if staff not in wb.sheetnames:
            return f"❌ 找不到人員分頁：[{staff}]，請確認 Excel 分頁名稱是否與選單一致。"
        
        ws = wb[staff]
        
        # 計算寫入的列號 (Row)
        # 根據你的 Excel：Row 15 對應 "1號"
        target_row = 15 + (date_obj.day - 1)
        
        # 雙重確認：檢查該列的 A 欄 (第1欄) 是否真的是該日期
        check_day = ws.cell(row=target_row, column=1).value
        # 有些 Excel 讀出來是 int, 有些是 str，轉字串比對較保險
        if str(check_day) != str(date_obj.day):
            return f"⚠️ 日期定位錯誤！Excel 第 {target_row} 列是 {check_day} 號，但你要填 {date_obj.day} 號。"

        # 定義欄位對應 (Column Map) A=1, B=2...
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8, 'VIVO手機': 9,
            '生活圈': 10, 'GOOGLE 評論': 11, '來客數': 12,
            '遠傳續約累積GAP': 13, '遠傳升續率': 14, '遠傳平續率': 15
        }

        # 覆蓋模式的欄位 (Snapshot)
        overwrite_fields = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率']

        updated_msg = [] 

        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                cell = ws.cell(row=target_row, column=col_idx)
                
                # 取得舊數值 (若為 None 轉為 0)
                old_val = cell.value
                if old_val is None or not isinstance(old_val, (int, float)):
                    old_val = 0
                
                # 判斷累加或覆蓋
                if field in overwrite_fields:
                    final_val = new_val
                    op_msg = "(覆蓋)"
                else:
                    final_val = old_val + new_val
                    op_msg = f"(累加 {old_val}+{new_val})"

                # 寫入
                cell.value = final_val
                updated_msg.append(f"{field}: {final_val} {op_msg}")

        # 存檔
        wb.save(filename)
        return f"✅ {date_obj} 資料已成功寫入並存檔！\n"

    except Exception as e:
        return f"❌ 存檔失敗: {str(e)}"

# --- 1. 系統初始化 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="🏢")

# 定義組織與人員結構
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

# 初始化 Session State
if 'db' not in st.session_state:
    st.session_state.records = pd.DataFrame(columns=[
        '門市', '人員', '日期', '毛利', '門號', '保險營收', '配件營收', 
        '庫存手機', '蘋果手機', '蘋果平板+手錶', 'VIVO手機',
        '生活圈', 'GOOGLE 評論', '來客數', '遠傳續約累積GAP', 
        '遠傳升續率', '遠傳平續率', '綜合指標'
    ])
    st.session_state.targets = {
        '毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21
    }

# --- 2. 側邊欄導航 ---
st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("選擇門市", list(STORES.keys()))

if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("選擇人員 / 檢視層級", staff_options)

st.sidebar.markdown("---")
st.sidebar.caption(f"操作身份：{selected_store} - {selected_user}")

# --- 3. 邏輯核心 ---
is_input_mode = False
if selected_store != "(ALL) 全店總表" and selected_user != "該店總表":
    is_input_mode = True

# 篩選資料 (用於儀表板)
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

# --- 4. 儀表板顯示區 ---
st.title(view_title)

# 簡單計算加總 (用於顯示上方卡片)
current_stats = {
    '毛利': filtered_df['毛利'].sum() if not filtered_df.empty else 0,
    '門號': filtered_df['門號'].sum() if not filtered_df.empty else 0,
    '保險': filtered_df['保險營收'].sum() if not filtered_df.empty else 0,
    '配件': filtered_df['配件營收'].sum() if not filtered_df.empty else 0,
}

# 簡單目標 (僅供顯示用)
multiplier = 8 if selected_store == "(ALL) 全店總表" else (4 if selected_user == "該店總表" else 1)
target_stats = {k: v * multiplier for k, v in st.session_state.targets.items() if k in current_stats}

# 顯示 Metrics
col1, col2, col3, col4 = st.columns(4)
today = date.today()
last_day = calendar.monthrange(today.year, today.month)[1]
remaining_days = max(0, last_day - today.day)

def show_metric(col, label, current, target):
    gap = target - current
    achieve = (current/target)*100 if target>0 else 0
    mom = gap/remaining_days if remaining_days>0 and gap>0 else 0
    with col:
        st.metric(label, f"{current:,}", f"{achieve:.1f}% (GAP: {gap:,})")
        if gap>0: st.caption(f"🔥 每日需達: {int(mom):,}")

show_metric(col1, "💰 毛利", current_stats['毛利'], st.session_state.targets['毛利']*multiplier)
show_metric(col2, "📱 門號", current_stats['門號'], st.session_state.targets['門號']*multiplier)
show_metric(col3, "🛡️ 保險", current_stats['保險'], st.session_state.targets['保險']*multiplier)
show_metric(col4, "🔌 配件", current_stats['配件'], st.session_state.targets['配件']*multiplier)

st.divider()

# --- 5. 資料輸入區 (包含 Excel 寫入) ---
if is_input_mode:
    st.markdown(f"### 📝 {selected_user} - 今日業績回報")
    st.info("💡 系統將自動累加至 Excel，請輸入「今日新增」的數值。")

    with st.form("daily_input_full", clear_on_submit=True):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        
        st.markdown("---")
        # 第一區：財務
        st.subheader("💰 財務與門號")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100)
        in_number = c2.number_input("門號 (件)", min_value=0, step=1)
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100)
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100)

        # 第二區：硬體
        st.subheader("📱 硬體銷售")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1)
        in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1)
        in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1)
        in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1)

        # 第三區：服務
        st.subheader("🤝 顧客經營")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (件)", min_value=0, step=1)
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

        # 第四區：遠傳指標
        st.subheader("📡 遠傳專案指標")
        t1, t2, t3 = st.columns(3)
        in_gap = t1.number_input("遠傳續約累積 GAP", step=1)
        in_up_rate_raw = t2.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        in_flat_rate_raw = t3.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        
        in_up_rate = in_up_rate_raw / 100
        in_flat_rate = in_flat_rate_raw / 100

        st.markdown("---")
        submit = st.form_submit_button("🚀 提交並寫入 Excel", use_container_width=True)

        if submit:
            # 1. 綜合指標試算 (Session State 模擬用)
            targets = st.session_state.targets
            def calc(act, tgt, w): return (act/tgt*w) if tgt>0 else 0
            
            total_score = (
                calc(in_profit, targets['毛利'], 0.25) + 
                calc(in_number, targets['門號'], 0.20) + 
                calc(in_insur, targets['保險'], 0.15) + 
                calc(in_acc, targets['配件'], 0.15) + 
                calc(in_stock, targets['庫存'], 0.15)
            )

            # 2. 準備寫入 Excel 的資料字典
            # 這些 key 必須跟 update_excel_accumulate 裡的 col_map 一樣
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
            
            # 3. 呼叫存檔函式
            save_result = update_excel_accumulate(selected_store, selected_user, input_date, excel_data)

            # 4. 顯示結果
            if "✅" in save_result:
                st.success(save_result)
                st.info(f"本次綜合指標得分估算：{total_score*100:.1f} 分")
                
                # 同步更新網頁顯示 (Optional: 寫入 Session State 讓儀表板跳動)
                new_record = excel_data.copy()
                new_record.update({'門市': selected_store, '人員': selected_user, '日期': input_date, '綜合指標': total_score})
                st.session_state.records = pd.concat([st.session_state.records, pd.DataFrame([new_record])], ignore_index=True)
            else:
                st.error(save_result)

# --- 6. 總表分析區 ---
if not is_input_mode and not filtered_df.empty:
    st.subheader("📊 數據分佈")
    group_col = '人員' if selected_user == "該店總表" else '門市'
    st.bar_chart(filtered_df.groupby(group_col)[['毛利', '保險營收']].sum())
    st.dataframe(filtered_df, use_container_width=True)
elif not is_input_mode:
    st.info("目前無暫存數據，請至人員頁面輸入，或確認 Excel 是否有資料讀入。")
