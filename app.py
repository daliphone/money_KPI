import streamlit as st
import pandas as pd
import openpyxl
from io import BytesIO
from datetime import date
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="📈")

# 初始化 Session State
if 'preview_data' not in st.session_state: st.session_state.preview_data = None
if 'preview_score' not in st.session_state: st.session_state.preview_score = 0
# 用來記錄目前已登入的門市
if 'authenticated_store' not in st.session_state: st.session_state.authenticated_store = None

# 檢查必要設定
if "gcp_service_account" not in st.secrets:
    st.error("❌ 嚴重錯誤：Secrets 中找不到 [gcp_service_account]。")
    st.stop()
if "TARGET_FOLDER_ID" not in st.secrets:
    st.warning("⚠️ 警告：Secrets 中找不到 TARGET_FOLDER_ID。")

# Google 套件
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    st.error("❌ 缺少 Google 套件，請檢查 requirements.txt")
    st.stop()

# --- 2. Google Drive 功能 (全域搜尋版) ---
def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)

def get_file_id_in_folder(service, filename, folder_id):
    """全域搜尋檔案，不限制資料夾"""
    query = f"name = '{filename}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)", orderBy="createdTime desc").execute()
    items = results.get('files', [])
    if not items: return None
    return items[0]['id']

def update_excel_drive(store, staff, date_obj, data_dict):
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表.xlsx"
    
    try:
        service = get_drive_service()
        file_id = get_file_id_in_folder(service, filename, folder_id)
        if not file_id:
            return f"❌ 找不到檔案 [{filename}]，請確認雲端硬碟檔名格式正確 (YYYY_MM_店名...)。"

        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        excel_stream = BytesIO(file_content)
        
        wb = openpyxl.load_workbook(excel_stream)
        if staff not in wb.sheetnames:
            return f"❌ 找不到人員分頁：[{staff}]"
        
        ws = wb[staff]
        target_row = 15 + (date_obj.day - 1)
        
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
        
        return f"✅ 資料已成功寫入：{filename}"

    except Exception as e:
        return f"❌ 系統錯誤: {str(e)}"

# --- 3. 組織設定 ---
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
    "鳳山店": ["店長", "組員"]
}
DEFAULT_TARGETS = {'毛利': 140000, '門號': 24, '保險': 28000, '配件': 35000, '庫存': 21}

# --- 4. 介面與權限邏輯 (核心修改) ---

st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()))

# 根據門市決定人員選單
if selected_store == "(ALL) 全店總表":
    staff_options = []
    selected_user = "全店總覽"
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options)

st.title(f"📊 {selected_store} - {selected_user}")

# --- 權限驗證函式 ---
def check_store_auth(current_store):
    """
    驗證當前選擇的門市是否已登入
    """
    # 1. 如果是全店總表，走管理員驗證邏輯
    if current_store == "(ALL) 全店總表":
        if st.session_state.get("admin_logged_in", False):
            return True
            
        st.info("🛡️ 此區域需要管理員權限")
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_input")
        if st.button("驗證管理員"):
            if admin_input == st.secrets.get("admin_password"):
                st.session_state["admin_logged_in"] = True
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
        return False

    # 2. 如果是各分店，走分店密碼驗證邏輯
    # 檢查是否已經登入過「這一家」店
    if st.session_state.authenticated_store == current_store:
        return True

    # 尚未登入，顯示輸入框
    st.info(f"🔒 請輸入【{current_store}】的專屬密碼以進行操作")
    
    # 使用 form 避免每打一個字就重新整理
    with st.form("store_login"):
        input_pass = st.text_input("密碼", type="password")
        login_btn = st.form_submit_button("登入")
        
        if login_btn:
            # 從 secrets 取得該店密碼
            # 注意：secrets["store_passwords"] 是一個字典
            correct_pass = st.secrets["store_passwords"].get(current_store)
            
            if not correct_pass:
                st.error("⚠️ 此門市尚未設定密碼，請聯繫管理員。")
            elif input_pass == correct_pass:
                st.session_state.authenticated_store = current_store
                st.success("登入成功！")
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
                
    return False

# --- 主程式邏輯 ---

# 先執行權限檢查，如果沒通過，程式就停在這裡，不顯示下面的表單
if not check_store_auth(selected_store):
    st.stop()

# =========================================================
# 驗證通過後，顯示該店內容
# =========================================================

if selected_store == "(ALL) 全店總表":
    st.success("✅ 管理員權限已解鎖")
    st.markdown("### 🏆 全公司業績戰情室")
    st.info("此處未來可串接 PowerBI 或讀取所有分店 Excel 進行彙整。")

else:
    # 這裡顯示分店的操作介面
    is_input_mode = (selected_user != "該店總表")
    
    if is_input_mode:
        st.markdown("### 📝 今日業績回報")

        # Step 1: 填寫表單
        with st.form("daily_input_full"):
            d_col1, d_col2 = st.columns([1, 3])
            input_date = d_col1.date_input("📅 報表日期", date.today())
            st.markdown("---")

            st.subheader("💰 財務與門號 (Core)")
            c1, c2, c3, c4 = st.columns(4)
            in_profit = c1.number_input("毛利 ($)", min_value=0, step=100)
            in_number = c2.number_input("門號 (件)", min_value=0, step=1)
            in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100)
            in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100)

            st.subheader("📱 硬體銷售 (Hardware)")
            h1, h2, h3, h4 = st.columns(4)
            in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1)
            in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1)
            in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1)
            in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1)

            st.subheader("🤝 顧客經營 (Service)")
            s1, s2, s3 = st.columns(3)
            in_life = s1.number_input("生活圈 (件)", min_value=0, step=1)
            in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
            in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

            st.subheader("📡 遠傳專案指標 (覆蓋)")
            t1, t2, t3 = st.columns(3)
            in_gap = t1.number_input("遠傳續約累積 GAP", step=1)
            in_up_rate_raw = t2.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
            in_flat_rate_raw = t3.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
            
            check_btn = st.form_submit_button("🔍 試算分數並預覽 (Step 1)", use_container_width=True)

            if check_btn:
                def calc(act, tgt, w): return (act / tgt * w) if tgt > 0 else 0
                score = (
                    calc(in_profit, DEFAULT_TARGETS['毛利'], 0.25) + 
                    calc(in_number, DEFAULT_TARGETS['門號'], 0.20) + 
                    calc(in_insur, DEFAULT_TARGETS['保險'], 0.15) + 
                    calc(in_acc, DEFAULT_TARGETS['配件'], 0.15) + 
                    calc(in_stock, DEFAULT_TARGETS['庫存'], 0.15)
                )
                
                st.session_state.preview_data = {
                    '毛利': in_profit, '門號': in_number, '保險營收': in_insur, '配件營收': in_acc,
                    '庫存手機': in_stock, '蘋果手機': in_apple, '蘋果平板+手錶': in_ipad, 'VIVO手機': in_vivo,
                    '生活圈': in_life, 'GOOGLE 評論': in_review, '來客數': in_traffic,
                    '遠傳續約累積GAP': in_gap, 
                    '遠傳升續率': in_up_rate_raw / 100, 
                    '遠傳平續率': in_flat_rate_raw / 100,
                    '日期': input_date
                }
                st.session_state.preview_score = score
                st.rerun()

        # Step 2: 確認上傳
        if st.session_state.preview_data:
            st.divider()
            st.markdown("### 👀 請確認下方資料是否正確？")
            
            df_preview = pd.DataFrame([st.session_state.preview_data])
            st.dataframe(df_preview, hide_index=True)
            
            if st.session_state.preview_score > 0:
                st.info(f"💡 預估綜合指標貢獻：{st.session_state.preview_score*100:.1f} 分")

            col_confirm, col_cancel = st.columns([1, 1])
            
            if col_confirm.button("✅ 確認無誤，立即上傳 (Step 2)", type="primary", use_container_width=True):
                progress_text = "連線 Google Drive 中...請稍候"
                my_bar = st.progress(0, text=progress_text)
                
                try:
                    data_to_save = st.session_state.preview_data.copy()
                    target_date = data_to_save.pop('日期')
                    
                    my_bar.progress(30, text="正在搜尋雲端檔案...")
                    result_msg = update_excel_drive(selected_store, selected_user, target_date, data_to_save)
                    my_bar.progress(100, text="處理完成！")
                    
                    if "✅" in result_msg:
                        st.success(result_msg)
                        st.balloons()
                        st.session_state.preview_data = None
                        st.session_state.preview_score = 0
                        time.sleep(3)
                        st.rerun()
                    else:
                        st.error(result_msg)
                        
                except Exception as e:
                    st.error(f"❌ 發生未預期的錯誤: {str(e)}")
            
            if col_cancel.button("❌ 有錯誤，重新填寫", use_container_width=True):
                st.session_state.preview_data = None
                st.rerun()
    else:
        st.info(f"歡迎來到 {selected_store} 門市總表 (開發中)")
