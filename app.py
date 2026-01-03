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
    st.error("❌ 缺少套件，請在 requirements.txt 加入 `gspread`, `google-auth`, `google-api-python-client`")
    st.stop()

# --- 2. Google Sheets 連線功能 ---

@st.cache_resource
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

def check_connection_debug():
    """(除錯用) 測試連線與權限"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    try:
        client, drive_service, email = get_gspread_client()
        query = f"'{folder_id}' in parents and trashed = false"
        results = drive_service.files().list(q=query, pageSize=5, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        
        st.sidebar.success(f"✅ Drive 連線成功！\n機器人: {email}")
        st.sidebar.info(f"📁 資料夾內前 5 個檔案：")
        for f in files:
            icon = "📊" if "spreadsheet" in f['mimeType'] else "📄"
            st.sidebar.code(f"{icon} {f['name']} ({f['mimeType']})")
            
    except Exception as e:
        st.sidebar.error(f"❌ Drive 連線失敗：{str(e)}")

def get_sheet_file_info(drive_service, filename, folder_id):
    """搜尋檔案並回傳詳細資訊"""
    query = f"name = '{filename}' and trashed = false"
    if folder_id:
        query += f" and '{folder_id}' in parents" 
    
    try:
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink, mimeType)").execute()
        items = results.get('files', [])
        return items
    except Exception as e:
        st.error(f"API 搜尋錯誤: {e}")
        return []

def safe_float(value):
    """強力轉換數值"""
    try:
        if value in [None, "", " ", "-"]: return 0.0
        # 移除常見的干擾字元
        clean_val = str(value).replace(",", "").replace("$", "").replace("%", "").replace(" ", "").strip()
        if not clean_val: return 0.0
        return float(clean_val)
    except ValueError:
        return 0.0

def read_specific_sheet_robust(filename, sheet_name):
    """(強健版) 讀取試算表，包含詳細錯誤診斷"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, email = get_gspread_client()
    
    files_found = get_sheet_file_info(drive_service, filename, folder_id)
    
    if not files_found:
        return None, f"❌ 找不到檔案：[{filename}]\n請確認檔名完全一致，且機器人 ({email}) 有權限讀取該資料夾。", None
    
    target_file = None
    excel_file = None
    
    for f in files_found:
        if "application/vnd.google-apps.spreadsheet" in f['mimeType']:
            target_file = f
            break
        elif "spreadsheetml.sheet" in f['mimeType']: 
            excel_file = f
            
    if not target_file:
        if excel_file:
            return None, f"⚠️ 找到檔案 [{filename}]，但它是 Excel (.xlsx) 格式。\n請在 Google Drive 將其「另存為 Google 試算表」。", None
        else:
            return None, f"❌ 找到同名檔案，但格式不支援。", None
            
    file_id = target_file['id']
    file_link = target_file['webViewLink']
    
    try:
        sh = client.open_by_key(file_id)
    except Exception as open_err:
        return None, f"❌ 無法開啟試算表 (ID: {file_id})。\n錯誤：{open_err}", file_link

    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        available = [s.title for s in sh.worksheets()]
        return None, f"❌ 檔案中找不到分頁：[{sheet_name}]。\n現有分頁：{available}", file_link
        
    try:
        data = ws.get_all_values()
        if len(data) > 1:
            header = data[0]
            rows = data[1:]
            seen = {}
            new_header = []
            for col in header:
                # 清除標題前後空白
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
            
        return df, "✅ 讀取成功", file_link
        
    except Exception as e:
        return None, f"❌ 讀取數據時發生錯誤：{e}", file_link

def update_google_sheet_robust(store, staff, date_obj, data_dict):
    """(強健版) 寫入數據"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    
    client, drive_service, email = get_gspread_client()
    files = get_sheet_file_info(drive_service, filename, folder_id)
    
    target_file = next((f for f in files if "google-apps.spreadsheet" in f['mimeType']), None)
    
    if not target_file:
        return f"❌ 找不到 Google 試算表：[{filename}]"
        
    try:
        sh = client.open_by_key(target_file['id'])
        ws = sh.worksheet(staff)
        
        target_row = 15 + (date_obj.day - 1)
        
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8, 'VIVO手機': 9,
            '生活圈': 10, 'GOOGLE 評論': 11, '來客數': 12,
            '遠傳續約': 13, '遠傳續約累積GAP': 14, 
            '遠傳升續率': 15, '遠傳平續率': 16, '綜合指標': 17
        }
        overwrite = ['遠傳續約累積GAP', '遠傳升續率', '遠傳平續率', '綜合指標']
        
        updates = []
        for field, new_val in data_dict.items():
            if field in col_map and new_val is not None:
                col_idx = col_map[field]
                if field in overwrite:
                    updates.append({'range': gspread.utils.rowcol_to_a1(target_row, col_idx), 'values': [[new_val]]})
                else:
                    old_val = ws.cell(target_row, col_idx).value
                    final_val = safe_float(old_val) + new_val
                    updates.append({'range': gspread.utils.rowcol_to_a1(target_row, col_idx), 'values': [[final_val]]})

        if updates: ws.batch_update(updates)
        return f"✅ 資料已成功寫入：{filename}"
        
    except gspread.WorksheetNotFound:
        return f"❌ 找不到人員分頁：[{staff}]"
    except Exception as e:
        return f"❌ 寫入錯誤：{str(e)}"

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

if st.sidebar.button("🛠️ 測試連線 (除錯用)"):
    check_connection_debug()

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
    
    if col_refresh.button("🔄 讀取全店總表 (ALL)", type="primary", key="btn_refresh_all"):
        
        target_filename = f"{view_date.year}_{view_date.month:02d}_(ALL)全店業績日報表"
        target_sheet = "ALL"
        
        with st.spinner(f"正在讀取檔案：[{target_filename}] ..."):
            df_all, msg, link = read_specific_sheet_robust(target_filename, target_sheet)
            
            if df_all is not None and not df_all.empty:
                st.success(f"✅ 成功讀取！")
                if link: st.link_button("🔗 開啟雲端原始檔", link)
                
                # --- 資料清洗與轉換 ---
                # 1. 移除可能的空行或「總計」行，避免計算店數錯誤
                # 假設第一欄是「門市」或「店名」，若為空則排除
                if "門市" in df_all.columns:
                    df_all = df_all[df_all["門市"].str.strip() != ""]
                    # 排除名稱含有 "總計", "Total" 的行
                    df_all = df_all[~df_all["門市"].str.contains("總計|Total|total", na=False)]

                # 2. 定義需要轉換的欄位
                target_metrics = [
                    "毛利", "門號", "保險營收", "配件營收", 
                    "庫存手機", "蘋果手機", "蘋果平板+手錶", "VIVO手機",
                    "生活圈", "GOOGLE 評論", "來客數", 
                    "遠傳續約累積GAP", "遠傳升續率", "遠傳平續率"
                ]
                
                # 3. 執行轉換 (確保欄位存在才轉)
                for col in target_metrics:
                    if col in df_all.columns:
                        df_all[col] = df_all[col].apply(safe_float)
                
                st.divider()
                
                # --- 4. 儀表板呈現 (Dashboard Layout) ---
                
                # [區塊 1] 財務與核心 (Profit & Core)
                st.subheader("💰 財務與核心指標")
                c1, c2, c3, c4 = st.columns(4)
                
                total_profit = df_all["毛利"].sum() if "毛利" in df_all.columns else 0
                total_cases = df_all["門號"].sum() if "門號" in df_all.columns else 0
                total_insur = df_all["保險營收"].sum() if "保險營收" in df_all.columns else 0
                store_count = len(df_all)
                
                c1.metric("全店總毛利", f"${total_profit:,.0f}")
                c2.metric("全店總門號", f"{total_cases:.0f} 件")
                c3.metric("總保險營收", f"${total_insur:,.0f}")
                c4.metric("營業門市數", f"{store_count} 間")
                
                st.markdown("---")

                # [區塊 2] 硬體銷售 (Hardware)
                st.subheader("📱 硬體銷售重點")
                h1, h2, h3, h4 = st.columns(4)
                
                t_stock = df_all["庫存手機"].sum() if "庫存手機" in df_all.columns else 0
                t_apple = df_all["蘋果手機"].sum() if "蘋果手機" in df_all.columns else 0
                t_ipad = df_all["蘋果平板+手錶"].sum() if "蘋果平板+手錶" in df_all.columns else 0
                t_vivo = df_all["VIVO手機"].sum() if "VIVO手機" in df_all.columns else 0
                
                h1.metric("庫存手機", f"{t_stock:.0f} 台")
                h2.metric("蘋果手機", f"{t_apple:.0f} 台")
                h3.metric("蘋果平板+手錶", f"{t_ipad:.0f} 台")
                h4.metric("VIVO手機", f"{t_vivo:.0f} 台")
                
                st.markdown("---")

                # [區塊 3] 顧客經營與專案 (Service & KPI)
                st.subheader("🤝 顧客經營 & 遠傳指標")
                s1, s2, s3, s4, s5 = st.columns(5)
                
                t_life = df_all["生活圈"].sum() if "生活圈" in df_all.columns else 0
                t_review = df_all["GOOGLE 評論"].sum() if "GOOGLE 評論" in df_all.columns else 0
                t_traffic = df_all["來客數"].sum() if "來客數" in df_all.columns else 0
                t_gap = df_all["遠傳續約累積GAP"].sum() if "遠傳續約累積GAP" in df_all.columns else 0
                
                # 比率類通常顯示平均值 (或加權平均，這裡暫用簡單平均)
                avg_up_rate = df_all["遠傳升續率"].mean() if "遠傳升續率" in df_all.columns else 0
                avg_flat_rate = df_all["遠傳平續率"].mean() if "遠傳平續率" in df_all.columns else 0
                
                s1.metric("生活圈", f"{t_life:.0f}")
                s2.metric("Google 評論", f"{t_review:.0f}")
                s3.metric("來客數", f"{t_traffic:.0f}")
                s4.metric("續約 GAP", f"{t_gap:.0f}")
                s5.metric("平均升續率", f"{avg_up_rate*100:.1f}%") # 假設原始資料為小數點 (0.8)

                st.markdown("---")

                # [區塊 4] 排行圖表
                st.subheader("📊 門市毛利排行")
                if "毛利" in df_all.columns and "門市" in df_all.columns:
                    df_plot = df_all[df_all["毛利"] > 0].sort_values("毛利", ascending=False)
                    st.bar_chart(df_plot, x="門市", y="毛利", color="#FF4B4B")
                
                # [區塊 5] 詳細數據表
                st.subheader("📋 詳細數據列表")
                
                column_cfg = {
                    "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                    "毛利": st.column_config.ProgressColumn("毛利", format="$%d", min_value=0, max_value=int(total_profit) if total_profit > 0 else 1000),
                    "遠傳升續率": st.column_config.NumberColumn("升續率", format="%.1f%%"), # 若原始資料是 80 代表 80%，請改 format="%d%%"
                    "遠傳平續率": st.column_config.NumberColumn("平續率", format="%.1f%%"),
                }
                
                st.dataframe(df_all, column_config=column_cfg, use_container_width=True, hide_index=True)
                
            else:
                st.error(msg) 
                if link: st.link_button("🔗 查看檔案", link)

elif selected_user == "該店總表":
    st.markdown("### 📥 門市報表檢視中心")
    
    col_d1, col_d2 = st.columns([1, 2])
    view_date = col_d1.date_input("選擇報表月份", date.today(), key="date_input_store")

    load_clicked = col_d1.button(f"📂 讀取 {selected_store} 總表", use_container_width=True, key="btn_load_sheet")
    
    if load_clicked:
        target_filename = f"{view_date.year}_{view_date.month:02d}_{selected_store}業績日報表"
        target_sheet = selected_store
        
        with st.spinner(f"正在讀取檔案：[{target_filename}] / 分頁：[{target_sheet}]..."):
            df_store, msg, link = read_specific_sheet_robust(target_filename, target_sheet)
            
            if df_store is not None:
                st.session_state.current_excel_file = {
                    'df': df_store, 
                    'name': target_filename,
                    'link': link,
                    'sheet': target_sheet
                }
                st.success("✅ 讀取成功！")
            else:
                st.error(msg)
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
                msg = update_google_sheet_robust(selected_store, selected_user, t_date, data_copy)
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
