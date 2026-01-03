import streamlit as st
import pandas as pd
from datetime import date, datetime
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="📈")

# 初始化 Session State
if 'preview_data' not in st.session_state: st.session_state.preview_data = None
if 'authenticated_store' not in st.session_state: st.session_state.authenticated_store = None
if 'admin_logged_in' not in st.session_state: st.session_state.admin_logged_in = False
if 'current_excel_file' not in st.session_state: st.session_state.current_excel_file = None

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
    from googleapiclient.discovery import build 
except ImportError:
    st.error("❌ 缺少必要套件，請檢查 requirements.txt 是否包含：gspread, google-auth, google-api-python-client")
    st.stop()

# --- 2. Google Sheets 連線功能 ---

def get_gspread_client():
    """建立 gspread 客戶端與 Drive API 服務"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return client, drive_service, creds.service_account_email

def debug_list_files(drive_service, folder_id):
    """(除錯用) 列出資料夾內前 5 個檔案"""
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, pageSize=10, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        return files
    except Exception as e:
        return f"無法列出檔案: {str(e)}"

def get_sheet_id_by_name(drive_service, filename, folder_id):
    """搜尋檔案 ID"""
    # 嚴格比對檔名 (不含副檔名，因為 Google Sheet 在 API 中沒有 .xlsx 後綴)
    query = f"name = '{filename}' and trashed = false"
    if folder_id:
        query += f" and '{folder_id}' in parents" 
    
    try:
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink, mimeType)").execute()
        items = results.get('files', [])
        
        if not items: 
            return None, "NOT_FOUND"
        
        # 檢查是否為 Google Sheet
        file_info = items[0]
        if "spreadsheet" not in file_info.get('mimeType', ''):
            return None, "FOUND_BUT_NOT_SHEET" # 找到同名檔案但它是 Excel/Word 等

        return file_info['id'], file_info['webViewLink']
    except Exception as e:
        return None, f"API_ERROR: {str(e)}"

def safe_float(value):
    """將表格內容轉為浮點數，失敗回傳 0"""
    try:
        if value in [None, "", " "]: return 0.0
        clean_val = str(value).replace(",", "").replace("$", "").replace("%", "").strip()
        if not clean_val: return 0.0
        return float(clean_val)
    except ValueError:
        return 0.0

def update_google_sheet(store, staff, date_obj, data_dict):
    """寫入單一門市單一人員數據"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"

    try:
        client, drive_service, email = get_gspread_client()
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        
        if file_url == "NOT_FOUND":
            return f"❌ 找不到檔案：[{filename}]。請確認檔名是否完全一致 (Google Sheet 不需 .xlsx 副檔名)。"
        if file_url == "FOUND_BUT_NOT_SHEET":
            return f"❌ 找到檔案 [{filename}] 但它是 Excel (.xlsx)。請在 Drive 點右鍵 > 選擇「Google 試算表」開啟 > 另存為 Google 試算表。"
        if str(file_url).startswith("API_ERROR"):
            return f"❌ API 搜尋錯誤：{file_url}"

        sh = client.open_by_key(file_id)
        try:
            ws = sh.worksheet(staff)
        except gspread.WorksheetNotFound:
            return f"❌ 找不到人員分頁：[{staff}]"

        target_row = 15 + (date_obj.day - 1)
        
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8, 'VIVO手機': 9,
            '生活圈': 10, 'GOOGLE 評論': 11, '來客數': 12,
            '遠傳續約': 13, '遠傳續約累積GAP': 14, 
            '遠傳升續率': 15, '遠傳平續率': 16, '綜合指標': 17
        }
        overwrite_fields = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率', '綜合指標']
        
        updates = []
        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                if field in overwrite_fields:
                    updates.append({'range': gspread.utils.rowcol_to_a1(target_row, col_idx), 'values': [[new_val]]})
                else:
                    old_val = ws.cell(target_row, col_idx).value
                    final_val = safe_float(old_val) + new_val
                    updates.append({'range': gspread.utils.rowcol_to_a1(target_row, col_idx), 'values': [[final_val]]})

        if updates: ws.batch_update(updates)
        return f"✅ 資料已成功寫入：{filename}"

    except Exception as e:
        return f"❌ 系統錯誤: {str(e)}"

# --- 讀取特定 Sheet 的共用函式 ---
def read_specific_sheet(filename, sheet_name):
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    try:
        client, drive_service, email = get_gspread_client()
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        
        # 詳細錯誤處理
        if file_url == "NOT_FOUND":
            # 除錯：列出資料夾內有的檔案，幫使用者找原因
            files_in_folder = debug_list_files(drive_service, folder_id)
            file_names = [f['name'] for f in files_in_folder] if isinstance(files_in_folder, list) else str(files_in_folder)
            return None, f"❌ 找不到檔案：[{filename}]\n\n🔍 機器人 ({email}) 在您的資料夾中只看到這些檔案：\n{file_names}", None
            
        if file_url == "FOUND_BUT_NOT_SHEET":
            return None, f"❌ 格式錯誤：檔案 [{filename}] 存在，但它是 Excel (.xlsx)。請務必在 Google Drive 將其「另存為 Google 試算表」。", None
            
        if str(file_url).startswith("API_ERROR"):
            return None, f"❌ Google API 連線失敗：{file_url}", None
            
        # 嘗試開啟
        try:
            sh = client.open_by_key(file_id)
        except Exception as open_err:
             return None, f"❌ 無法開啟試算表 (ID: {file_id})。請確認您已將檔案共用給：{email}\n錯誤訊息：{open_err}", None

        # 嘗試讀取分頁
        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            available_sheets = [s.title for s in sh.worksheets()]
            return None, f"❌ 檔案 [{filename}] 中找不到分頁：[{sheet_name}]。\n現有分頁：{available_sheets}", file_url
            
        # 讀取資料
        data = ws.get_all_values()
        
        if len(data) > 1:
            header = data[0]
            rows = data[1:]
            seen = {}
            new_header = []
            for col in header:
                col_str = str(col).strip()
                if col_str in seen:
                    seen[col_str] += 1
                    new_header.append(f"{col_str}_{seen[col_str]}")
                else:
                    seen[col_str] = 0
                    new_header.append(col_str)
            df = pd.DataFrame(rows, columns=new_header)
        else:
            df = pd.DataFrame(data)
            
        return df, "✅ 讀取成功", file_url
        
    except Exception as e:
        return None, f"❌ 未知系統錯誤：{str(e)}", None

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

# --- 4. 介面與權限邏輯 ---

st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()), key="sidebar_store_select")

if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
    staff_options = []
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options, key="sidebar_user_select")

st.title(f"📊 {selected_store} - {selected_user}")

# 權限驗證
def check_store_auth(current_store):
    if current_store == "(ALL) 全店總表":
        if st.session_state.admin_logged_in: return True
        st.info("🛡️ 此區域需要管理員權限")
        admin_input = st.text_input("🔑 請輸入管理員密碼 (輸入後按 Enter)", type="password", key="auth_admin_pass") 
        if admin_input == st.secrets.get("admin_password"):
             st.session_state.admin_logged_in = True
             st.rerun()
        return False

    if st.session_state.authenticated_store == current_store: return True

    st.info(f"🔒 請輸入【{current_store}】的專屬密碼")
    with st.form("store_login"):
        input_pass = st.text_input("密碼 (輸入後按 Enter)", type="password")
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
    st.markdown("### 🏆 全公司業績戰情室")
    
    col_date, col_refresh = st.columns([1, 4])
    view_date = col_date.date_input("選擇檢視月份", date.today(), key="date_input_all")
    
    # 強制讀取：2026_01_(ALL)全店業績日報表 / 分頁：ALL
    if col_refresh.button("🔄 讀取全店總表 (ALL)", type="primary", key="btn_refresh_all"):
        
        target_filename = f"{view_date.year}_{view_date.month:02d}_(ALL)全店業績日報表"
        target_sheet = "ALL"
        
        with st.spinner(f"正在搜尋檔案：[{target_filename}] ..."):
            df_all, msg, link = read_specific_sheet(target_filename, target_sheet)
            
            if df_all is not None and not df_all.empty:
                st.success(f"✅ 成功讀取！")
                if link: st.link_button("🔗 開啟雲端原始檔", link)
                
                # 自動轉換數值
                cols_to_convert = ["毛利", "門號", "綜合指標", "保險營收", "配件營收"]
                for col in cols_to_convert:
                    if col in df_all.columns:
                        df_all[col] = df_all[col].apply(safe_float)
                
                st.divider()
                
                # 計算 KPI
                total_profit = df_all["毛利"].sum() if "毛利" in df_all.columns else 0
                total_cases = df_all["門號"].sum() if "門號" in df_all.columns else 0
                avg_score = df_all["綜合指標"].mean() if "綜合指標" in df_all.columns else 0
                
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("全店總毛利", f"${total_profit:,.0f}")
                kpi2.metric("全店總門號", f"{total_cases:.0f} 件")
                kpi3.metric("平均綜合分", f"{avg_score:.1f} 分")
                kpi4.metric("門市數量", f"{len(df_all)} 間")
                
                st.subheader("📊 績效視覺化")
                chart1, chart2 = st.columns(2)
                
                if "毛利" in df_all.columns and "門市" in df_all.columns:
                    with chart1:
                        st.caption("各店毛利排行")
                        df_plot = df_all[df_all["毛利"] > 0].sort_values("毛利", ascending=False)
                        st.bar_chart(df_plot, x="門市", y="毛利", color="#FF4B4B")
                
                st.subheader("📋 詳細數據")
                column_cfg = {
                    "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                    "毛利": st.column_config.ProgressColumn("毛利", format="$%d", min_value=0, max_value=int(total_profit) if total_profit > 0 else 1000),
                    "綜合指標": st.column_config.NumberColumn("綜合分數", format="%.1f 分"),
                }
                st.dataframe(df_all, column_config=column_cfg, use_container_width=True, hide_index=True)
                
            else:
                st.error(msg) # 這裡會顯示詳細的除錯訊息

elif selected_user == "該店總表":
    st.markdown("### 📥 門市報表檢視中心")
    
    col_d1, col_d2 = st.columns([1, 2])
    view_date = col_d1.date_input("選擇報表月份", date.today(), key="date_input_store")

    # 強制讀取：2026_01_{店名}業績日報表 / 分頁：{店名}
    load_clicked = col_d1.button(f"📂 讀取 {selected_store} 總表", use_container_width=True, key="btn_load_sheet")
    
    if load_clicked:
        target_filename = f"{view_date.year}_{view_date.month:02d}_{selected_store}業績日報表"
        target_sheet = selected_store
        
        with st.spinner(f"正在讀取檔案：[{target_filename}] / 分頁：[{target_sheet}]..."):
            df_store, msg, link = read_specific_sheet(target_filename, target_sheet)
            
            if df_store is not None:
                st.session_state.current_excel_file = {
                    'df': df_store, 
                    'name': target_filename,
                    'link': link,
                    'sheet': target_sheet
                }
                st.success("✅ 讀取成功！")
            else:
                st.error(msg) # 這裡會顯示詳細的除錯訊息
                if link and "FOUND_BUT_NOT_SHEET" not in str(msg): 
                    st.link_button("🔗 前往檔案查看 (可能分頁名稱有誤)", link)
    
    if st.session_state.current_excel_file:
        file_data = st.session_state.current_excel_file
        st.divider()
        st.subheader(f"📄 {file_data['name']} (分頁: {file_data.get('sheet', '未知')})")
        
        if file_data.get('link'):
            st.link_button("🔗 前往 Google 試算表編輯", file_data['link'], type="primary", use_container_width=True)

        st.markdown("---")
        st.dataframe(file_data['df'], use_container_width=True)

else:
    # ----------------------------------------------------
    # 個人填寫模式
    # ----------------------------------------------------
    st.markdown(f"### 📝 {selected_user} - 今日業績回報")

    with st.form("daily_input_full"):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        st.markdown("---")

        st.subheader("💰 財務與門號")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100)
        in_number = c2.number_input("門號 (件)", min_value=0, step=1)
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100)
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100)

        st.subheader("📱 硬體銷售")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1)
        in_vivo = h2.number_input("VIVO 手機 (台)", min_value=0, step=1)
        in_apple = h3.number_input("🍎 蘋果手機 (台)", min_value=0, step=1)
        in_ipad = h4.number_input("🍎 平板/手錶 (台)", min_value=0, step=1)

        st.subheader("🤝 顧客經營")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (件)", min_value=0, step=1)
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

        st.subheader("📡 遠傳專案指標")
        t1, t2, t3, t4 = st.columns(4)
        in_renew = t1.number_input("遠傳續約 (件)", min_value=0, step=1)
        in_gap = t2.number_input("遠傳續約累積 GAP", step=1)
        in_up_rate_raw = t3.number_input("遠傳升續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        in_flat_rate_raw = t4.number_input("遠傳平續率 (%)", min_value=0.0, max_value=100.0, step=0.1)
        
        st.subheader("🏆 綜合評估")
        in_composite = st.number_input("綜合指標分數", min_value=0.0, step=0.1)
        
        check_btn = st.form_submit_button("🔍 預覽 (Step 1)", use_container_width=True)

        if check_btn:
            st.session_state.preview_data = {
                '毛利': in_profit, '門號': in_number, '保險營收': in_insur, '配件營收': in_acc,
                '庫存手機': in_stock, '蘋果手機': in_apple, '蘋果平板+手錶': in_ipad, 'VIVO手機': in_vivo,
                '生活圈': in_life, 'GOOGLE 評論': in_review, '來客數': in_traffic,
                '遠傳續約': in_renew, '遠傳續約累積GAP': in_gap, 
                '遠傳升續率': in_up_rate_raw / 100, '遠傳平續率': in_flat_rate_raw / 100,
                '綜合指標': in_composite, '日期': input_date
            }
            st.rerun()

    if st.session_state.preview_data:
        st.divider()
        st.markdown("### 👀 確認資料")
        df_p = pd.DataFrame([st.session_state.preview_data])
        st.dataframe(df_p.drop(columns=['日期']), hide_index=True)
        
        col_ok, col_no = st.columns([1, 1])
        if col_ok.button("✅ 確認上傳至 Google Sheets (Step 2)", type="primary", use_container_width=True, key="btn_confirm_upload"):
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
                else: st.error(msg)
            except Exception as e: st.error(f"錯誤: {e}")
        
        if col_no.button("❌ 取消", key="btn_cancel_upload"):
            st.session_state.preview_data = None
            st.rerun()
