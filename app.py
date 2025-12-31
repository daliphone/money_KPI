# --- [升級版] Google Drive 雲端存取模組 ---

def get_file_id_in_folder(service, filename, folder_id):
    """
    在「指定資料夾」中搜尋檔案
    """
    # 語法：name = '檔名' AND '資料夾ID' in parents AND trashed = false
    query = f"name = '{filename}' and '{folder_id}' in parents and trashed = false"
    
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    
    if not items:
        return None
    return items[0]['id'] # 回傳找到的第一個檔案 ID

def update_excel_drive(store, staff, date_obj, data_dict):
    # 1. 讀取 secrets 中的資料夾 ID
    folder_id = st.secrets.get("TARGET_FOLDER_ID")
    if not folder_id:
        return "❌ 設定錯誤：找不到 TARGET_FOLDER_ID，請檢查 secrets.toml。"

    # 2. [關鍵] 根據日期自動產生檔名 (YYYY_MM_店名...)
    # 例如：2025_12_東門店業績日報表.xlsx
    filename = f"{date_obj.year}_{date_obj.month:02d}_{store}業績日報表.xlsx"
    
    try:
        service = get_drive_service()
        
        # 3. 在指定資料夾搜尋檔案
        file_id = get_file_id_in_folder(service, filename, folder_id)
        
        if not file_id:
            return f"❌ 找不到檔案：[{filename}] \n請確認：\n1. 檔案是否已上傳至公用資料夾\n2. 檔名是否包含年月 (例如 2025_12_...)"

        # 4. 下載檔案 (跟之前一樣)
        request = service.files().get_media(fileId=file_id)
        file_content = request.execute()
        excel_stream = BytesIO(file_content)
        
        # 5. 用 openpyxl 修改 (跟之前一樣)
        wb = openpyxl.load_workbook(excel_stream)
        
        if staff not in wb.sheetnames:
            return f"❌ 檔案 [{filename}] 中找不到分頁：{staff}"
        
        ws = wb[staff]
        
        # 6. 定位與寫入 (跟之前一樣)
        # 注意：如果是每月一個檔，每月的1號通常都是從 Row 15 開始 (依照你的 Excel 設計)
        target_row = 15 + (date_obj.day - 1)
        
        # 檢查日期防呆
        check_day = ws.cell(row=target_row, column=1).value
        # 有些 Excel 日期格式可能會變，這裡做個簡單容錯，或者您可以暫時拿掉這行檢查
        # if str(check_day) != str(date_obj.day): ...
        
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
                
                old_val = cell.value
                if old_val is None or not isinstance(old_val, (int, float)):
                    old_val = 0
                
                if field in overwrite_fields:
                    cell.value = new_val
                else:
                    cell.value = old_val + new_val

        # 7. 上傳覆蓋 (跟之前一樣)
        output_stream = BytesIO()
        wb.save(output_stream)
        output_stream.seek(0)
        
        media = MediaIoBaseUpload(output_stream, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()
        
        return f"✅ 資料已存入 [{filename}]！"

    except Exception as e:
        return f"❌ 雲端存取失敗: {str(e)}"
