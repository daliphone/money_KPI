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

# --- 2. Google Sheets 與 Drive 連線功能 ---

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

def get_working_folder_id(drive_service, root_folder_id, date_obj):
    """
    (智慧搜尋) 嘗試尋找月份資料夾，若找不到則回退至根目錄
    回傳: (folder_id, is_subfolder_found, message)
    """
    folder_name = date_obj.strftime("%Y%m") # 例如 202601
    
    # 嘗試搜尋子資料夾
    query = f"name = '{folder_name}' and '{root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    
    try:
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        
        if files:
            # 找到月份資料夾，使用它
            return files[0]['id'], True, f"📂 已進入 [{folder_name}] 資料夾"
        else:
            # 沒找到，回退使用根目錄 (Root)
            return root_folder_id, False, f"⚠️ 未發現 [{folder_name}] 資料夾，改為搜尋根目錄"
            
    except Exception as e:
        # 發生錯誤，只好回傳 None
        return None, False, f"搜尋錯誤: {str(e)}"

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
    try:
        if value in [None, "", " ", "-"]: return 0.0
        clean_val = str(value).replace(",", "").replace("$", "").replace("%", "").replace(" ", "").strip()
        if not clean_val: return 0.0
        return float(clean_val)
    except ValueError:
        return 0.0

# --- 讀取與彙整邏輯 (v12.0) ---

def scan_and_aggregate_stores(date_obj):
    """
    (ALL) 掃描資料夾內所有 'xx店業績日報表'
    """
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, email = get_gspread_client()
    
    # 1. 取得工作資料夾 (月份資料夾 or 根目錄)
    work_folder_id, is_sub, status_msg = get_working_folder_id(drive_service, root_id, date_obj)
    
    if not work_folder_id:
        return None, f"❌ 資料夾錯誤: {status_msg}"
    
    # 顯示提示訊息 (如果是 fallback)
    if not is_sub:
        st.toast(status_msg, icon="ℹ️")

    # 2. 列出資料夾內所有檔案
    try:
        query = f"'{work_folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
        all_files = results.get('files', [])
    except Exception as e:
        return None, f"❌ 無法讀取資料夾內容: {e}"

    # 3. 過濾出符合格式的檔案: YYYY_MM_xx店業績日報表
    target_pattern = f"{date_obj.strftime('%Y_%m')}_.+店業績日報表"
    valid_store_files = []
    
    for f in all_files:
        if "店業績日報表" in f['name'] and "(ALL)" not in f['name']:
            if f['name'].startswith(date_obj.strftime('%Y_%m')):
                valid_store_files.append(f)

    if not valid_store_files:
        return None, f"⚠️ 在資料夾中找不到符合 [{target_pattern}] 的檔案。\n(目前搜尋位置: {'月份資料夾' if is_sub else '根目錄'})"

    # 4. 開始逐一讀取數據
    aggregated_data = []
    prog_bar = st.progress(0, text="開始掃描門市...")
    total = len(valid_store_files)
    
    for idx, f in enumerate(valid_store_files):
        store_name_raw = f['name'].split('_')[-1].replace('業績日報表', '') 
        prog_bar.progress(int((idx+1)/total * 100), text=f"正在讀取：{store_name_raw}...")
        
        store_stat = {
            "門市": store_name_raw,
            "連結": f['webViewLink'],
            "檔案ID": f['id'],
            "毛利": 0, "門號": 0, "保險營收": 0, "配件營收": 0,
            "庫存手機": 0, "蘋果手機": 0, "蘋果平板+手錶": 0, "VIVO手機": 0,
            "生活圈": 0, "GOOGLE 評論": 0, "來客數": 0,
            "遠傳續約累積GAP": 0, "遠傳升續率": 0, "遠傳平續率": 0
        }
        
        try:
            sh = client.open_by_key(f['id'])
            target_ws = None
            try:
                target_ws = sh.worksheet(store_name_raw)
            except:
                try:
                    target_ws = sh.worksheet("總表")
                except: pass
            
            if target_ws:
                data_range = target_ws.get("B15:S45")
                for row in data_range:
                    if len(row) > 0:
                        store_stat["毛利"] += safe_float(row[0]) if len(row) > 0 else 0
                        store_stat["門號"] += safe_float(row[1]) if len(row) > 1 else 0
                        store_stat["保險營收"] += safe_float(row[2]) if len(row) > 2 else 0
                        store_stat["配件營收"] += safe_float(row[3]) if len(row) > 3 else 0
                        store_stat["庫存手機"] += safe_float(row[4]) if len(row) > 4 else 0
                        store_stat["蘋果手機"] += safe_float(row[5]) if len(row) > 5 else 0
                        store_stat["蘋果平板+手錶"] += safe_float(row[6]) if len(row) > 6 else 0
                        store_stat["VIVO手機"] += safe_float(row[7]) if len(row) > 7 else 0
                        store_stat["生活圈"] += safe_float(row[8]) if len(row) > 8 else 0
                        store_stat["GOOGLE 評論"] += safe_float(row[9]) if len(row) > 9 else 0
                        store_stat["來客數"] += safe_float(row[10]) if len(row) > 10 else 0
                        
                        val_gap = safe_float(row[12]) if len(row) > 12 else 0
                        val_up = safe_float(row[13]) if len(row) > 13 else 0
                        val_flat = safe_float(row[14]) if len(row) > 14 else 0
                        
                        if val_gap != 0: store_stat["遠傳續約累積GAP"] = val_gap
                        if val_up != 0: store_stat["遠傳升續率"] = val_up
                        if val_flat != 0: store_stat["遠傳平續率"] = val_flat

        except Exception as e:
            print(f"Error reading {store_name_raw}: {e}")
            store_stat["門市"] = f"{store_name_raw} (失敗)"
            
        aggregated_data.append(store_stat)
        
    prog_bar.empty()
    return pd.DataFrame(aggregated_data), f"✅ 成功掃描 {len(valid_store_files)} 間分店"

def update_google_sheet_robust(store, staff, date_obj, data_dict):
    """(強健版) 寫入數據 - 支援月份資料夾與根目錄 fallback"""
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, email = get_gspread_client()
    
    # 1. 取得工作資料夾
    work_folder_id, is_sub, status_msg = get_working_folder_id(drive_service, root_id, date_obj)
    
    if not work_folder_id:
        return f"❌ {status_msg}"
    
    # 2. 在該資料夾內搜尋檔案
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    files = get_sheet_file_info(drive_service, filename, work_folder_id)
    
    target_file = next((f for f in files if "google-apps.spreadsheet" in f['mimeType']), None)
    
    if not target_file:
        return f"❌ 找不到試算表：[{filename}] (位置: {'月份資料夾' if is_sub else '根目錄'})"
        
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

def read_sheet_robust_v12(store, date_obj):
    """v12 讀取單店報表 - 支援 fallback"""
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, _ = get_gspread_client()
    
    work_folder_id, _, _ = get_working_folder_id(drive_service, root_id, date_obj)
    if not work_folder_id: return None, "資料夾錯誤", None
    
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    files = get_sheet_file_info(drive_service, filename, work_folder_id)
    target_file = next((f for f in files if "google-apps.spreadsheet" in f['mimeType']), None)
    
    if not target_file: return None, f"找不到檔案：{filename}", None
    
    try:
        sh = client.open_by_key(target_file['id'])
        # 優先找店名分頁，次找總表
        target_ws = None
        try: target_ws = sh.worksheet(store)
        except:
            try: target_ws = sh.worksheet("總表")
            except: pass
            
        if target_ws:
            data = target_ws.get_all_values()
            if len(data) > 1:
                df = pd.DataFrame(data[1:], columns=data[0])
            else:
                df = pd.DataFrame(data)
            return df, filename, target_file['webViewLink']
        else:
            return None, f"找不到 [{store}] 或 [總表] 分頁", target_file['webViewLink']
            
    except Exception as e:
        return None, str(e), None

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

# 移除 Debug 按鈕，介面更乾淨
# if st.sidebar.button("🛠️ 測試連線"): ...

selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()), key="sidebar_store_select")

if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
    staff_options = []
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options, key="sidebar_user_select")

# --- 系統資訊 Footer ---
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 系統資訊", expanded=True):
    st.write("**馬尼門市業績戰情表**")
    st.write("版本：v12.0")
    st.caption("© 2025 Money KPI")

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
    st.info("此功能會自動搜尋該月份所有分店報表並彙總 (支援月份資料夾與根目錄)。")
    
    col_date, col_refresh = st.columns([1, 4])
    view_date = col_date.date_input("選擇檢視月份", date.today(), key="date_input_all")
    
    if col_refresh.button("🔄 掃描並彙整全店數據", type="primary", key="btn_refresh_all"):
        
        with st.spinner(f"正在掃描 {view_date.strftime('%Y%m')} 資料..."):
            df_all, msg = scan_and_aggregate_stores(view_date)
            
            if df_all is not None and not df_all.empty:
                st.success(msg)
                st.divider()
                
                # 計算 KPI
                total_profit = df_all["毛利"].sum()
                total_cases = df_all["門號"].sum()
                total_insur = df_all["保險營收"].sum()
                store_count = len(df_all)
                
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("全店總毛利", f"${total_profit:,.0f}")
                kpi2.metric("全店總門號", f"{total_cases:.0f} 件")
                kpi3.metric("總保險營收", f"${total_insur:,.0f}")
                kpi4.metric("營業門市數", f"{store_count} 間")
                
                st.markdown("---")

                # 硬體銷售
                st.subheader("📱 硬體銷售")
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("庫存手機", f"{df_all['庫存手機'].sum():.0f}")
                h2.metric("蘋果手機", f"{df_all['蘋果手機'].sum():.0f}")
                h3.metric("蘋果平板+手錶", f"{df_all['蘋果平板+手錶'].sum():.0f}")
                h4.metric("VIVO手機", f"{df_all['VIVO手機'].sum():.0f}")
                
                st.markdown("---")

                # 顧客與專案
                st.subheader("🤝 顧客與遠傳指標")
                s1, s2, s3, s4, s5 = st.columns(5)
                s1.metric("生活圈", f"{df_all['生活圈'].sum():.0f}")
                s2.metric("Google 評論", f"{df_all['GOOGLE 評論'].sum():.0f}")
                s3.metric("來客數", f"{df_all['來客數'].sum():.0f}")
                s4.metric("續約 GAP", f"{df_all['遠傳續約累積GAP'].sum():.0f}")
                
                avg_up = df_all[df_all["遠傳升續率"] > 0]["遠傳升續率"].mean()
                if pd.isna(avg_up): avg_up = 0
                s5.metric("平均升續率", f"{avg_up*100:.1f}%")

                st.markdown("---")

                # 視覺化與表格
                st.subheader("📊 門市排行與數據")
                if store_count > 0:
                    c_chart1, c_chart2 = st.columns(2)
                    with c_chart1:
                        st.caption("毛利排行")
                        st.bar_chart(df_all.set_index("門市")["毛利"].sort_values(ascending=False), color="#FF4B4B")
                    with c_chart2:
                        st.caption("門號件數排行")
                        st.bar_chart(df_all.set_index("門市")["門號"].sort_values(ascending=False), color="#3366CC")
                
                column_cfg = {
                    "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                    "毛利": st.column_config.ProgressColumn("毛利", format="$%d", min_value=0, max_value=int(total_profit/2) if total_profit > 0 else 1000),
                    "遠傳升續率": st.column_config.NumberColumn("升續率", format="%.1f%%"),
                    "遠傳平續率": st.column_config.NumberColumn("平續率", format="%.1f%%"),
                    "連結": st.column_config.LinkColumn("檔案連結")
                }
                st.dataframe(df_all, column_config=column_cfg, use_container_width=True, hide_index=True)
                
            else:
                st.error(msg)

elif selected_user == "該店總表":
    st.markdown("### 📥 門市報表檢視中心")
    
    col_d1, col_d2 = st.columns([1, 2])
    view_date = col_d1.date_input("選擇報表月份", date.today(), key="date_input_store")

    load_clicked = col_d1.button(f"📂 讀取 {selected_store} 總表", use_container_width=True, key="btn_load_sheet")
    
    if load_clicked:
        with st.spinner("搜尋資料夾與檔案..."):
            df, fname, link = read_sheet_robust_v12(selected_store, view_date)
            
            if df is not None:
                st.session_state.current_excel_file = {
                    'df': df, 'name': fname, 'link': link
                }
                st.success("✅ 讀取成功！")
            else:
                st.error(fname) # 這裡是錯誤訊息
    
    if st.session_state.current_excel_file:
        file_data = st.session_state.current_excel_file
        st.divider()
        st.subheader(f"📄 {file_data['name']}")
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
                my_bar.progress(30, text="搜尋資料夾...")
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
