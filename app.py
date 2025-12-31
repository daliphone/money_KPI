import streamlit as st
import pandas as pd
import openpyxl
import os
from io import BytesIO
from datetime import date
import calendar

# --- 1. 系統初始化與除錯模式 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="🏢")

# 顯示環境狀態 (測試成功後可刪除)
st.sidebar.success("✅ 系統啟動成功！")

# 檢查 Secrets 是否存在
if "gcp_service_account" not in st.secrets:
    st.error("❌ 嚴重錯誤：找不到 [gcp_service_account] 設定，請檢查 Secrets。")
    st.stop()
if "TARGET_FOLDER_ID" not in st.secrets:
    st.warning("⚠️ 警告：找不到 TARGET_FOLDER_ID，雲端存取功能將失效。")

# --- 2. 密碼驗證模組 (修復版) ---
def check_password():
    """Returns `True` if the user had the correct password."""
    
    # 如果 Secrets 裡沒設定密碼，就直接放行 (方便測試)
    if "app_password" not in st.secrets:
        st.warning("⚠️ 未設定 app_password，目前為無密碼模式。")
        return True

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.text_input(
            "請輸入戰情室密碼", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.text_input(
            "請輸入戰情室密碼", type="password", on_change=password_entered, key="password"
        )
        st.error("❌ 密碼錯誤")
        return False
    else:
        # Password correct.
        return True

# --- 3. 執行密碼檢查 ---
if not check_password():
    st.stop()  # 如果沒通過，就停在這裡，不載入後面的程式

# ==========================================
# ⬇️ 密碼通過後，才會執行以下主程式 ⬇️
# ==========================================

# 引入 Google 套件 (延遲引入，避免一開始就崩潰)
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    st.error("❌ Google 套件未安裝，請檢查 requirements.txt")
    st.stop()

# --- 雲端存取函式 ---
def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"]) # 轉為 dict 避免格式問題
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_file_id_in_folder(service, filename, folder_id):
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if not items: return None
    return items[0]['id']

def update_excel_drive(store, staff, date_obj, data_dict):
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    if not folder_id: return "❌ 未設定資料夾 ID"
    
    # 這裡假設檔名格式，請務必確認您的 Google Drive 檔名
    filename = f"2025_12_{store}業績日報表.xlsx" 
    # 若要全自動日期： filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表.xlsx"

    try:
        service = get_drive_service()
        file_id = get_file_id_in_folder(service, filename, folder_id)
        
        if not file_id:
            return f"❌ 雲端找不到檔案 [{filename}]，請確認檔名與資料夾位置。"

        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        excel_stream = BytesIO(file_content)
        
        wb = openpyxl.load_workbook(excel_stream)
        
        if staff not in wb.sheetnames:
            return f"❌ 找不到分頁：{staff}"
        
        ws = wb[staff]
        target_row = 15 + (date_obj.day - 1)
        
        # 欄位對應
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8, 'VIVO手機': 9,
            '生活圈': 10, 'GOOGLE 評論': 11, '來客數': 12,
            '遠傳續約累積GAP': 13, '遠傳升續率': 14, '遠傳平續率': 15
        }
        overwrite_fields = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率']
        
        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                cell = ws.cell(row=target_row, column=col_idx)
                old_val = cell.value if isinstance(cell.value, (int, float)) else 0
                
                if field in overwrite_fields:
                    cell.value = new_val
                else:
                    cell.value = old_val + new_val

        output_stream = BytesIO()
        wb.save(output_stream)
        output_stream.seek(0)
        
        media = MediaIoBaseUpload(output_stream, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        service.files().update(fileId=file_id, media_body=media).execute()
        
        return f"✅ 資料已同步至雲端！({filename})"

    except Exception as e:
        return f"❌ 錯誤: {str(e)}"

# --- 介面邏輯 ---
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

if 'db' not in st.session_state:
    st.session_state.records = pd.DataFrame(columns=['門市', '人員', '日期', '毛利', '門號', '保險營收', '配件營收', '綜合指標'])
    st.session_state.targets = {'毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21}

st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("選擇門市", list(STORES.keys()))

if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("選擇人員", staff_options)

st.title(f"📊 {selected_store} - {selected_user}")

# 只有選個人時顯示輸入框
if selected_store != "(ALL) 全店總表" and selected_user != "該店總表":
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        input_date = col1.date_input("日期", date.today())
        in_profit = col2.number_input("毛利", step=100)
        in_number = col2.number_input("門號", step=1)
        # ... (這裡省略部分欄位以簡化測試，您可以自己補上) ...
        
        submit = st.form_submit_button("🚀 提交測試")
        
        if submit:
            data = {'毛利': in_profit, '門號': in_number}
            msg = update_excel_drive(selected_store, selected_user, input_date, data)
            if "✅" in msg:
                st.success(msg)
            else:
                st.error(msg)
else:
    st.info("請選擇一位人員進行輸入測試。")
