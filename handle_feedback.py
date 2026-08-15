"""
معالجة ضغطات أزرار التصنيف - يخلي البوت "يتعلم" من تصحيحاتك
==================================================================
كل ما تضغط على فئة تحت خبر، السكريبت ده بياخد كلمات من عنوان الخبر
ويضيفها لقائمة كلمات الفئة دي، عشان أخبار مشابهة تتصنّف صح تلقائي المرة الجاية.
"""

import requests
import json
import os
import re

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

STATE_DIR = "state"
OFFSET_FILE = os.path.join(STATE_DIR, "update_offset.json")
TITLES_FILE = os.path.join(STATE_DIR, "article_titles.json")
LEARNED_FILE = os.path.join(STATE_DIR, "learned_keywords.json")

CATEGORY_LABELS = {
    "military": "عسكري", "security": "أمني/إرهاب", "diplomacy": "دبلوماسي/تفاوضي",
    "politics": "سياسي/داخلي", "economy": "عقوبات/اقتصادي", "escalation": "تصعيد/حرب",
}

# كلمات شائعة نتجاهلها عشان متتضافش كـ"كلمة مفتاحية" (مش مفيدة للتصنيف)
STOPWORDS = {
    "في", "من", "إلى", "على", "أن", "ذلك", "هذا", "هذه", "التي", "الذي",
    "بعد", "قبل", "عن", "مع", "كان", "يكون", "قد", "لم", "لن", "ما", "لا",
    "و", "أو", "لكن", "حيث", "حين", "عند", "دون", "غير", "بين", "حول",
    "نحو", "عبر", "خلال", "ضد", "تم", "يتم", "أكد", "قال", "أعلن", "صرح",
    "كشف", "أوضح", "بشأن", "خلال", "الذى", "اليوم", "أمس", "غدا",
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def answer_callback(callback_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    requests.post(url, data={"callback_query_id": callback_id, "text": text}, timeout=10)


def extract_keywords(title, max_words=3):
    """يطلع كلمات مفيدة (أطول من 3 حروف ومش من الكلمات الشائعة) من عنوان الخبر"""
    words = re.findall(r"[\u0621-\u064A]{4,}", title)  # كلمات عربية 4 حروف فأكتر
    useful = [w for w in words if w not in STOPWORDS]
    return useful[:max_words]


def main():
    offset = load_json(OFFSET_FILE, {"last_update_id": 0})
    titles_map = load_json(TITLES_FILE, {})
    learned = load_json(LEARNED_FILE, {})

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": offset["last_update_id"] + 1, "timeout": 5}
    r = requests.get(url, params=params, timeout=15)
    data = r.json()

    if not data.get("ok"):
        print("[!] فشل جلب التحديثات")
        return

    processed = 0
    for update in data.get("result", []):
        offset["last_update_id"] = update["update_id"]

        cq = update.get("callback_query")
        if not cq:
            continue

        callback_data = cq.get("data", "")
        parts = callback_data.split("|")
        if len(parts) != 3:
            continue

        action, cat_key, article_id = parts
        article_info = titles_map.get(article_id)

        if action == "ok":
            answer_callback(cq["id"], "تمام، التصنيف صح ✅")
            processed += 1
            continue

        if action == "cat" and article_info:
            title = article_info["title"]
            new_words = extract_keywords(title)

            existing = set(learned.get(cat_key, []))
            added = [w for w in new_words if w not in existing]
            if added:
                learned.setdefault(cat_key, []).extend(added)

            label = CATEGORY_LABELS.get(cat_key, cat_key)
            msg = f"تم التصحيح لفئة {label} ✅"
            if added:
                msg += f"\nكلمات جديدة اتضافت: {', '.join(added)}"
            answer_callback(cq["id"], msg)
            processed += 1

    save_json(OFFSET_FILE, offset)
    save_json(LEARNED_FILE, learned)
    print(f"تمت معالجة {processed} تصحيح")


if __name__ == "__main__":
    main()
