"""
فحص الأخبار وإرسالها - نسخة سحابية (تشتغل عبر GitHub Actions)
==================================================================
كل خبر جديد يتبعت في رسالة مستقلة فور نزوله، مع أزرار تصنيف تحته.
"""

import feedparser
import requests
import json
import os
import hashlib
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RSS_FEEDS = {
    "الجزيرة": "https://www.aljazeera.net/aljazeerarss/a7c186be-1baa-4bd4-9d80-a84db769f779/73d0e1b4-532f-45ef-b135-bb92b0b3413b",
    "BBC عربي": "https://feeds.bbci.co.uk/arabic/rss.xml",
    "سكاي نيوز عربية": "https://www.skynewsarabia.com/rss/6a267ac5-0846-4a04-b8f9-e08d70d78e10",
    "رويترز - الشرق الأوسط": "https://www.reuters.com/world/middle-east/rss",
    "فرانس24 عربي": "https://www.france24.com/ar/rss",
    "الأناضول عربي": "https://www.aa.com.tr/ar/rss/default?cat=guncel",
    "RT عربي": "https://arabic.rt.com/rss/",
    "المصري اليوم": "https://www.almasryalyoum.com/rss/rssfeed",
}

CATEGORIES = {
    "military": {"label": "عسكري", "emoji": "🪖",
        "keywords": ["جيش", "عسكري", "قصف", "صاروخ", "غارة", "طائرة مسيّرة",
                     "درون", "قوات", "معركة", "اشتباك", "غزو", "احتلال",
                     "سلاح", "ذخيرة", "جبهة"]},
    "security": {"label": "أمني/إرهاب", "emoji": "🚨",
        "keywords": ["إرهاب", "تفجير", "انفجار", "اعتقال", "مسلحون",
                     "عملية أمنية", "خلية", "هجوم مسلح", "احتجاز"]},
    "diplomacy": {"label": "دبلوماسي/تفاوضي", "emoji": "🤝",
        "keywords": ["مفاوضات", "اتفاق", "هدنة", "وقف إطلاق نار", "قمة",
                     "زيارة رسمية", "وساطة", "محادثات", "مجلس الأمن"]},
    "politics": {"label": "سياسي/داخلي", "emoji": "🏛️",
        "keywords": ["رئيس", "وزير", "حكومة", "برلمان", "انتخابات",
                     "استقالة", "أزمة سياسية", "دستور", "حزب", "معارضة"]},
    "economy": {"label": "عقوبات/اقتصادي", "emoji": "💰",
        "keywords": ["عقوبات", "حظر", "تجميد أصول", "أزمة اقتصادية",
                     "عملة", "تضخم", "ديون"]},
    "escalation": {"label": "تصعيد/حرب", "emoji": "⚔️",
        "keywords": ["تصعيد", "حرب", "نزاع", "توتر عسكري", "تهديد", "إنذار"]},
}

STATE_DIR = "state"
SEEN_FILE = os.path.join(STATE_DIR, "seen_articles.json")
TITLES_FILE = os.path.join(STATE_DIR, "article_titles.json")
LEARNED_FILE = os.path.join(STATE_DIR, "learned_keywords.json")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all_keywords(cat_key, learned):
    base = CATEGORIES[cat_key]["keywords"]
    extra = learned.get(cat_key, [])
    return base + extra


def classify(title, summary, learned):
    text = (title + " " + summary).lower()
    matches = {}
    for cat_key in CATEGORIES:
        kws = get_all_keywords(cat_key, learned)
        count = sum(1 for kw in kws if kw in text)
        if count > 0:
            matches[cat_key] = count
    if not matches:
        return None
    return max(matches, key=matches.get)


def article_hash(link, title):
    return hashlib.md5((link + title).encode("utf-8")).hexdigest()[:12]


def build_keyboard(article_id):
    """أزرار تصنيف تحت كل خبر - المستخدم يضغط الفئة الصح لو التصنيف غلط"""
    buttons = []
    row = []
    for cat_key, data in CATEGORIES.items():
        row.append({"text": f"{data['emoji']} {data['label']}", "callback_data": f"cat|{cat_key}|{article_id}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "✅ التصنيف صح", "callback_data": f"ok|_|{article_id}"}])
    return {"inline_keyboard": buttons}


def send_telegram(text, keyboard=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = json.dumps(keyboard)
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code != 200:
            print(f"[!] خطأ إرسال: {r.text}")
    except Exception as e:
        print(f"[!] فشل الاتصال: {e}")


def main():
    seen_ids = set(load_json(SEEN_FILE, []))
    titles_map = load_json(TITLES_FILE, {})
    learned = load_json(LEARNED_FILE, {})

    new_count = 0
    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"[!] فشل تحميل {source_name}: {e}")
            continue

        for entry in feed.entries[:20]:
            uid = entry.get("id", entry.get("link", entry.get("title", "")))
            if uid in seen_ids:
                continue
            seen_ids.add(uid)

            title = entry.get("title", "بدون عنوان")
            summary = entry.get("summary", "")
            link = entry.get("link", "")

            category = classify(title, summary, learned)
            if category is None:
                continue

            aid = article_hash(link, title)
            titles_map[aid] = {"title": title, "category": category, "ts": datetime.now().isoformat()}

            cat_data = CATEGORIES[category]
            message = (
                f"{cat_data['emoji']} <b>{cat_data['label']}</b> | {source_name}\n\n"
                f"{title}\n\n"
                f"🔗 {link}\n\n"
                f"<i>غلط في التصنيف؟ صحّحه بالأزرار تحت 👇</i>"
            )
            send_telegram(message, build_keyboard(aid))
            new_count += 1

    # امسح titles القديمة (أكتر من 500 عشان الملف ميكبرش)
    if len(titles_map) > 500:
        items = sorted(titles_map.items(), key=lambda x: x[1].get("ts", ""), reverse=True)[:500]
        titles_map = dict(items)

    save_json(SEEN_FILE, list(seen_ids))
    save_json(TITLES_FILE, titles_map)
    print(f"تم إرسال {new_count} خبر جديد")


if __name__ == "__main__":
    main()