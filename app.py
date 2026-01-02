import streamlit as st
import pandas as pd
from datetime import date, datetime
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="📈")

# 初始化 Session State
if 'preview_data' not in st.session_state: st.session_state.preview_data = None
if 'preview_score' not in st.session_state: st.session_state.preview_score = 0
if 'authenticated_store' not in st.session_state: st.session_state.authenticated_store = None
if 'admin_logged_in' not in st.session_state: st.session_state.admin_logged_in = False

# 檢查 Secrets
if "gcp_service_account" not in st.secrets:
    st.error("❌ 嚴重錯誤：Secrets 中找不到 [gcp_service_account]。")
    st.stop()
if "TARGET_FOLDER_ID" not in st.secrets:
    st.warning("⚠️ 警告：Secrets 中找不到 TARGET_FOLDER_ID。")

# 匯入 Google 套件
try:
    import gspread
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build # 仍需用於搜尋檔案 ID
except ImportError:
    st.error("❌ 缺少套件，請在 requirements.txt 加入 `gspread`")
    st.stop()

# --- 2. Google Sheets 連線功能 (核心) ---

def get_gspread_client():
    """建立 gspread 客戶端與 Drive API 服務"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # 另外建立 Drive Service 用於搜尋資料夾內的檔案 ID
    drive_service = build('drive', 'v3', credentials=creds)
    
    return client, drive_service

def get_sheet_id_by_name(drive_service, filename, folder_id):
    """
    在指定資料夾搜尋 Google Sheets 檔案 ID
    注意：Google Sheets 在 Drive API 中沒有副檔名，MimeType 為 application/vnd.google-apps.spreadsheet
    """
    query = f"name = '{filename}' and trashed = false and mimeType = 'application/vnd.google-apps.spreadsheet'"
    if folder_id:
        query += f" and '{folder_id}' in parents"
        
    results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
    items = results.get('files', [])
    
    if not items: return None, None
    return items[0]['id'], items[0]['webViewLink']

def update_google_sheet(store, staff, date_obj, data_dict):
    """直接更新 Google 試算表儲存格"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    # Google Sheet 檔名通常不帶 .xlsx，這裡假設您的檔名格式為 "2026_01_東門店業績日報表"
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"

    try:
        client, drive_service = get_gspread_client()
        
        # 1. 找到檔案 ID
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        if not file_id:
            return f"❌ 找不到試算表：[{filename}]。請確認已將 Excel 轉存為 Google 試算表格式，且位於正確資料夾。"

        # 2. 開啟試算表與分頁
        sh = client.open_by_key(file_id)
        
        try:
            ws = sh.worksheet(staff)
        except gspread.WorksheetNotFound:
            return f"❌ 找不到人員分頁：[{staff}]"

        # 3. 計算寫入列數 (邏輯：第 15 列為 1 號)
        target_row = 15 + (date_obj.day - 1)
        
        # 4. 定義欄位對應 (Col A=1, B=2...)
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8, 'VIVO手機': 9,
            '生活圈': 10, 'GOOGLE 評論': 11, '來客數': 12,
            '遠傳續約': 13,
            '遠傳續約累積GAP': 14, 
            '遠傳升續率': 15, 
            '遠傳平續率': 16,
            '綜合指標': 17
        }
        
        # 覆蓋模式的欄位
        overwrite_fields = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率', '綜合指標']
        
        # 5. 批次讀取舊資料以進行累加 (減少 API 呼叫次數)
        # 讀取該列目前的數值 (假設資料在 B 到 Q 欄 -> Col 2 to 17)
        # current_values = ws.row_values(target_row) # 這會讀整列，稍微處理一下
        
        # 為了精準更新，我們逐一 cell 更新 (gspread 的 batch_update 比較快，但逐格寫比較好懂)
        # 若要追求效能，可改用 batch_update。這裡為了穩定性，先逐格檢查。
        
        updates = []
        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                
                # 如果是覆蓋模式，直接加到更新清單
                if field in overwrite_fields:
                    updates.append({
                        'range': gspread.utils.rowcol_to_a1(target_row, col_idx),
                        'values': [[new_val]]
                    })
                else:
                    # 累加模式：先讀取舊值 (注意：這會增加 API 時間，若太慢可優化)
                    old_val = ws.cell(target_row, col_idx).value
                    # 處理舊值：可能是字串、None 或數字
                    try:
                        if old_val in [None, "", " "]: 
                            old_num = 0
                        else:
                            # 移除可能的逗號或貨幣符號
                            old_num = float(str(old_val).replace(",", "").replace("$", ""))
                    except ValueError:
                        old_num = 0
                        
                    final_val = old_num + new_val
                    updates.append({
                        'range': gspread.utils.rowcol_to_a1(target_row, col_idx),
                        'values': [[final_val]]
                    })

        # 執行批次更新
        if updates:
            ws.batch_update(updates)

        return f"✅ 資料已成功寫入：{filename}"

    except Exception as e:
        return f"❌ 寫入失敗: {str(e)}"

def read_google_sheet_data(store, date_obj):
    """讀取 Google 試算表資料用於預覽"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    
    try:
        client, drive_service = get_gspread_client()
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        
        if not file_id:
            return None, f"找不到試算表：{filename}", None

        sh = client.open_by_key(file_id)
        
        # 回傳：(Sheet物件, 檔名, 連結)
        return sh, filename, file_url

    except Exception as e:
        return None, str(e), None

def aggregate_all_stores_gs(date_obj):
    """(Google Sheets 版) 彙整所有分店當月數據"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service = get_gspread_client()
    
    all_data = []
    
    for store_name in STORES.keys():
        if store_name == "(ALL) 全店總表": continue
        
        filename = f"{date_obj.year}_{date_obj.month:02d}_{store_name}業績日報表"
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        
        store_stats = {
            "門市": store_name,
            "狀態": "❌ 未建立",
            "連結": file_url
        }

        if file_id:
            store_stats["狀態"] = "✅ 線上"
            # 若要進階：打開 Sheet 讀取 "總表" 分頁的加總值
            # sh = client.open_by_key(file_id)
            # ws = sh.worksheet("總表") ...
        
        all_data.append(store_stats)
        
    return pd.DataFrame(all_data)

# --- 3. 組織與目標 ---
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

# --- 4. 介面與權限邏輯 ---

st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()))

if selected_store == "(ALL) 全店總表":
    staff_options = []
    selected_user = "全店總覽"
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options)

st.title(f"📊 {selected_store} - {selected_user}")

# 權限驗證函式
def check_store_auth(current_store):
    if current_store == "(ALL) 全店總表":
        if st.session_state.admin_logged_in: return True
        st.info("🛡️ 此區域需要管理員權限")
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_input")
        if st.button("驗證管理員"):
            if admin_input == st.secrets.get("admin_password"):
                st.session_state.admin_logged_in = True
                st.rerun()
            else: st.error("❌ 密碼錯誤")
        return False

    if st.session_state.authenticated_store == current_store: return True

    st.info(f"🔒 請輸入【{current_store}】的專屬密碼")
    with st.form("store_login"):
        input_pass = st.text_input("密碼", type="password")
        login_btn = st.form_submit_button("登入")
        if login_btn:
            correct_pass = st.secrets["store_passwords"].get(current_store)
            if not correct_pass: st.error("⚠️ 未設定密碼")
            elif input_pass == correct_pass:
                st.session_state.authenticated_store = current_store
                st.success("登入成功！")
                st.rerun()
            else: st.error("❌ 密碼錯誤")
    return False

if not check_store_auth(selected_store):
    st.stop()

# =========================================================
# 主畫面邏輯
# =========================================================

if selected_store == "(ALL) 全店總表":
    st.success("✅ 管理員權限已解鎖")
    st.markdown("### 🏆 全公司業績戰情室 (Google Sheets 版)")
    
    col_date, _ = st.columns([1, 3])
    view_date = col_date.date_input("選擇檢視月份", date.today())
    
    if st.button("🔄 讀取全部分店狀態"):
        with st.spinner("正在搜尋雲端試算表..."):
            df_all_stores = aggregate_all_stores_gs(view_date)
            st.dataframe(
                df_all_stores, 
                column_config={
                    "連結": st.column_config.LinkColumn("雲端試算表")
                },
                use_container_width=True
            )

elif selected_user == "該店總表":
    st.markdown("### 📥 門市報表檢視中心 (Google Sheets)")
    
    col_d1, col_d2 = st.columns([1, 2])
    view_date = col_d1.date_input("選擇報表月份", date.today())

    if col_d1.button("📂 讀取雲端報表", use_container_width=True):
        with st.spinner("連線 Google Sheets..."):
            sh_obj, file_msg, file_link = read_google_sheet_data(selected_store, view_date)
            
            if sh_obj:
                st.session_state.current_excel_file = {
                    'sheet_obj': sh_obj, # 存入 Sheet 物件
                    'name': file_msg,
                    'link': file_link
                }
                st.success("✅ 試算表連線成功！")
            else:
                st.error(file_msg)
    
    if st.session_state.current_excel_file:
        file_data = st.session_state.current_excel_file
        st.divider()
        st.subheader(f"📄 試算表：{file_data['name']}")
        
        c_btn1, c_btn3 = st.columns([1, 1])
        if file_data.get('link'):
            c_btn1.link_button("🔗 前往 Google 試算表編輯", file_data['link'], type="primary", use_container_width=True)
        
        if c_btn3.button("🔄 重新整理", use_container_width=True):
            st.session_state.current_excel_file = None
            st.rerun()

        st.markdown("---")
        st.write("#### 👀 網頁內快速預覽")
        
        try:
            # 從 Sheet 物件讀取分頁
            sh = file_data['sheet_obj']
            # 取得所有分頁名稱
            # 注意：gspread 每次呼叫都是 API request，若分頁多會慢
            worksheets = sh.worksheets()
            sheet_names = [ws.title for ws in worksheets]
            
            col_sheet, _ = st.columns([1, 2])
            selected_sheet_name = col_sheet.selectbox("選擇要檢視的分頁", sheet_names)
            
            # 讀取數據
            ws = sh.worksheet(selected_sheet_name)
            data = ws.get_all_values()
            df_preview = pd.DataFrame(data)
            st.dataframe(df_preview, use_container_width=True)
            
        except Exception as e:
            st.warning(f"預覽載入失敗 (可能是連線逾時): {str(e)}")

else:
    # ----------------------------------------------------
    # 個人填寫模式 (Step 1 預覽 -> Step 2 上傳)
    # ----------------------------------------------------
    st.markdown("### 📝 今日業績回報")

    with st.form("daily_input_full"):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        st.markdown("---")

        # 1. 財務與門號
        st.subheader("💰 財務與門號")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100)
        in_number = c2.number_input("門號 (件)", min_value=0, step=1)
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100)
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100)

        # 2. 硬體銷售
        st.subheader("📱 硬體銷售")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1)
        in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1)
        in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1)
        in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1)

        # 3. 顧客經營
        st.subheader("🤝 顧客經營")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (件)", min_value=0, step=1)
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

        # 4. 遠傳專案
        st.subheader("📡 遠傳專案指標")
        t1, t2, t3, t4 = st.columns(4)
        in_renew = t1.number_input("遠傳續約 (件)", min_value=0, step=1)
        in_gap = t2.number_input("遠傳續約累積 GAP", step=1)
        in_up_rate_raw = t3.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        in_flat_rate_raw = t4.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        
        # 5. 綜合
        st.subheader("🏆 綜合評估")
        in_composite = st.number_input("綜合指標分數", min_value=0.0, step=0.1)
        
        check_btn = st.form_submit_button("🔍 預覽 (Step 1)", use_container_width=True)

        if check_btn:
            # 試算預覽
            score = 0 # 暫時簡化
            st.session_state.preview_data = {
                '毛利': in_profit, '門號': in_number, '保險營收': in_insur, '配件營收': in_acc,
                '庫存手機': in_stock, '蘋果手機': in_apple, '蘋果平板+手錶': in_ipad, 'VIVO手機': in_vivo,
                '生活圈': in_life, 'GOOGLE 評論': in_review, '來客數': in_traffic,
                '遠傳續約': in_renew,
                '遠傳續約累積GAP': in_gap, 
                '遠傳升續率': in_up_rate_raw / 100, 
                '遠傳平續率': in_flat_rate_raw / 100,
                '綜合指標': in_composite,
                '日期': input_date
            }
            st.rerun()

    if st.session_state.preview_data:
        st.divider()
        st.markdown("### 👀 確認資料")
        df_p = pd.DataFrame([st.session_state.preview_data])
        st.dataframe(df_p.drop(columns=['日期']), hide_index=True)
        
        col_ok, col_no = st.columns([1, 1])
        if col_ok.button("✅ 確認上傳至 Google Sheets (Step 2)", type="primary", use_container_width=True):
            progress_text = "寫入試算表中..."
            my_bar = st.progress(0, text=progress_text)
            
            try:
                data_copy = st.session_state.preview_data.copy()
                t_date = data_copy.pop('日期')
                my_bar.progress(50, text="連線 API...")
                
                msg = update_google_sheet(selected_store, selected_user, t_date, data_copy)
                my_bar.progress(100)
                
                if "✅" in msg:
                    st.success(msg)
                    st.balloons()
                    st.session_state.preview_data = None
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(msg)
            except Exception as e:
                st.error(f"錯誤: {e}")
        
        if col_no.button("❌ 取消"):
            st.session_state.preview_data = None
            st.rerun()
