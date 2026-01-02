import streamlit as st
import pandas as pd
from datetime import datetime
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# 1. 系統設定與連線準備
# ==========================================

st.set_page_config(
    page_title="馬尼通訊 - 營運管理系統",
    page_icon="📱",
    layout="wide"
)

# 分店清單 (請確保這裡的店名與您的 Excel 檔名一致)
STORE_LIST = ["東門店", "西門店", "南門店", "北門店"]

# 需填寫的 15 項營運目標
INPUT_ITEMS = [
    "毛利", "門號", "保險營收", "配件營收", "庫存手機",
    "蘋果手機", "蘋果平板+手錶", "VIVO手機", "生活圈", "GOOGLE 評論",
    "來客數", "遠傳續約", "累積GAP", "遠傳升續率", "遠傳平續率"
]

# --- Google Drive API 連線函式 ---
def get_drive_service():
    """建立 Google Drive API 服務"""
    if "gcp_service_account" not in st.secrets:
        st.error("找不到 GCP 憑證，請檢查 secrets.toml")
        return None
    
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

# ==========================================
# 2. 核心功能：讀寫 Google Drive Excel
# ==========================================

def save_to_drive_excel(store_name, staff_name, target_date, data_df):
    """
    邏輯 A 實作：
    1. 根據 secrets 中的 TARGET_FOLDER_ID 搜尋檔案。
    2. 下載 Excel -> 寫入新資料 -> 更新回 Drive。
    """
    drive_service = get_drive_service()
    if not drive_service:
        return False

    folder_id = st.secrets["TARGET_FOLDER_ID"]
    
    # 組合目標檔名：例如 "2025_12_東門店業績日報表.xlsx"
    # 這裡假設您的檔名格式是 YYYY_MM_店名業績日報表.xlsx
    file_year = target_date.strftime("%Y")
    file_month = target_date.strftime("%m")
    target_filename = f"{file_year}_{file_month}_{store_name}業績日報表.xlsx"
    
    status_text = st.empty()
    status_text.info(f"🔍 正在資料夾中搜尋：{target_filename} ...")

    try:
        # 1. 搜尋檔案
        query = f"'{folder_id}' in parents and name = '{target_filename}' and trashed = false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])

        if not files:
            st.error(f"❌ 找不到檔案：{target_filename}。請確認 Google Drive 資料夾 ID 正確，且檔案已建立。")
            return False
        
        file_id = files[0]['id']
        status_text.info(f"📥 找到檔案 (ID: {file_id})，正在下載並寫入資料...")

        # 2. 下載檔案到記憶體
        request = drive_service.files().get_media(fileId=file_id)
        file_content = io.BytesIO(request.execute())

        # 3. 使用 Pandas 處理 Excel (寫入邏輯)
        # 我們將資料寫入一個名為 "目標分配紀錄" 的分頁，以免覆蓋原始報表
        try:
            # 嘗試讀取現有 Excel
            # 注意：這裡使用 openpyxl 引擎來處理 .xlsx
            with pd.ExcelWriter(file_content, engine="openpyxl", mode="a", if_sheet_exists="overlay") as writer:
                
                # 準備要寫入的資料：加入填寫人與時間戳記
                data_df["填寫人"] = staff_name
                data_df["填寫日期"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                data_df["目標月份"] = target_date.strftime("%Y-%m")
                
                # 重新排列欄位，把資訊放前面
                cols = ["目標月份", "填寫日期", "填寫人", "評估項目", "目標/數值", "備註"]
                final_df = data_df[cols]

                # 寫入名為 "人員目標_Log" 的分頁 (如果不存在會自動建立，存在則附加)
                # 由於 ExcelWriter 的 append 模式比較複雜，這裡簡化為：
                # 如果分頁已存在，算出列數往下寫；如果不存在，寫在第一列。
                
                sheet_name = "人員目標_Log"
                start_row = 0
                header = True
                
                if sheet_name in writer.book.sheetnames:
                    start_row = writer.book[sheet_name].max_row
                    header = False # 附加模式不重複寫入標題

                final_df.to_excel(writer, sheet_name=sheet_name, startrow=start_row, index=False, header=header)
            
            # 4. 上傳更新後的檔案回 Google Drive
            status_text.info("📤 資料寫入完成，正在上傳更新檔...")
            file_content.seek(0) # 重置指標
            
            media = MediaIoBaseUpload(
                file_content, 
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                resumable=True
            )
            
            updated_file = drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            
            status_text.success(f"✅ 成功！已將 {staff_name} 的目標更新至 {target_filename}")
            return True

        except Exception as e:
            st.error(f"Excel 處理失敗：{str(e)}")
            return False

    except Exception as e:
        st.error(f"Google Drive 連線失敗：{str(e)}")
        return False

# ==========================================
# 3. 介面渲染函式 (維持原本邏輯)
# ==========================================

def render_store_tab(store_name):
    # --- 頂部功能區 ---
    # 這裡可以根據 store_name 產生動態連結 (如果需要的話)
    st.caption(f"目前操作門市：**{store_name}**")
    st.markdown("---")

    # --- 填寫表單區 ---
    st.subheader(f"📝 {store_name} - 營運目標分配")
    
    c1, c2 = st.columns(2)
    with c1:
        staff_name = st.text_input("填寫人員姓名", placeholder="請輸入姓名", key=f"staff_{store_name}")
    with c2:
        # 預設為當月
        target_month = st.date_input("設定月份", value=datetime.now(), key=f"date_{store_name}")

    # 資料結構初始化
    data_key = f'input_data_{store_name}'
    if data_key not in st.session_state:
        st.session_state[data_key] = pd.DataFrame({
            "評估項目": INPUT_ITEMS,
            "目標/數值": [0] * len(INPUT_ITEMS),
            "備註": [""] * len(INPUT_ITEMS)
        })

    # 顯示編輯表
    column_config = {
        "評估項目": st.column_config.TextColumn("評估項目", disabled=True),
        "目標/數值": st.column_config.NumberColumn("目標數值", min_value=0, required=True),
        "備註": st.column_config.TextColumn("備註", width="large")
    }

    edited_df = st.data_editor(
        st.session_state[data_key],
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        num_rows="fixed",
        key=f"editor_{store_name}"
    )

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(f"確認上傳 ({store_name})", use_container_width=True, key=f"btn_upload_{store_name}"):
        if not staff_name:
            st.warning("⚠️ 請務必填寫人員姓名！")
        else:
            # 呼叫上面寫好的 save_to_drive_excel 函式
            save_to_drive_excel(store_name, staff_name, target_month, edited_df)

# ==========================================
# 4. 主程式
# ==========================================

def main():
    st.title("📱 馬尼通訊 - 目標分配 (Drive版)")

    # 簡單用分頁顯示各店
    tabs = st.tabs(STORE_LIST)

    for i, store_name in enumerate(STORE_LIST):
        with tabs[i]:
            render_store_tab(store_name)

if __name__ == "__main__":
    main()
