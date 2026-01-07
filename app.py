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

# --- 2. Google Sheets 連線與工具 ---

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return client, drive_service, creds.service_account_email

def check_connection_status():
    try:
        _, _, email = get_gspread_client()
        return True, email
    except:
        return False, None

def get_working_folder_id(drive_service, root_folder_id, date_obj):
    """廣域搜尋月份資料夾"""
    folder_name = date_obj.strftime("%Y%m")
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if files: return files[0]['id']
        else: return root_folder_id 
    except: return root_folder_id

def get_sheet_file_info(drive_service, filename, folder_id):
    query = f"name = '{filename}' and trashed = false"
    if folder_id: query += f" and '{folder_id}' in parents"
    try:
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink, mimeType)").execute()
        return results.get('files', [])
    except: return []

def safe_float(value):
    try:
        if value in [None, "", " ", "-"]: return 0.0
        clean_val = str(value).replace(",", "").replace("$", "").replace("%", "").replace(" ", "").strip()
        if not clean_val: return 0.0
        return float(clean_val)
    except ValueError: return 0.0

def make_columns_unique(columns):
    seen = {}
    new_columns = []
    for i, col in enumerate(columns):
        col_name = str(col).strip() if str(col).strip() else f"Column_{i}"
        if col_name in seen:
            seen[col_name] += 1
            new_columns.append(f"{col_name}_{seen[col_name]}")
        else:
            seen[col_name] = 0
            new_columns.append(col_name)
    return new_columns

# --- 核心邏輯：動態讀取 Excel 分頁 ---

@st.cache_data(ttl=60)
def fetch_dynamic_staff_list(store_name, date_obj):
    if store_name == "(ALL) 全店總表": return []
    
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, _ = get_gspread_client()
    
    folder_id = get_working_folder_id(drive_service, root_id, date_obj)
    
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store_name}業績日報表"
    files = get_sheet_file_info(drive_service, filename, folder_id)
    target_file = next((f for f in files if "google-apps.spreadsheet" in f['mimeType']), None)
    
    if not target_file: return []
    
    try:
        sh = client.open_by_key(target_file['id'])
        all_sheets = [ws.title for ws in sh.worksheets()]
        exclude_list = ["總表", "總計", "Total", "TOTAL", "Log", "設定", "Config", store_name]
        staff_list = [s for s in all_sheets if s not in exclude_list]
        return staff_list
    except: return []

# --- 讀取與彙整功能 (v15.5 修正欄位) ---

def scan_and_aggregate_stores(date_obj):
    """(ALL) 總表彙整"""
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, _ = get_gspread_client()
    
    folder_id = get_working_folder_id(drive_service, root_id, date_obj)
    
    try:
        query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
        all_files = results.get('files', [])
    except Exception as e: return None, f"無法讀取資料夾: {e}"

    target_pattern = f"{date_obj.strftime('%Y_%m')}_.+店業績日報表"
    valid_files = [f for f in all_files if "店業績日報表" in f['name'] and "(ALL)" not in f['name'] and f['name'].startswith(date_obj.strftime('%Y_%m'))]

    if not valid_files: return None, f"找不到符合 {target_pattern} 的檔案"

    aggregated_data = []
    prog_bar = st.progress(0, text="掃描中...")
    
    for idx, f in enumerate(valid_files):
        store_name = f['name'].split('_')[-1].replace('業績日報表', '')
        prog_bar.progress(int((idx+1)/len(valid_files)*100), text=f"讀取：{store_name}")
        
        stat = {
            "門市": store_name, "連結": f['webViewLink'],
            "毛利": 0, "門號": 0, "保險營收": 0, "配件營收": 0,
            "庫存手機": 0, "蘋果手機": 0, "蘋果平板+手錶": 0, 
            # [v15.5 New Items]
            "華為穿戴": 0, "橙艾玻璃貼": 0, "VIVO銷售目標": 0, "GPLUS吸塵器": 0,
            # [Shifted Items] - VIVO手機已移除
            "生活圈": 0, "GOOGLE 評論": 0, "來客數": 0,
            "遠傳續約": 0, "遠傳續約累積GAP": 0, "遠傳升續率": 0, "遠傳平續率": 0
        }
        
        try:
            sh = client.open_by_key(f['id'])
            ws = None
            try: ws = sh.worksheet(store_name)
            except: 
                try: ws = sh.worksheet("總表")
                except: pass
            
            if ws:
                # 讀取範圍至 U (21欄)
                data = ws.get("B15:U45")
                for row in data:
                    if len(row) > 0:
                        # 0~6 固定
                        stat["毛利"] += safe_float(row[0]) if len(row)>0 else 0
                        stat["門號"] += safe_float(row[1]) if len(row)>1 else 0
                        stat["保險營收"] += safe_float(row[2]) if len(row)>2 else 0
                        stat["配件營收"] += safe_float(row[3]) if len(row)>3 else 0
                        stat["庫存手機"] += safe_float(row[4]) if len(row)>4 else 0
                        stat["蘋果手機"] += safe_float(row[5]) if len(row)>5 else 0
                        stat["蘋果平板+手錶"] += safe_float(row[6]) if len(row)>6 else 0
                        
                        # [v15.5 Mappings]
                        # I (7) -> 華為穿戴
                        stat["華為穿戴"] += safe_float(row[7]) if len(row)>7 else 0
                        # J (8) -> 橙艾玻璃貼
                        stat["橙艾玻璃貼"] += safe_float(row[8]) if len(row)>8 else 0
                        # K (9) -> VIVO銷售目標
                        stat["VIVO銷售目標"] += safe_float(row[9]) if len(row)>9 else 0
                        # L (10) -> GPLUS吸塵器
                        stat["GPLUS吸塵器"] += safe_float(row[10]) if len(row)>10 else 0
                        
                        # [Shifted] M (11) 開始
                        stat["生活圈"] += safe_float(row[11]) if len(row)>11 else 0
                        stat["GOOGLE 評論"] += safe_float(row[12]) if len(row)>12 else 0
                        stat["來客數"] += safe_float(row[13]) if len(row)>13 else 0
                        
                        stat["遠傳續約"] += safe_float(row[14]) if len(row)>14 else 0
                        
                        v_gap = safe_float(row[15]) if len(row)>15 else 0
                        v_up = safe_float(row[16]) if len(row)>16 else 0
                        v_flat = safe_float(row[17]) if len(row)>17 else 0
                        
                        if v_gap != 0: stat["遠傳續約累積GAP"] = v_gap
                        if v_up != 0: stat["遠傳升續率"] = v_up
                        if v_flat != 0: stat["遠傳平續率"] = v_flat

        except Exception as e: print(e)
        aggregated_data.append(stat)
    
    prog_bar.empty()
    return pd.DataFrame(aggregated_data), f"✅ 掃描完成：{len(valid_files)} 間門市"

def update_google_sheet_robust(store, staff, date_obj, data_dict):
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, _ = get_gspread_client()
    folder_id = get_working_folder_id(drive_service, root_id, date_obj)
    
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    files = get_sheet_file_info(drive_service, filename, folder_id)
    target_file = next((f for f in files if "google-apps.spreadsheet" in f['mimeType']), None)
    
    if not target_file: return f"❌ 找不到檔案：{filename}"
    
    try:
        sh = client.open_by_key(target_file['id'])
        ws = sh.worksheet(staff)
        target_row = 15 + (date_obj.day - 1)
        
        # [v15.5 Col Map - VIVO手機 Removed]
        col_map = {
            '毛利': 2, '門號': 3, '保險營收': 4, '配件營收': 5,
            '庫存手機': 6, '蘋果手機': 7, '蘋果平板+手錶': 8,
            # New Items (I, J, K, L)
            '華為穿戴': 9,
            '橙艾玻璃貼': 10,
            'VIVO銷售目標': 11,
            'GPLUS吸塵器': 12,
            # Shifted Items (M...)
            '生活圈': 13,
            'GOOGLE 評論': 14,
            '來客數': 15,
            '遠傳續約': 16,
            '遠傳續約累積GAP': 17, '遠傳升續率': 18, '遠傳平續率': 19, '綜合指標': 20
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
        return f"✅ 寫入成功：{filename}"
    except Exception as e: return f"❌ 寫入錯誤：{e}"

def read_sheet_robust_v13(store, date_obj):
    root_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service, _ = get_gspread_client()
    folder_id = get_working_folder_id(drive_service, root_id, date_obj)
    
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    files = get_sheet_file_info(drive_service, filename, folder_id)
    target_file = next((f for f in files if "google-apps.spreadsheet" in f['mimeType']), None)
    
    if not target_file: return None, f"找不到檔案：{filename}", None
    
    try:
        sh = client.open_by_key(target_file['id'])
        target_ws = None
        try: target_ws = sh.worksheet(store)
        except:
            try: target_ws = sh.worksheet("總表")
            except: pass
            
        if target_ws:
            data = target_ws.get_all_values()
            if len(data) > 1:
                clean_headers = make_columns_unique(data[0])
                df = pd.DataFrame(data[1:], columns=clean_headers)
            else: df = pd.DataFrame(data)
            return df, filename, target_file['webViewLink']
        else: return None, "找不到店名或總表分頁", target_file['webViewLink']
    except Exception as e: return None, str(e), None

# --- 3. 組織定義 ---
STORE_NAMES = [
    "(ALL) 全店總表",
    "文賢店", "東門店", "永康店", "歸仁店", "安中店",
    "小西門店", "鹽行店", "五甲店", "鳳山店"
]

# --- 4. 介面邏輯 ---

st.sidebar.title("🏢 門市導航")

# 連線狀態
conn_ok, _ = check_connection_status()
if conn_ok: st.sidebar.success("🟢 系統連線正常", icon="📶")
else: st.sidebar.error("🔴 系統連線失敗")

# 1. 選擇門市
selected_store = st.sidebar.selectbox("請選擇門市", STORE_NAMES, key="sidebar_store_select")

# 2. 選擇月份
if selected_store == "(ALL) 全店總表":
    if 'global_view_date' not in st.session_state:
        st.session_state.global_view_date = date.today()
    selected_user = "全店總覽"
    staff_options = []
else:
    view_date = st.sidebar.date_input("設定工作月份", date.today(), key="sidebar_date_picker")
    with st.spinner("讀取人員名單..."):
        dynamic_staff = fetch_dynamic_staff_list(selected_store, view_date)
    
    if dynamic_staff:
        staff_options = ["該店總表"] + dynamic_staff
    else:
        staff_options = ["該店總表"]
        st.sidebar.caption("⚠️ 尚未建立該月檔案或讀取失敗")
        
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options, key="sidebar_user_select")

# Footer
st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 系統資訊", expanded=False):
    st.markdown("""
    **馬尼門市業績戰情表**
    © 2025 Money KPI
    
    **v15.5 更新說明：**
    * 欄位更新：移除「VIVO手機」。
    * 新增項目：華為穿戴、橙艾玻璃貼、VIVO目標、GPLUS吸塵器 (I, J, K, L 欄)。
    """)

st.title(f"📊 {selected_store} - {selected_user}")

# 權限驗證
def check_store_auth(current_store):
    if current_store == "(ALL) 全店總表":
        if st.session_state.admin_logged_in: return True
        st.info("🛡️ 此區域需要管理員權限")
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password") 
        if admin_input == st.secrets.get("admin_password"):
             st.session_state.admin_logged_in = True
             st.rerun()
        return False
    
    if st.session_state.authenticated_store == current_store: return True
    
    st.info(f"🔒 請輸入【{current_store}】的專屬密碼")
    with st.form("store_login"):
        input_pass = st.text_input("密碼", type="password")
        if st.form_submit_button("登入"):
            correct_pass = st.secrets["store_passwords"].get(current_store)
            if input_pass == correct_pass:
                st.session_state.authenticated_store = current_store
                st.rerun()
            else:
                st.error("❌ 密碼錯誤")
    return False

if not check_store_auth(selected_store): st.stop()

# =========================================================
# 主畫面邏輯
# =========================================================

if selected_store == "(ALL) 全店總表":
    st.markdown("### 🏆 全公司業績戰情室")
    view_date = st.date_input("選擇檢視月份", date.today(), key="main_date_input")
    
    if st.button("🔄 掃描並彙整全店數據", type="primary"):
        with st.spinner(f"正在掃描 {view_date.strftime('%Y%m')} 資料..."):
            df_all, msg = scan_and_aggregate_stores(view_date)
            if df_all is not None and not df_all.empty:
                st.success(msg)
                st.divider()
                
                # 1. 毛利與門號
                st.subheader("💰 毛利與門號")
                tp = df_all["毛利"].sum(); tc = df_all["門號"].sum(); ti = df_all["保險營收"].sum()
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("全店總毛利", f"${tp:,.0f}")
                k2.metric("全店總門號", f"{tc:.0f} 件")
                k3.metric("總保險營收", f"${ti:,.0f}")
                k4.metric("營業門市數", f"{len(df_all)} 間")
                
                st.markdown("---")
                
                # 2. 硬體銷售 (Updated)
                st.subheader("📱 硬體銷售")
                h1, h2, h3, h4 = st.columns(4)
                h1.metric("庫存手機", f"{df_all['庫存手機'].sum():.0f} 台")
                h2.metric("蘋果手機", f"{df_all['蘋果手機'].sum():.0f} 台")
                h3.metric("蘋果平板/手錶", f"{df_all['蘋果平板+手錶'].sum():.0f} 台")
                h4.metric("GPLUS吸塵器", f"{df_all['GPLUS吸塵器'].sum():.0f} 台") # Replaces VIVO Phone
                
                st.markdown("---")
                
                # 3. 重點推廣 (New)
                st.subheader("🔥 重點推廣與目標")
                p1, p2, p3 = st.columns(3)
                p1.metric("華為穿戴", f"{df_all['華為穿戴'].sum():.0f} 台")
                p2.metric("橙艾玻璃貼", f"{df_all['橙艾玻璃貼'].sum():.0f} 張")
                p3.metric("VIVO銷售目標", f"{df_all['VIVO銷售目標'].sum():.0f} 台")

                st.markdown("---")
                
                # 4. 顧客經營
                st.subheader("🤝 顧客經營")
                s1, s2, s3 = st.columns(3)
                s1.metric("生活圈", f"{df_all['生活圈'].sum():.0f} 人")
                s2.metric("Google 評論", f"{df_all['GOOGLE 評論'].sum():.0f} 則")
                s3.metric("來客數", f"{df_all['來客數'].sum():.0f} 人")
                
                st.markdown("---")
                
                # 5. 遠傳專案
                st.subheader("📡 遠傳專案指標")
                f1, f2, f3, f4 = st.columns(4)
                f1.metric("遠傳續約", f"{df_all['遠傳續約'].sum():.0f} 件")
                f2.metric("續約 GAP", f"{df_all['遠傳續約累積GAP'].sum():.0f}")
                
                avg_up = df_all[df_all["遠傳升續率"]>0]["遠傳升續率"].mean()
                f3.metric("升續率", f"{avg_up*100:.1f}%" if not pd.isna(avg_up) else "0%")
                
                avg_flat = df_all[df_all["遠傳平續率"]>0]["遠傳平續率"].mean()
                f4.metric("平續率", f"{avg_flat*100:.1f}%" if not pd.isna(avg_flat) else "0%")
                
                st.markdown("---")
                
                # 詳細報表
                st.subheader("📋 詳細分店報表")
                column_cfg = {
                    "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                    "毛利": st.column_config.ProgressColumn("毛利", format="$%d", min_value=0, max_value=int(tp/2) if tp > 0 else 1000),
                    "連結": st.column_config.LinkColumn("檔案連結", display_text="🔗 開啟")
                }
                st.dataframe(df_all, column_config=column_cfg, use_container_width=True, hide_index=True)
            else: st.error(msg)

elif selected_user == "該店總表":
    st.markdown("### 📥 門市報表檢視中心")
    st.info(f"目前設定工作月份：**{view_date.strftime('%Y年%m月')}**")
    
    if st.button(f"📂 讀取 {selected_store} 總表", use_container_width=True):
        with st.spinner("讀取中..."):
            df, fname, link = read_sheet_robust_v13(selected_store, view_date)
            if df is not None:
                st.session_state.current_excel_file = {'df': df, 'name': fname, 'link': link}
                st.success("讀取成功")
            else: st.error(fname)
    
    if st.session_state.current_excel_file:
        f = st.session_state.current_excel_file
        st.subheader(f['name'])
        st.link_button("🔗 開啟試算表", f['link'])
        st.dataframe(f['df'], use_container_width=True)

else:
    # 個人填寫
    st.markdown(f"### 📝 {selected_user} - {view_date.strftime('%Y-%m')} 業績回報")
    
    with st.form("daily_input_full"):
        d_col1, d_col2 = st.columns([1, 3])
        input_date = d_col1.date_input("📅 報表日期", date.today())
        st.markdown("---")

        st.subheader("💰 毛利與門號")
        c1, c2, c3, c4 = st.columns(4)
        in_profit = c1.number_input("毛利 ($)", min_value=0, step=100)
        in_number = c2.number_input("門號 (件)", min_value=0, step=1)
        in_insur = c3.number_input("保險營收 ($)", min_value=0, step=100)
        in_acc = c4.number_input("配件營收 ($)", min_value=0, step=100)

        st.subheader("📱 商品銷售")
        h1, h2, h3, h4 = st.columns(4)
        in_stock = h1.number_input("庫存手機 (台)", min_value=0, step=1)
        in_apple = h2.number_input("蘋果手機 (台)", min_value=0, step=1)
        in_ipad = h3.number_input("蘋果平板/手錶 (台)", min_value=0, step=1)
        in_gplus = h4.number_input("GPLUS吸塵器 (台)", min_value=0, step=1) # Replaced VIVO Phone

        # [New] 重點推廣區塊 (UI)
        st.subheader("🔥 重點推廣與目標")
        n1, n2, n3 = st.columns(3)
        in_huawei = n1.number_input("華為穿戴 (台)", min_value=0, step=1)
        in_orange = n2.number_input("橙艾玻璃貼 (張)", min_value=0, step=1)
        in_vivo_target = n3.number_input("VIVO銷售目標 (台)", min_value=0, step=1)

        st.subheader("🤝 顧客經營")
        s1, s2, s3 = st.columns(3)
        in_life = s1.number_input("生活圈 (人)", min_value=0, step=1)
        in_review = s2.number_input("Google 評論 (則)", min_value=0, step=1)
        in_traffic = s3.number_input("來客數 (人)", min_value=0, step=1)

        st.subheader("📡 遠傳專案指標")
        t1, t2, t3, t4 = st.columns(4)
        in_renew = t1.number_input("遠傳續約 (件)", min_value=0, step=1)
        in_gap = t2.number_input("遠傳續約累積 GAP", step=1)
        in_up = t3.number_input("遠傳升續率 (%)", min_value=0.0, step=0.1)
        in_flat = t4.number_input("遠傳平續率 (%)", min_value=0.0, step=0.1)
        
        in_composite = st.number_input("綜合指標分數", min_value=0.0, step=0.1) 

        if st.form_submit_button("🔍 預覽", use_container_width=True):
            st.session_state.preview_data = {
                '毛利': in_profit, '門號': in_number, '保險營收': in_insur, '配件營收': in_acc,
                '庫存手機': in_stock, '蘋果手機': in_apple, '蘋果平板+手錶': in_ipad, 
                # Replaced VIVO Phone with GPLUS in hardware section logic
                'GPLUS吸塵器': in_gplus,
                '生活圈': in_life, 'GOOGLE 評論': in_review, '來客數': in_traffic,
                '遠傳續約': in_renew, '遠傳續約累積GAP': in_gap, 
                '遠傳升續率': in_up, '遠傳平續率': in_flat,
                '綜合指標': in_composite, '日期': input_date,
                # New items
                '華為穿戴': in_huawei, '橙艾玻璃貼': in_orange, 'VIVO銷售目標': in_vivo_target
            }
            st.rerun()

    if st.session_state.preview_data:
        st.divider()
        st.write("### 確認上傳資料")
        st.dataframe(pd.DataFrame([st.session_state.preview_data]).drop(columns=['日期']), hide_index=True)
        
        c1, c2 = st.columns(2)
        if c1.button("✅ 確認上傳", use_container_width=True, type="primary"):
            d = st.session_state.preview_data.copy()
            t = d.pop('日期')
            msg = update_google_sheet_robust(selected_store, selected_user, t, d)
            if "✅" in msg:
                st.success(msg)
                st.session_state.preview_data = None
                time.sleep(2)
                st.rerun()
            else: st.error(msg)
            
        if c2.button("❌ 取消", use_container_width=True):
            st.session_state.preview_data = None
            st.rerun()
