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

# ==============================================================================
# ⚙️ 中央參數設定區 (KPI CONFIG) - 未來增減欄位改這裡即可！
# ==============================================================================
# 格式： "欄位名稱": {"col": Excel欄位索引(0-based), "type": "類型", "cat": "分類"}
# Excel 對應：A=0, B=1, C=2 ... I=8, J=9, K=10, L=11 ...
# ------------------------------------------------------------------------------
KPI_CONFIG = {
    # [財務與門號]
    "毛利":       {"col": 0,  "type": "money",  "cat": "finance", "label": "毛利 ($)"},
    "門號":       {"col": 1,  "type": "int",    "cat": "finance", "label": "門號 (件)"},
    "保險營收":   {"col": 2,  "type": "money",  "cat": "finance", "label": "保險營收 ($)"},
    "配件營收":   {"col": 3,  "type": "money",  "cat": "finance", "label": "配件營收 ($)"},
    
    # [硬體銷售] (舊有)
    "庫存手機":   {"col": 4,  "type": "int",    "cat": "hardware", "label": "庫存手機 (台)"},
    "蘋果手機":   {"col": 5,  "type": "int",    "cat": "hardware", "label": "蘋果手機 (台)"},
    "蘋果平板+手錶": {"col": 6, "type": "int",  "cat": "hardware", "label": "蘋果平板/手錶 (台)"},
    
    # [重點目標銷售] (I, J, K, L)
    "華為穿戴":     {"col": 7,  "type": "int",    "cat": "target",   "label": "華為穿戴 (台)"},
    "橙艾玻璃貼":   {"col": 8,  "type": "int",    "cat": "target",   "label": "橙艾玻璃貼 (張)"},
    "VIVO銷售目標": {"col": 9,  "type": "int",    "cat": "target",   "label": "VIVO銷售目標 (台)"},
    "GPLUS吸塵器":  {"col": 10, "type": "int",    "cat": "target",   "label": "GPLUS吸塵器 (台)"},

    # [顧客經營] (Shifted M, N, O, P)
    "生活圈":       {"col": 11, "type": "int",    "cat": "service",  "label": "生活圈 (人)"},
    "GOOGLE 評論":  {"col": 12, "type": "int",    "cat": "service",  "label": "Google 評論 (則)"},
    "來客數":       {"col": 13, "type": "int",    "cat": "service",  "label": "來客數 (人)"},

    # [遠傳專案] (Shifted Q, R, S, T)
    "遠傳續約":        {"col": 14, "type": "int",    "cat": "project",  "label": "遠傳續約 (件)"},
    "遠傳續約累積GAP": {"col": 15, "type": "int",    "cat": "project",  "label": "續約累積 GAP"},
    "遠傳升續率":      {"col": 16, "type": "percent","cat": "project",  "label": "升續率 (%)", "mode": "overwrite"},
    "遠傳平續率":      {"col": 17, "type": "percent","cat": "project",  "label": "平續率 (%)", "mode": "overwrite"},
    
    # [綜合] (U)
    "綜合指標":        {"col": 18, "type": "float",  "cat": "score",    "label": "綜合指標分數", "mode": "overwrite"}
}

# --- 2. Google Sheets 連線與工具 ---

@st.cache_resource
def get_gspread_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return client, drive_service, creds.service_account_email

def check_connection_status():
    try:
        _, _, email = get_gspread_client()
        return True, email
    except: return False, None

def get_working_folder_id(drive_service, root_folder_id, date_obj):
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
        return [s for s in all_sheets if s not in exclude_list]
    except: return []

# --- 讀取與彙整功能 (使用 KPI_CONFIG 自動對應) ---

def scan_and_aggregate_stores(date_obj):
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
        
        # 初始化統計字典
        stat = {"門市": store_name, "連結": f['webViewLink']}
        for key in KPI_CONFIG:
            stat[key] = 0
        
        try:
            sh = client.open_by_key(f['id'])
            ws = None
            try: ws = sh.worksheet(store_name)
            except: 
                try: ws = sh.worksheet("總表")
                except: pass
            
            if ws:
                # 讀取範圍動態判斷：從 B15 到 最後一欄 (目前到 U=20, 讀到 W 保險)
                data = ws.get("B15:W45")
                for row in data:
                    if len(row) > 0:
                        for key, cfg in KPI_CONFIG.items():
                            col_idx = cfg['col']
                            val = safe_float(row[col_idx]) if len(row) > col_idx else 0
                            
                            # 如果是覆蓋型 (比率/GAP)，取最後一筆非 0
                            if cfg.get('mode') == 'overwrite':
                                if val != 0: stat[key] = val
                            else:
                                # 累加型
                                stat[key] += val

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
        
        updates = []
        for field, new_val in data_dict.items():
            if field in KPI_CONFIG and new_val is not None:
                cfg = KPI_CONFIG[field]
                # 轉回 Excel 欄位索引 (config 是 0-based，gspread 是 1-based, 但 B 欄是 Start, 所以 col=0 -> B=2)
                # B欄是第 2 欄，所以 gspread col = config_col + 2
                col_idx = cfg['col'] + 2
                
                if cfg.get('mode') == 'overwrite':
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
conn_ok, _ = check_connection_status()
if conn_ok: st.sidebar.success("🟢 系統連線正常", icon="📶")
else: st.sidebar.error("🔴 系統連線失敗")

selected_store = st.sidebar.selectbox("請選擇門市", STORE_NAMES, key="sidebar_store_select")

if selected_store == "(ALL) 全店總表":
    if 'global_view_date' not in st.session_state: st.session_state.global_view_date = date.today()
    selected_user = "全店總覽"
    staff_options = []
else:
    view_date = st.sidebar.date_input("設定工作月份", date.today(), key="sidebar_date_picker")
    with st.spinner("讀取人員名單..."):
        dynamic_staff = fetch_dynamic_staff_list(selected_store, view_date)
    
    if dynamic_staff: staff_options = ["該店總表"] + dynamic_staff
    else:
        staff_options = ["該店總表"]
        st.sidebar.caption("⚠️ 尚未建立該月檔案或讀取失敗")
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options, key="sidebar_user_select")

st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ 系統資訊", expanded=False):
    st.markdown("""
    **馬尼門市業績戰情表**
    © 2025 Money KPI
    **v16.0 旗艦版：**
    * 架構升級：導入中央參數設定 (KPI_CONFIG)，未來增減欄位只需修改設定區。
    * 介面美化：全店總表導入分頁 (Tabs) 設計。
    """)

st.title(f"📊 {selected_store} - {selected_user}")

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
            else: st.error("❌ 密碼錯誤")
    return False

if not check_store_auth(selected_store): st.stop()

# =========================================================
# 主畫面邏輯
# =========================================================

if selected_store == "(ALL) 全店總表":
    st.markdown("### 🏆 全公司業績戰情室")
    view_date = st.date_input("選擇檢視月份", date.today(), key="main_date_input")
    
    if st.button("🔄 掃描並彙整全店數據", type="primary", use_container_width=True):
        with st.spinner(f"正在掃描 {view_date.strftime('%Y%m')} 資料..."):
            df_all, msg = scan_and_aggregate_stores(view_date)
            if df_all is not None and not df_all.empty:
                st.success(msg)
                
                # --- 頂部關鍵指標 (Key Metrics) ---
                total_profit = df_all["毛利"].sum()
                total_cases = df_all["門號"].sum()
                store_count = len(df_all)
                
                m1, m2, m3 = st.columns(3)
                m1.metric("全店總毛利", f"${total_profit:,.0f}", border=True)
                m2.metric("全店總門號", f"{total_cases:.0f} 件", border=True)
                m3.metric("營業門市數", f"{store_count} 間", border=True)
                
                st.divider()

                # --- 分頁顯示 (Tabs) ---
                tab1, tab2, tab3, tab4, tab5 = st.tabs([
                    "💰 財務概況", "🎯 重點目標", "🤝 顧客經營", "📡 遠傳專案", "📋 詳細報表"
                ])
                
                with tab1:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("保險營收", f"${df_all['保險營收'].sum():,.0f}")
                    c2.metric("配件營收", f"${df_all['配件營收'].sum():,.0f}")
                    # 毛利已在上面顯示，這裡可以放佔比圖或其他
                    
                with tab2:
                    st.caption("含硬體銷售與推廣目標")
                    # 自動從 CONFIG 取出所有 'hardware' 和 'target' 類別
                    target_cols = [k for k, v in KPI_CONFIG.items() if v['cat'] in ['hardware', 'target']]
                    # 4 column grid
                    cols = st.columns(4)
                    for i, key in enumerate(target_cols):
                        with cols[i % 4]:
                            val = df_all[key].sum()
                            label = KPI_CONFIG[key]['label']
                            # 簡化標籤顯示 (去掉單位括號，讓畫面乾淨)
                            display_label = label.split(" (")[0]
                            st.metric(display_label, f"{val:,.0f}")
                            
                with tab3:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("生活圈", f"{df_all['生活圈'].sum():.0f}")
                    c2.metric("Google 評論", f"{df_all['GOOGLE 評論'].sum():.0f}")
                    c3.metric("來客數", f"{df_all['來客數'].sum():.0f}")
                    
                with tab4:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("遠傳續約", f"{df_all['遠傳續約'].sum():.0f}")
                    c2.metric("續約 GAP", f"{df_all['遠傳續約累積GAP'].sum():.0f}")
                    
                    avg_up = df_all[df_all["遠傳升續率"]>0]["遠傳升續率"].mean()
                    c3.metric("升續率", f"{avg_up*100:.1f}%" if not pd.isna(avg_up) else "0%")
                    
                    avg_flat = df_all[df_all["遠傳平續率"]>0]["遠傳平續率"].mean()
                    c4.metric("平續率", f"{avg_flat*100:.1f}%" if not pd.isna(avg_flat) else "0%")
                    
                with tab5:
                    column_cfg = {
                        "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                        "毛利": st.column_config.ProgressColumn("毛利", format="$%d", min_value=0, max_value=int(total_profit/2) if total_profit > 0 else 1000),
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
        
        # 動態生成表單 (根據 KPI_CONFIG 分類)
        # 1. 財務 (Finance)
        st.subheader("💰 財務與門號")
        fin_items = [k for k,v in KPI_CONFIG.items() if v['cat'] == 'finance']
        cols = st.columns(len(fin_items))
        inputs = {}
        for i, key in enumerate(fin_items):
            inputs[key] = cols[i].number_input(KPI_CONFIG[key]['label'], min_value=0, step=1 if KPI_CONFIG[key]['type']=='int' else 100)

        # 2. 重點目標銷售 (Hardware + Target)
        st.subheader("🎯 重點目標銷售")
        tgt_items = [k for k,v in KPI_CONFIG.items() if v['cat'] in ['hardware', 'target']]
        # Split into rows of 4
        for i in range(0, len(tgt_items), 4):
            batch = tgt_items[i:i+4]
            cols = st.columns(4)
            for j, key in enumerate(batch):
                inputs[key] = cols[j].number_input(KPI_CONFIG[key]['label'], min_value=0, step=1)
        
        # 3. 顧客經營 (Service)
        st.subheader("🤝 顧客經營")
        svc_items = [k for k,v in KPI_CONFIG.items() if v['cat'] == 'service']
        cols = st.columns(len(svc_items))
        for i, key in enumerate(svc_items):
            inputs[key] = cols[i].number_input(KPI_CONFIG[key]['label'], min_value=0, step=1)

        # 4. 專案 (Project)
        st.subheader("📡 遠傳專案指標")
        prj_items = [k for k,v in KPI_CONFIG.items() if v['cat'] == 'project']
        cols = st.columns(len(prj_items))
        for i, key in enumerate(prj_items):
            # 百分比特殊處理
            if KPI_CONFIG[key]['type'] == 'percent':
                inputs[key] = cols[i].number_input(KPI_CONFIG[key]['label'], min_value=0.0, step=0.1, format="%.1f")
            else:
                inputs[key] = cols[i].number_input(KPI_CONFIG[key]['label'], min_value=0, step=1)
        
        # 5. 綜合 (Score)
        score_item = "綜合指標"
        if score_item in KPI_CONFIG:
            st.markdown("---")
            inputs[score_item] = st.number_input(KPI_CONFIG[score_item]['label'], min_value=0.0, step=0.1)

        if st.form_submit_button("🔍 預覽", use_container_width=True):
            # 組合預覽資料
            preview = {'日期': input_date}
            # 百分比轉回小數
            for k, v in inputs.items():
                if KPI_CONFIG[k]['type'] == 'percent':
                    preview[k] = v / 100.0 if v else 0
                else:
                    preview[k] = v
            
            st.session_state.preview_data = preview
            st.rerun()

    if st.session_state.preview_data:
        st.divider()
        st.write("### 確認上傳資料")
        # 預覽時把小數轉回百分比顯示比較好看
        disp_df = pd.DataFrame([st.session_state.preview_data]).drop(columns=['日期'])
        st.dataframe(disp_df, hide_index=True)
        
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
