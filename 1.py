easyocr
pandas
import os
import re
import datetime
import pandas as pd
import easyocr
from PIL import Image
import numpy as np

CSV_FILE = "expenses_report.csv"
IMAGE_DIR = "receipts"

def init_csv():
    """如果記帳 CSV 不存在，就建立一個新的"""
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(columns=["流水號", "記帳日期", "消費日期", "商店名稱", "金額", "原始文字摘要"])
        df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")

def parse_receipt(image_path):
    """利用 EasyOCR 辨識單張照片並撈出金額與日期"""
    print(f"🔍 正在辨識檔案：{image_path} ...")
    reader = easyocr.Reader(['ch_tra', 'en'])
    
    image = Image.open(image_path)
    image_np = np.array(image)
    results = reader.readtext(image_np, detail=0)
    full_text = "\n".join(results)
    
    # 預設值
    detected_amount = 0.0
    detected_date = datetime.date.today().strftime("%Y-%m-%d")
    
    # 搜尋金額關鍵字
    amount_patterns = [
        r'(?:總計|合計|TOTAL|Amount|金額|應付|實付)[:\s]*\$?([0-9,]+)',
        r'\$?([0-9,]+)\s*(?:元|NTD|TWD)'
    ]
    for pattern in amount_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        if matches:
            clean_num = matches[-1].replace(',', '')
            try:
                detected_amount = float(clean_num)
                break
            except:
                continue
                
    if detected_amount == 0.0:
        all_numbers = re.findall(r'\b\d+\b', full_text)
        nums = [int(n) for n in all_numbers if 1 <= len(n) <= 5]
        clean_nums = [n for n in nums if n not in {2024, 2025, 2026, 114, 115} and n > 0]
        if clean_nums:
            detected_amount = float(max(clean_nums))

    # 搜尋日期
    date_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2})', full_text)
    if date_match:
        detected_date = date_match.group(1).replace('/', '-')
        
    return detected_date, detected_amount, full_text[:100].replace('\n', ' ')

def main():
    init_csv()
    
    if not os.path.exists(IMAGE_DIR) or torch_dir_empty := (len(os.listdir(IMAGE_DIR)) == 0):
        print("ℹ️ receipts 資料夾是空的，沒有新收據需要辨識。")
        return

    # 讀取現有的記帳本
    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
    
    # 開始處理資料夾內的所有圖片
    for file_name in os.listdir(IMAGE_DIR):
        if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            img_path = os.path.join(IMAGE_DIR, file_name)
            
            # 執行辨識
            con_date, amount, summary = parse_receipt(img_path)
            
            # 新增一筆紀錄
            new_id = len(df) + 1
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            
            new_row = {
                "流水號": new_id,
                "記帳日期": today_str,
                "消費日期": con_date,
                "商店名稱": "GitHub自動辨識(請手動微調)",
                "金額": amount,
                "原始文字摘要": summary
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            # 辨識完後，把圖片刪除，防止下次重複辨識
            os.remove(img_path)
            print(f"✅ 成功辨識 {file_name}，金額：${amount}，已從 receipts 中移出。")
            
    # 存檔回 CSV
    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    print("💾 記帳本更新成功！")

if __name__ == "__main__":
    main()