import streamlit as st
import pandas as pd
import openpyxl
from io import BytesIO
from datetime import date
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="全店業績戰情室", layout="wide", page_icon="📈")

# 檢查必要設定
if "gcp_service_account" not in st.secrets:
    st.error("❌ 嚴重錯誤：Secrets 中找不到 [gcp_service_account]。")
    st.stop()
if "TARGET_FOLDER_ID" not in st.secrets:
    st.warning("⚠️ 警告：Secrets 中找不到 TARGET_FOLDER_ID。")

# Google 套件引入
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    st.error("❌ 缺少 Google 套件，請檢查 requirements.txt")
    st.stop()

# --- 2. 密碼驗證模組 (第一層：全站) ---
def check_password():
    if "app_password" not in st.secrets:
        return True

    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 請輸入員工/店長密碼", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 請輸入員工/店長密碼", type="password", on_change=password_entered, key="password")
        st.error("❌ 密碼錯誤")
        return False
    else:
        return True

# --- 3. 管理員密碼驗證 (第二層：全店總表) ---
def check_admin_password():
    """檢查是否輸入正確的管理員密碼"""
    # 如果已經登入過管理員，直接通過
    if st.session_state.get("admin_logged_in", False):
        return True
        
    if "admin_password" not in st.secrets:
        st.warning("⚠️ 未設定 admin_password，所有人皆可查看總表。")
        return True

    st.markdown("### 🛡️ 管理員專區")
    st.info("此區域包含敏感數據，請輸入第二層密碼。")
    
    admin_input = st.text_input("🔑 請輸入管理員密碼", type="password", key="admin_pass_input")
    
    if st.button("解鎖總表"):
        if admin_input == st.secrets["admin_password"]:
            st.session_state["admin_logged_in"] = True
            st.rerun()
        else:
            st.error("❌ 管理員密碼錯誤")
            
    return False

# 執行第一層檢查
if not check_password():
    st.stop()

# --- 4. Google Drive 功能 ---
def get_drive_service():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=['https://www.googleapis.com/auth/drive']
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
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表.xlsx"
    
    try:
        service = get_drive_service()
        file_id = get_file_id_in_folder(service, filename, folder_id)
        if not file_id:
            return f"❌ 找不到檔案 [{filename}]，請確認雲端硬碟檔名是否正確。"

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

# --- 5. 組織設定 ---
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

# --- 6. 介面邏輯 ---
st.sidebar.title("🏢 門市導航")
selected_store = st.sidebar.selectbox("請選擇門市", list(STORES.keys()))

# 根據門市決定人員選單
if selected_store == "(ALL) 全店總表":
    selected_user = "全店總覽"
else:
    staff_options = ["該店總表"] + STORES[selected_store]
    selected_user = st.sidebar.selectbox("請選擇人員", staff_options)

st.title(f"📊 {selected_store} - {selected_user}")

# --- 邏輯分支：全店總表 vs 單店填寫 ---

if selected_store == "(ALL) 全店總表":
    # 呼叫第二層密碼檢查
    if check_admin_password():
        # --- 這裡顯示全店總表的內容 (需驗證通過才看得到) ---
        st.success("✅ 管理員驗證通過")
        
        st.markdown("### 🏆 全公司業績戰情室")
        st.info("此處未來可串接 PowerBI 或讀取所有分店 Excel 進行彙整。")
        
        # 這裡可以做一個簡單的「分店檔案檢視器」作為範例
        st.markdown("#### 📂 快速檢視分店報表狀態")
        view_store = st.selectbox("選擇要檢視的分店 (僅檢視)", [s for s in STORES.keys() if s != "(ALL) 全店總表"])
        view_date = st.date_input("選擇月份 (讀取該月檔案)", date.today())
        
        filename = f"{view_date.year}_{view_date.month:02d}_{view_store}業績日報表.xlsx"
        st.write(f"正在監控檔案： `{filename}`")
        # (這裡未來可以加入讀取 Excel 並畫圖的功能)

else:
    # --- 單店/個人模式 (不需要第二層密碼) ---
    is_input_mode = (selected_user != "該店總表")
    
    if is_input_mode:
        st.markdown("### 📝 今日業績回報")
        st.info("💡 數值將「累加」，GAP/比率類為「覆蓋」。")

        with st.form("daily_input_full", clear_on_submit=True):
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
            
            in_up_rate = in_up_rate_raw / 100
            in_flat_rate = in_flat_rate_raw / 100

            st.markdown("---")
            submit = st.form_submit_button("🚀 提交並寫入 Excel", use_container_width=True)

            if submit:
                # 簡易前端算分
                def calc(act, tgt, w): return (act / tgt * w) if tgt > 0 else 0
                score = (
                    calc(in_profit, DEFAULT_TARGETS['毛利'], 0.25) + 
                    calc(in_number, DEFAULT_TARGETS['門號'], 0.20) + 
                    calc(in_insur, DEFAULT_TARGETS['保險'], 0.15) + 
                    calc(in_acc, DEFAULT_TARGETS['配件'], 0.15) + 
                    calc(in_stock, DEFAULT_TARGETS['庫存'], 0.15)
                )

                data_to_save = {
                    '毛利': in_profit, '門號': in_number, '保險營收': in_insur, '配件營收': in_acc,
                    '庫存手機': in_stock, '蘋果手機': in_apple, '蘋果平板+手錶': in_ipad, 'VIVO手機': in_vivo,
                    '生活圈': in_life, 'GOOGLE 評論': in_review, '來客數': in_traffic,
                    '遠傳續約累積GAP': in_gap, '遠傳升續率': in_up_rate, '遠傳平續率': in_flat_rate
                }
                
                with st.spinner("正在連線 Google Drive 同步資料..."):
                    result_msg = update_excel_drive(selected_store, selected_user, input_date, data_to_save)
                
                if "✅" in result_msg:
                    st.success(result_msg)
                    if score > 0:
                        st.info(f"💡 預估貢獻綜合指標：{score*100:.2f} 分")
                else:
                    st.error(result_msg)
    else:
        # 單店總表顯示區
        st.info(f"歡迎查看 {selected_store} 門市總表 (開發中)")
