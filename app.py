import streamlit as st
import pandas as pd
import openpyxl
from io import BytesIO
from datetime import date
import time

# --- 1. 系統初始化與設定 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="📈")

# 檢查必要設定是否存在
if "gcp_service_account" not in st.secrets:
    st.error("❌ 嚴重錯誤：Secrets 中找不到 [gcp_service_account]。")
    st.stop()
if "TARGET_FOLDER_ID" not in st.secrets:
    st.warning("⚠️ 警告：Secrets 中找不到 TARGET_FOLDER_ID，無法存檔。")

# 引入 Google 套件 (延遲引入以防崩潰)
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    st.error("❌ 缺少 Google 套件，請檢查 requirements.txt")
    st.stop()

# --- 2. 密碼驗證模組 ---
def check_password():
    """檢查使用者是否輸入正確密碼"""
    if "app_password" not in st.secrets:
        return True # 若未設定密碼則直接通過

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 請輸入戰情室密碼", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 請輸入戰情室密碼", type="password", on_change=password_entered, key="password")
        st.error("❌ 密碼錯誤")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- 3. Google Drive 連線函式 ---
def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_file_id_in_folder(service, filename, folder_id):
    """在指定資料夾搜尋特定檔名"""
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if not items: return None
    return items[0]['id']

def update_excel_drive(store, staff, date_obj, data_dict):
    """核心功能：下載 -> 修改(累加/覆蓋) -> 上傳"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    
    # 自動產生檔名格式：YYYY_MM_店名業績日報表.xlsx
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表.xlsx"
    
    try:
        service = get_drive_service()
        file_id = get_file_id_in_folder(service, filename, folder_id)
        
        if not file_id:
            return f"❌ 雲端找不到檔案 [{filename}]。\n請確認：\n1. 檔名是否正確包含年月\n2. 檔案是否在指定資料夾內"

        # 下載檔案
        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        excel_stream = BytesIO(file_content)
        
        # 開啟 Excel
        wb = openpyxl.load_workbook(excel_stream)
        
        if staff not in wb.sheetnames:
            return f"❌ 檔案中找不到人員分頁：[{staff}]，請確認 Excel 分頁名稱。"
        
        ws = wb[staff]
        
        # 定位列數 (假設每月1號從 Row 15 開始)
        target_row = 15 + (date_obj.day - 1)
        
        # 定義欄位對應表 (Column Mapping) A=1, B=2...
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8, 'VIVO手機': 9,
            '生活圈': 10, 'GOOGLE 評論': 11, '來客數': 12,
            '遠傳續約累積GAP': 13, '遠傳升續率': 14, '遠傳平續率': 15
        }
        
        # 定義哪些欄位是「覆蓋」(Snapshot)，其餘預設為「累加」(Accumulate)
        overwrite_fields = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率']
        
        log_msg = [] # 紀錄變更日誌
        
        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                cell = ws.cell(row=target_row, column=col_idx)
                
                # 取得舊值 (處理 None 或非數字的情況)
                old_val = cell.value
                if old_val is None or not isinstance(old_val, (int, float)):
                    old_val = 0
                
                if field in overwrite_fields:
                    cell.value = new_val # 覆蓋
                    # log_msg.append(f"{field}: {new_val} (覆蓋)")
                else:
                    cell.value = old_val + new_val # 累加
                    # log_msg.append(f"{field}: {old_val} + {new_val} = {cell.value}")

        # 存回記憶體並上傳
        output_stream = BytesIO()
        wb.save(output_stream)
        output_stream.seek(0)
        
        media = MediaIoBaseUpload(output_stream, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        service.files().update(fileId=file_id, media_body=media).execute()
        
        return f"✅ 資料已成功寫入雲端檔案：{filename}"

    except Exception as e:
        return f"❌ 系統錯誤: {str(e)}"

# --- 4. 組織架構設定 (請依實際情況增減) ---
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
    "鳳山店": ["店長", "組員"] # 範例
}

# 預設目標 (用於即時算分模擬，實際目標以 Excel 內為準)
DEFAULT_TARGETS = {
    '毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21
}

# --- 5. 介面與邏輯 ---
st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()))

if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options)

st.title(f"📊 {selected_store} - {selected_user}")

# 判斷模式
is_input_mode = (selected_store != "(ALL) 全店總表" and selected_user != "該店總表")

if is_input_mode:
    st.markdown("### 📝 今日業績回報")
    st.info("💡 數值將「累加」至 Excel，GAP/比率類則為「覆蓋」。請輸入**今日新增**的業績。")

    with st.form("daily_input_full", clear_on_submit=True):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        
        st.markdown("---")

        # --- 第一區：核心營收 ---
        st.subheader("💰 財務與門號 (Core)")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100, help="權重 25% (累加)")
        in_number = c2.number_input("門號 (件)", min_value=0, step=1, help="權重 20% (累加)")
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100, help="權重 15% (累加)")
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100, help="權重 15% (累加)")

        # --- 第二區：硬體銷售 ---
        st.subheader("📱 硬體銷售 (Hardware)")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1, help="權重 15% (累加)")
        in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1, help="權重 10% (累加)")
        in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1, help="權重 10% (累加)")
        in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1, help="權重 5% (累加)")

        # --- 第三區：服務指標 ---
        st.subheader("🤝 顧客經營 (Service)")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (件)", min_value=0, step=1, help="(累加)")
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1, help="(累加)")
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1, help="(累加)")

        # --- 第四區：遠傳指標 ---
        st.subheader("📡 遠傳專案指標 (覆蓋更新)")
        t1, t2, t3 = st.columns(3)
        in_gap = t1.number_input("遠傳續約累積 GAP", step=1, help="請填寫當下總數 (覆蓋)")
        in_up_rate_raw = t2.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1, help="請填寫當下比率 (覆蓋)")
        in_flat_rate_raw = t3.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1, help="請填寫當下比率 (覆蓋)")
        
        in_up_rate = in_up_rate_raw / 100
        in_flat_rate = in_flat_rate_raw / 100

        st.markdown("---")
        submit = st.form_submit_button("🚀 提交並寫入 Excel", use_container_width=True)

        if submit:
            # 1. 前端即時算分 (僅供參考，不寫入 Excel 綜合指標欄位，讓 Excel 公式自己算)
            def calc(act, tgt, w): return (act / tgt * w) if tgt > 0 else 0
            # 這裡簡單使用預設目標做即時回饋，實際分數以 Excel 報表為準
            score = (
                calc(in_profit, DEFAULT_TARGETS['毛利'], 0.25) + 
                calc(in_number, DEFAULT_TARGETS['門號'], 0.20) + 
                calc(in_insur, DEFAULT_TARGETS['保險'], 0.15) + 
                calc(in_acc, DEFAULT_TARGETS['配件'], 0.15) + 
                calc(in_stock, DEFAULT_TARGETS['庫存'], 0.15)
            )
            
            # 2. 準備寫入資料
            data_to_save = {
                '毛利': in_profit, '門號': in_number, '保險營收': in_insur, '配件營收': in_acc,
                '庫存手機': in_stock, '蘋果手機': in_apple, '蘋果平板+手錶': in_ipad, 'VIVO手機': in_vivo,
                '生活圈': in_life, 'GOOGLE 評論': in_review, '來客數': in_traffic,
                '遠傳續約累積GAP': in_gap, '遠傳升續率': in_up_rate, '遠傳平續率': in_flat_rate
            }
            
            # 3. 呼叫雲端寫入
            with st.spinner("正在連線 Google Drive 同步資料..."):
                result_msg = update_excel_drive(selected_store, selected_user, input_date, data_to_save)
            
            # 4. 顯示結果
            if "✅" in result_msg:
                st.success(result_msg)
                st.balloons()
                # 顯示當次提交摘要
                st.write("本次提交數據預覽：")
                st.dataframe(pd.DataFrame([data_to_save]), hide_index=True)
                if score > 0:
                    st.info(f"💡 本次輸入貢獻約可增加綜合指標：{score*100:.2f} 分 (僅供參考)")
            else:
                st.error(result_msg)

else:
    # 總表檢視模式 (未來可擴充 PowerBI 或讀取 Excel 彙整)
    st.info("👋 歡迎來到全店業績戰情室！")
    st.markdown("""
    - 請從左側選擇 **門市** 與 **人員** 進行日報表填寫。
    - 系統會自動讀取對應月份的 Excel 檔案 (例如 `2025_12_東門店業績日報表.xlsx`)。
    - 財務與商品數量將自動 **累加**，指標類數據將 **覆蓋** 更新。
    """)
    if selected_store == "(ALL) 全店總表":
        st.image("https://streamlit.io/images/brand/streamlit-logo-secondary-colormark-darktext.png", width=200)
        st.caption("全店總表功能開發中...")
