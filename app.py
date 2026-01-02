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
    st.error("❌ 缺少套件，請在 requirements.txt 加入 `gspread`")
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
    return client, drive_service

def get_sheet_id_by_name(drive_service, filename, folder_id):
    """搜尋檔案 ID"""
    query = f"name = '{filename}' and trashed = false and mimeType = 'application/vnd.google-apps.spreadsheet'"
    if folder_id:
        query += f" and '{folder_id}' in parents" 
    results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
    items = results.get('files', [])
    if not items: return None, None
    return items[0]['id'], items[0]['webViewLink']

def safe_float(value):
    """將表格內容轉為浮點數，失敗回傳 0"""
    try:
        if value in [None, "", " "]: return 0.0
        return float(str(value).replace(",", "").replace("$", "").replace("%", ""))
    except ValueError:
        return 0.0

def update_google_sheet(store, staff, date_obj, data_dict):
    """寫入單一門市單一人員數據"""
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"

    try:
        client, drive_service = get_gspread_client()
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        if not file_id:
            return f"❌ 找不到試算表：[{filename}]。請確認已將 Excel 轉存為 Google 試算表格式。"

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
                    # 讀取舊值累加
                    old_val = ws.cell(target_row, col_idx).value
                    final_val = safe_float(old_val) + new_val
                    updates.append({'range': gspread.utils.rowcol_to_a1(target_row, col_idx), 'values': [[final_val]]})

        if updates: ws.batch_update(updates)
        return f"✅ 資料已成功寫入：{filename}"

    except Exception as e:
        return f"❌ 寫入失敗: {str(e)}"

def read_google_sheet_data(store, date_obj):
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表"
    try:
        client, drive_service = get_gspread_client()
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        if not file_id: return None, f"找不到試算表：{filename}", None
        sh = client.open_by_key(file_id)
        return sh, filename, file_url
    except Exception as e:
        return None, str(e), None

def aggregate_all_stores_gs(date_obj):
    """
    (真實版) 彙整所有分店數據
    會開啟每一家分店的試算表，將該店所有人員當日數據加總。
    """
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    client, drive_service = get_gspread_client()
    
    all_data = []
    
    # 定義要加總的欄位索引 (Excel 中的 Column B=2, C=3...)
    # 這裡我們只抓取重點數據進行加總展示
    metrics_indices = {
        "毛利": 2, "門號": 3, "保險營收": 4, "配件營收": 5, "綜合指標": 17
    }
    
    target_row = 15 + (date_obj.day - 1)

    # 進度條
    prog_bar = st.progress(0, text="開始彙整...")
    total_steps = len(STORES) - 1 # 扣掉 ALL
    current_step = 0

    for store_name, staff_list in STORES.items():
        if store_name == "(ALL) 全店總表": continue
        
        current_step += 1
        prog_bar.progress(int(current_step / total_steps * 100), text=f"正在讀取：{store_name}...")
        
        filename = f"{date_obj.year}_{date_obj.month:02d}_{store_name}業績日報表"
        file_id, file_url = get_sheet_id_by_name(drive_service, filename, folder_id)
        
        store_stats = {
            "門市": store_name,
            "毛利": 0, "門號": 0, "保險營收": 0, "配件營收": 0, "綜合指標": 0,
            "狀態": "❌ 缺檔"
        }

        if file_id:
            try:
                sh = client.open_by_key(file_id)
                store_stats["狀態"] = "✅ 正常"
                
                # 遍歷該店所有人員進行加總
                # 注意：這會比較慢，因為要開多個分頁。為了效能，這裡假設 Excel 有一個 "總表" 分頁
                # 如果您的 Excel 已經有公式自動算總表，讀總表最快。
                # 如果沒有，我們必須讀每個人的分頁。
                
                # 方案 A：嘗試讀取 '總表' 或 '總計' 分頁 (最快)
                summary_sheet = None
                for possible_name in ["總表", "總計", "TOTAL", "Total"]:
                    try:
                        summary_sheet = sh.worksheet(possible_name)
                        break
                    except: pass
                
                if summary_sheet:
                    # 直接讀取總表的該日數據
                    row_vals = summary_sheet.row_values(target_row)
                    # row_vals 是 list，index 0 對應 Col A
                    # 毛利 Col 2 -> index 1
                    if len(row_vals) >= 17:
                        store_stats["毛利"] = safe_float(row_vals[1])
                        store_stats["門號"] = safe_float(row_vals[2])
                        store_stats["保險營收"] = safe_float(row_vals[3])
                        store_stats["配件營收"] = safe_float(row_vals[4])
                        store_stats["綜合指標"] = safe_float(row_vals[16])
                else:
                    # 方案 B：若無總表，則加總所有人員 (較慢，但準確)
                    for staff in staff_list:
                        try:
                            ws = sh.worksheet(staff)
                            val_profit = safe_float(ws.cell(target_row, 2).value)
                            val_num = safe_float(ws.cell(target_row, 3).value)
                            val_ins = safe_float(ws.cell(target_row, 4).value)
                            val_acc = safe_float(ws.cell(target_row, 5).value)
                            val_score = safe_float(ws.cell(target_row, 17).value)
                            
                            store_stats["毛利"] += val_profit
                            store_stats["門號"] += val_num
                            store_stats["保險營收"] += val_ins
                            store_stats["配件營收"] += val_acc
                            # 綜合指標通常是平均或加總？這裡先用平均
                            if store_stats["綜合指標"] == 0: store_stats["綜合指標"] = val_score
                            else: store_stats["綜合指標"] = (store_stats["綜合指標"] + val_score) / 2
                        except:
                            pass # 該人員分頁不存在跳過

            except Exception as e:
                store_stats["狀態"] = "⚠️ 讀取錯"
                print(e)
        
        all_data.append(store_stats)
    
    prog_bar.empty()
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

# --- 4. 介面與權限邏輯 ---

st.sidebar.title("🏢 門市導航")

# 4.1 選擇門市
selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()), key="sidebar_store_select")

# 4.2 選擇人員
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
        admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="auth_admin_pass") 
        if st.button("驗證管理員", key="btn_auth_admin"): 
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
    st.markdown("### 🏆 全公司業績戰情室")
    st.info("此頁面會連線至各分店的 Google 試算表，讀取當日數據並加總。")
    
    col_date, col_refresh = st.columns([1, 4])
    view_date = col_date.date_input("選擇檢視日期", date.today(), key="date_input_all")
    
    if col_refresh.button("🔄 立即更新全店數據 (真實讀取)", type="primary", key="btn_refresh_all"):
        with st.spinner("正在彙整各分店戰報 (這可能需要一點時間)..."):
            df_all = aggregate_all_stores_gs(view_date)
            
            st.divider()
            total_profit = df_all["毛利"].sum()
            total_cases = df_all["門號"].sum()
            avg_score = df_all[df_all["綜合指標"] > 0]["綜合指標"].mean() # 只算有分數的
            if pd.isna(avg_score): avg_score = 0
            
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("全店總毛利", f"${total_profit:,.0f}", delta="本日即時")
            kpi2.metric("全店總門號", f"{total_cases:.0f} 件")
            kpi3.metric("平均綜合分", f"{avg_score:.1f} 分")
            kpi4.metric("資料來源", f"{len(df_all)} 間門市")
            
            st.subheader("📊 門市績效排行")
            chart1, chart2 = st.columns(2)
            with chart1:
                st.caption("各店毛利貢獻")
                # 簡單過濾掉 0 的店
                df_plot = df_all[df_all["毛利"] > 0]
                if not df_plot.empty:
                    st.bar_chart(df_plot, x="門市", y="毛利", color="#FF4B4B")
                else:
                    st.info("尚無毛利數據")

            with chart2:
                st.caption("綜合指標分數")
                df_plot_score = df_all[df_all["綜合指標"] > 0]
                if not df_plot_score.empty:
                    st.bar_chart(df_plot_score, x="門市", y="綜合指標", color="#3366CC")
                else:
                    st.info("尚無分數數據")

            st.subheader("📋 詳細數據列表")
            
            # 使用 column_config 替代 style.background_gradient
            # 這樣就不會出現 matplotlib ImportError
            column_cfg = {
                "門市": st.column_config.TextColumn("門市名稱", disabled=True),
                "狀態": st.column_config.TextColumn("連線狀態"),
                "毛利": st.column_config.ProgressColumn(
                    "毛利貢獻", 
                    format="$%d", 
                    min_value=0, 
                    max_value=int(df_all["毛利"].max()) if not df_all.empty and df_all["毛利"].max() > 0 else 1000
                ),
                "門號": st.column_config.NumberColumn("門號", format="%d 件"),
                "保險營收": st.column_config.NumberColumn("保險", format="$%d"),
                "配件營收": st.column_config.NumberColumn("配件", format="$%d"),
                "綜合指標": st.column_config.NumberColumn("綜合分數", format="%.1f 分"),
            }
            
            st.dataframe(
                df_all,
                column_config=column_cfg,
                use_container_width=True,
                hide_index=True
            )

elif selected_user == "該店總表":
    st.markdown("### 📥 門市報表檢視中心 (Google Sheets)")
    
    col_d1, col_d2 = st.columns([1, 2])
    view_date = col_d1.date_input("選擇報表月份", date.today(), key="date_input_store")

    if col_d1.button("📂 讀取雲端報表", use_container_width=True, key="btn_load_sheet"):
        with st.spinner("連線 Google Sheets..."):
            sh_obj, file_msg, file_link = read_google_sheet_data(selected_store, view_date)
            if sh_obj:
                st.session_state.current_excel_file = {
                    'sheet_obj': sh_obj, 
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
        
        if c_btn3.button("🔄 重新整理", use_container_width=True, key="btn_refresh_sheet"):
            st.session_state.current_excel_file = None
            st.rerun()

        st.markdown("---")
        st.write("#### 👀 網頁內快速預覽")
        try:
            sh = file_data['sheet_obj']
            worksheets = sh.worksheets()
            sheet_names = [ws.title for ws in worksheets]
            col_sheet, _ = st.columns([1, 2])
            selected_sheet_name = col_sheet.selectbox("選擇要檢視的分頁", sheet_names, key="select_sheet_preview")
            
            ws = sh.worksheet(selected_sheet_name)
            data = ws.get_all_values()
            df_preview = pd.DataFrame(data)
            st.dataframe(df_preview, use_container_width=True)
        except Exception as e:
            st.warning(f"預覽載入失敗: {str(e)}")

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
