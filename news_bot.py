#!/usr/bin/env python3
"""毎日の経済・市場ニュースをLINEに送信するボット"""

import os
import re
import requests
import feedparser
from datetime import datetime

LINE_CHANNEL_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

LINE_MAX_LENGTH = 4900

# ── マーケットデータ設定 ──────────────────────────────
MARKET_SYMBOLS_UNUSED = {  # 旧設定（使用しない）
    "【株式指数】": [
        ("日経平均",  "^N225",      "",    0),
        ("TOPIX",    "^TOPX",      "",    2),
        ("S&P500",   "^GSPC",      "",    0),
        ("ナスダック","^IXIC",      "",    0),
        ("ダウ",     "^DJI",       "",    0),
        ("VIX",      "^VIX",       "",    2),
        ("上海総合",  "000001.SS",  "",    2),
        ("ハンセン",  "^HSI",       "",    0),
    ],
    "【為替】": [
        ("USD/JPY",  "USDJPY=X",   "円",  2),
        ("EUR/JPY",  "EURJPY=X",   "円",  2),
        ("EUR/USD",  "EURUSD=X",   "",    4),
        ("GBP/JPY",  "GBPJPY=X",   "円",  2),
        ("AUD/JPY",  "AUDJPY=X",   "円",  2),
        ("USD/CNY",  "USDCNY=X",   "",    4),
    ],
    "【金利】": [
        ("米10年債",  "^TNX",       "%",   3),
        ("日本10年債","^JGB10Y",    "%",   3),
        ("独10年債",  "^BUND10Y",   "%",   3),
    ],
    "【コモディティ】": [
        ("WTI原油",  "CL=F",       "$",   2),
        ("金",       "GC=F",       "$",   0),
        ("銅",       "HG=F",       "$",   3),
    ],
    "【暗号資産】": [
        ("BTC",      "BTC-USD",    "$",   0),
    ],
}

# ── ニュースフィルタ設定 ──────────────────────────────
EXCLUDE_KEYWORDS = [
    "将棋", "囲碁", "WBC", "野球", "サッカー", "テニス", "ゴルフ", "バスケ",
    "バレー", "ラグビー", "水泳", "陸上", "五輪", "オリンピック", "パラリンピック",
    "甲子園", "Jリーグ", "プロ野球", "NFL", "NBA", "MLB",
    "結婚", "離婚", "出産", "熱愛", "交際", "芸人", "俳優", "女優", "アイドル",
    "紅白", "コンサート", "ドラマ", "映画", "アニメ",
    "殺人", "殺害", "死亡", "死去", "逝去", "訃報", "遺体", "遺族",
    "承諾", "心中", "自殺", "強盗", "強姦", "わいせつ", "痴漢",
    "カジノ", "パチンコ", "競馬", "競輪", "オンラインカジノ", "賭博",
    "占い", "星座", "血液型", "おみくじ",
]

MA_KEYWORDS = [
    "TOB", "MBO", "買収", "合併", "M&A", "子会社化", "完全子会社",
    "経営統合", "上場廃止", "非上場化", "株式公開買付", "出資", "資本業務提携",
    "ファンド", "IPO", "増資", "社債", "融資", "リファイナンス", "スピンオフ",
    "分社化", "事業譲渡", "持株会社", "公開買付",
]

CATEGORIES = [
    {
        "label": "💼 M&A・ファイナンス",
        "feeds": [
            {"name": "東洋経済",       "url": "https://toyokeizai.net/list/feed/rss", "max": 15},
            {"name": "NHK経済",        "url": "https://www3.nhk.or.jp/rss/news/cat6.xml", "max": 15},
            {"name": "Yahooビジネス",  "url": "https://news.yahoo.co.jp/rss/topics/business.xml", "max": 15},
        ],
        "filter_keywords": MA_KEYWORDS,
    },
    {
        "label": "📊 マーケット・経済",
        "feeds": [
            {"name": "NHK経済",       "url": "https://www3.nhk.or.jp/rss/news/cat6.xml", "max": 5},
            {"name": "Yahooビジネス", "url": "https://news.yahoo.co.jp/rss/topics/business.xml", "max": 5},
            {"name": "Reuters経済",   "url": "https://jp.reuters.com/rssFeed/businessNews", "max": 4},
        ],
    },
    {
        "label": "🏛️ 政治・政策",
        "feeds": [
            {"name": "NHK政治",   "url": "https://www3.nhk.or.jp/rss/news/cat3.xml", "max": 5},
            {"name": "Yahoo政治", "url": "https://news.yahoo.co.jp/rss/topics/politics.xml", "max": 4},
        ],
    },
    {
        "label": "🌏 国際・地政学",
        "feeds": [
            {"name": "NHK国際",     "url": "https://www3.nhk.or.jp/rss/news/cat4.xml", "max": 5},
            {"name": "Reuters国際", "url": "https://jp.reuters.com/rssFeed/worldNews", "max": 4},
            {"name": "Yahoo国際",   "url": "https://news.yahoo.co.jp/rss/topics/world.xml", "max": 3},
        ],
    },
    {
        "label": "🔬 テクノロジー・産業",
        "feeds": [
            {"name": "NHK科学",  "url": "https://www3.nhk.or.jp/rss/news/cat5.xml", "max": 4},
            {"name": "Yahoo IT", "url": "https://news.yahoo.co.jp/rss/topics/it.xml", "max": 4},
        ],
    },
]


# ── マーケットデータ取得 ──────────────────────────────
def fmt_number(value, decimals):
    """カンマ区切りで数値フォーマット"""
    if decimals == 0:
        return f"{value:,.0f}"
    else:
        return f"{value:,.{decimals}f}"


def fetch_yahoo(symbol):
    """Yahoo Finance v8 APIで終値と前日比を取得"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if len(closes) < 2:
            return None, None
        prev, last = closes[-2], closes[-1]
        return last, last - prev
    except Exception:
        return None, None


def fetch_japan_10y():
    """財務省CSVから日本10年国債利回りを取得"""
    url = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        text = r.content.decode("shift-jis", errors="replace")
        rows = [l for l in text.strip().split("\n") if l.strip().startswith("R")]
        if len(rows) < 2:
            return None, None
        prev_cols = [x.strip() for x in rows[-2].split(",")]
        last_cols = [x.strip() for x in rows[-1].split(",")]
        prev_val = float(prev_cols[10])
        last_val = float(last_cols[10])
        chg = last_val - prev_val  # 金利は差分で表示
        return last_val, chg
    except Exception:
        return None, None


def fetch_ecb_10y():
    """ECB APIからユーロ圏10年国債利回り（独国債の代替）を取得"""
    url = (
        "https://data-api.ecb.europa.eu/service/data/"
        "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y"
        "?lastNObservations=3&format=csvdata"
    )
    try:
        r = requests.get(url, timeout=10)
        lines = [l for l in r.text.strip().split("\n") if not l.startswith("KEY")]
        if len(lines) < 2:
            return None, None
        prev_val = float(lines[-2].split(",")[9])
        last_val = float(lines[-1].split(",")[9])
        chg = last_val - prev_val
        return last_val, chg
    except Exception:
        return None, None


def build_market_message():
    lines = ["📈 マーケットデータ\n" + "=" * 20]

    # 株式指数
    lines.append("\n【株式指数】")
    stocks = [
        ("日経平均",  "^N225",    "",  0),
        ("TOPIX ETF", "1306.T",   "",  0),
        ("S&P500",    "^GSPC",    "",  0),
        ("ナスダック", "^IXIC",   "",  0),
        ("ダウ",      "^DJI",    "",  0),
        ("VIX",       "^VIX",    "",  2),
        ("上海総合",  "000001.SS","",  2),
        ("ハンセン",  "^HSI",    "",  0),
    ]
    for label, sym, unit, dec in stocks:
        price, chg = fetch_yahoo(sym)
        if price is None:
            lines.append(f"  {label:<12} -")
            continue
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(f"  {label:<12} {fmt_number(price, dec)}{unit}  {arrow}{fmt_number(abs(chg), dec)}")

    # 為替
    lines.append("\n【為替】")
    fx = [
        ("USD/JPY",  "USDJPY=X", "円", 2),
        ("EUR/JPY",  "EURJPY=X", "円", 2),
        ("EUR/USD",  "EURUSD=X", "",   4),
        ("GBP/JPY",  "GBPJPY=X", "円", 2),
        ("AUD/JPY",  "AUDJPY=X", "円", 2),
        ("USD/CNY",  "USDCNY=X", "",   4),
    ]
    for label, sym, unit, dec in fx:
        price, chg = fetch_yahoo(sym)
        if price is None:
            lines.append(f"  {label:<12} -")
            continue
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(f"  {label:<12} {fmt_number(price, dec)}{unit}  {arrow}{fmt_number(abs(chg), dec)}")

    # 金利（前日比は差分で表示）
    lines.append("\n【金利】")
    # 米10年
    price, chg = fetch_yahoo("^TNX")
    if price:
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(f"  {'米10年債':<12} {fmt_number(price, 3)}%  {arrow}{abs(chg):.3f}")
    else:
        lines.append(f"  {'米10年債':<12} -")
    # 日本10年（財務省）
    price, chg = fetch_japan_10y()
    if price:
        sign = "+" if chg >= 0 else ""
        lines.append(f"  {'日本10年債':<12} {fmt_number(price, 3)}%  ({sign}{chg:.3f})")
    else:
        lines.append(f"  {'日本10年債':<12} -")
    # ドイツ10年（ECB）
    price, chg = fetch_ecb_10y()
    if price:
        sign = "+" if chg >= 0 else ""
        lines.append(f"  {'独10年債':<12} {fmt_number(price, 3)}%  ({sign}{chg:.3f})")
    else:
        lines.append(f"  {'独10年債':<12} -")

    # コモディティ
    lines.append("\n【コモディティ】")
    comm = [
        ("WTI原油", "CL=F",  "$", 2),
        ("金",      "GC=F",  "$", 0),
        ("銅",      "HG=F",  "$", 3),
    ]
    for label, sym, unit, dec in comm:
        price, chg = fetch_yahoo(sym)
        if price is None:
            lines.append(f"  {label:<12} -")
            continue
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(f"  {label:<12} {unit}{fmt_number(price, dec)}  {arrow}{fmt_number(abs(chg), dec)}")

    # 暗号資産
    lines.append("\n【暗号資産】")
    price, chg = fetch_yahoo("BTC-USD")
    if price:
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(f"  {'BTC':<12} ${fmt_number(price, 0)}  {arrow}{fmt_number(abs(chg), 0)}")
    else:
        lines.append(f"  {'BTC':<12} -")

    return "\n".join(lines)


# ── ニュース取得 ──────────────────────────────────────
def clean_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def is_relevant(title):
    return not any(kw in title for kw in EXCLUDE_KEYWORDS)


def matches_keywords(title, summary, keywords):
    return any(kw in title + summary for kw in keywords)


def fetch_all_news():
    seen_urls = set()
    seen_titles = set()
    result = []

    for category in CATEGORIES:
        cat_items = []
        filter_kws = category.get("filter_keywords")

        for feed_info in category["feeds"]:
            try:
                feed = feedparser.parse(feed_info["url"])
                count = 0
                for entry in feed.entries:
                    if count >= feed_info["max"]:
                        break
                    title = entry.title.strip()
                    link = entry.link.strip()
                    summary = clean_html(
                        getattr(entry, "summary", "") or getattr(entry, "description", "")
                    )
                    if not is_relevant(title):
                        continue
                    if filter_kws and not matches_keywords(title, summary, filter_kws):
                        continue
                    if link in seen_urls or title[:20] in seen_titles:
                        continue
                    seen_urls.add(link)
                    seen_titles.add(title[:20])
                    cat_items.append({"title": title, "summary": summary, "link": link})
                    count += 1
            except Exception as e:
                print(f"{feed_info['name']} 取得失敗: {e}")

        result.append({"label": category["label"], "items": cat_items})

    return result


def format_category_message(label, items):
    lines = [label + "\n" + "=" * 20]
    links = []
    for i, item in enumerate(items, 1):
        lines.append(f"\n【{i}】{item['title']}")
        if item["summary"]:
            lines.append(item["summary"])
        links.append(f"[{i}] {item['link']}")
    lines.append("\n\n🔗 詳細")
    lines.extend(links)
    text = "\n".join(lines)
    if len(text) > LINE_MAX_LENGTH:
        text = text[:LINE_MAX_LENGTH] + "\n..."
    return text


def build_header(total_items):
    today = datetime.now().strftime("%Y年%m月%d日")
    dow = ["月", "火", "水", "木", "金", "土", "日"][datetime.now().weekday()]
    return (
        f"📰 {today}（{dow}）朝刊\n"
        f"{'='*20}\n"
        f"本日のニュース {total_items}件をお届けします。\n"
        f"続けてマーケットデータ＋各カテゴリを配信します。"
    )



def send_line_messages(messages):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    for i in range(0, len(messages), 5):
        batch = messages[i:i+5]
        payload = {
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": m} for m in batch],
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        print(f"バッチ {i//5 + 1} 送信完了: {response.status_code}")


def main():
    print("マーケットデータ取得中...")
    market_msg = build_market_message()
    print(market_msg)

    print("\nニュース取得中...")
    categories = fetch_all_news()
    total = sum(len(c["items"]) for c in categories)

    messages = [build_header(total), market_msg]
    for cat in categories:
        if cat["items"]:
            messages.append(format_category_message(cat["label"], cat["items"]))
            print(f"  {cat['label']}: {len(cat['items'])}件")
        else:
            print(f"  {cat['label']}: 0件（本日はなし）")

    print(f"\n合計 {len(messages)} メッセージ送信中...")
    send_line_messages(messages)
    print("完了")


if __name__ == "__main__":
    main()
