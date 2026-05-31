import os
import re
import json
import datetime
import pandas as pd
import easyocr
import openai
from dotenv import load_dotenv
from PIL import Image
import numpy as np

CSV_FILE = "expenses_report.csv"
IMAGE_DIR = "receipts"

load_dotenv()


def init_csv():
    """如果記帳 CSV 不存在，就建立一個新的。"""
    if not os.path.exists(CSV_FILE):
        df = pd.DataFrame(
            columns=[
                "流水號",
                "記帳日期",
                "消費日期",
                "商店名稱",
                "類別",
                "金額",
                "備註",
                "原始文字摘要",
            ]
        )
        df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")


def parse_receipt(image_path):
    """利用 EasyOCR 辨識單張照片並撈出金額、日期與原始文字內容。"""
    print(f"🔍 正在辨識檔案：{image_path} ...")
    reader = easyocr.Reader(["ch_tra", "en"], gpu=False)

    image = Image.open(image_path).convert("RGB")
    image_np = np.array(image)
    results = reader.readtext(image_np, detail=0)
    full_text = "\n".join(results)

    detected_amount = 0.0
    detected_date = datetime.date.today().strftime("%Y-%m-%d")

    amount_patterns = [
        r"(?:總計|合計|TOTAL|Amount|金額|應付|實付)[:\s]*\$?([0-9,]+(?:\.[0-9]{1,2})?)",
        r"\$?([0-9,]+(?:\.[0-9]{1,2})?)\s*(?:元|NTD|TWD)",
    ]
    for pattern in amount_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        if matches:
            clean_num = matches[-1].replace(",", "")
            try:
                detected_amount = float(clean_num)
                break
            except ValueError:
                continue

    if detected_amount == 0.0:
        all_numbers = re.findall(r"\b\d+(?:\.\d{1,2})?\b", full_text)
        candidate_nums = [n for n in all_numbers if not n.startswith("0") or n == "0"]
        if candidate_nums:
            try:
                detected_amount = float(max(candidate_nums, key=lambda x: float(x)))
            except ValueError:
                pass

    date_match = re.search(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})", full_text)
    if date_match:
        detected_date = date_match.group(1).replace("/", "-")
        try:
            parsed_date = datetime.datetime.strptime(detected_date, "%Y-%m-%d")
            detected_date = parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            try:
                parsed_date = datetime.datetime.strptime(detected_date, "%Y-%m-%d")
                detected_date = parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                pass

    return detected_date, detected_amount, full_text.strip()


def openai_enhance(full_text, amount, detected_date):
    """使用 OpenAI 生成商店名稱、消費類別與備註。"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "merchant": "GitHub自動辨識",
            "category": "其他",
            "note": "未使用 OpenAI 增強資訊。",
        }

    openai.api_key = api_key
    prompt = (
        "你是一個消費記帳助理。請根據以下收據 OCR 文字，" 
        "幫我生成 JSON，格式如下：\n"
        "{\"merchant\": \"...\", \"category\": \"...\", \"note\": \"...\"}\n"
        "說明：\n"
        "1. merchant = 最合理的商店名稱（最多 20 字）。\n"
        "2. category = 支出類別，例：餐飲、交通、購物、生活、娛樂、其他。\n"
        "3. note = 以一句話描述這筆消費內容。\n"
        "請只輸出純 JSON，不要額外文字。\n\n"
        f"收據文字：\n{full_text}\n"
        f"金額：{amount}\n"
        f"消費日期：{detected_date}\n"
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=180,
        )
        content = response.choices[0].message.content.strip()
        if not content:
            raise ValueError("OpenAI 回傳空內容")

        parsed = json.loads(content)
        return {
            "merchant": parsed.get("merchant", "GitHub自動辨識"),
            "category": parsed.get("category", "其他"),
            "note": parsed.get("note", "無法判斷消費內容。"),
        }
    except Exception as exc:
        print(f"⚠️ OpenAI 增強失敗：{exc}")
        return {
            "merchant": "GitHub自動辨識",
            "category": "其他",
            "note": "OpenAI 增強失敗，請手動補上。",
        }


def main():
    init_csv()
    os.makedirs(IMAGE_DIR, exist_ok=True)

    receipt_files = [
        file_name
        for file_name in os.listdir(IMAGE_DIR)
        if file_name.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    if not receipt_files:
        print("ℹ️ receipts 資料夾是空的，沒有新收據需要辨識。")
        return

    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")

    for file_name in receipt_files:
        img_path = os.path.join(IMAGE_DIR, file_name)
        detected_date, amount, full_text = parse_receipt(img_path)
        enhanced = openai_enhance(full_text, amount, detected_date)

        new_id = len(df) + 1
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        new_row = {
            "流水號": new_id,
            "記帳日期": today_str,
            "消費日期": detected_date,
            "商店名稱": enhanced["merchant"],
            "類別": enhanced["category"],
            "金額": amount,
            "備註": enhanced["note"],
            "原始文字摘要": full_text[:200].replace("\n", " "),
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        os.remove(img_path)
        print(f"✅ 成功辨識 {file_name}，金額：{amount}，已從 receipts 中移出。")

    df.to_csv(CSV_FILE, index=False, encoding="utf-8-sig")
    print("💾 記帳本更新成功！")


if __name__ == "__main__":
    main()
