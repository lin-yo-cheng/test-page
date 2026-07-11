"""Fetch stock index / crypto data and update data.json for the dashboard.

Sources:
  - Yahoo Finance chart API: full daily history in one request, no key needed.
  - TWSE OpenAPI (openapi.twse.com.tw): only returns the latest trading day,
    so those series are built up by appending one point per run.
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DashboardBot/1.0"

YAHOO_SERIES = [
    {"key": "taiex", "name": "台股加權指數", "symbol": "^TWII"},
    {"key": "sp500", "name": "S&P 500", "symbol": "^GSPC"},
    {"key": "nasdaq", "name": "Nasdaq", "symbol": "^IXIC"},
    {"key": "dow", "name": "Dow Jones", "symbol": "^DJI"},
    {"key": "sox", "name": "費城半導體指數 (SOX)", "symbol": "^SOX"},
    {"key": "btc", "name": "比特幣 (BTC/USD)", "symbol": "BTC-USD"},
]

TWSE_SERIES = [
    {"key": "tw_semi", "name": "台股半導體類指數", "match": "半導體類指數"},
    {"key": "tw_finance", "name": "台股金融保險類指數", "match": "金融保險類指數"},
]

HISTORY_LIMIT = 180


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_yahoo_history(symbol):
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        "?range=6mo&interval=1d"
    )
    payload = fetch_json(url)
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    history = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        history.append({"date": date, "close": round(close, 2)})
    return history


def fetch_twse_today():
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
    rows = fetch_json(url)
    today = None
    values = {}
    for row in rows:
        name = row.get("指數", "")
        close_str = row.get("收盤指數", "").replace(",", "")
        if not close_str:
            continue
        for series in TWSE_SERIES:
            if row.get("指數") == series["match"]:
                values[series["key"]] = float(close_str)
        if today is None and row.get("日期"):
            # ROC date e.g. 1150709 -> 2026-07-09
            roc = row["日期"]
            year = int(roc[:3]) + 1911
            today = f"{year}-{roc[3:5]}-{roc[5:7]}"
    return today, values


def load_existing():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {"updated_at": None, "series": {}}


def main():
    data = load_existing()
    series = data.setdefault("series", {})

    for s in YAHOO_SERIES:
        try:
            history = fetch_yahoo_history(s["symbol"])
        except Exception as e:
            print(f"[warn] failed to fetch {s['symbol']}: {e}")
            continue
        series[s["key"]] = {
            "name": s["name"],
            "history": history[-HISTORY_LIMIT:],
        }
        print(f"{s['key']}: {len(history)} points, latest {history[-1] if history else None}")

    try:
        today, values = fetch_twse_today()
    except Exception as e:
        print(f"[warn] failed to fetch TWSE data: {e}")
        today, values = None, {}

    for s in TWSE_SERIES:
        entry = series.setdefault(s["key"], {"name": s["name"], "history": []})
        entry["name"] = s["name"]
        if today and s["key"] in values:
            hist = entry["history"]
            if not hist or hist[-1]["date"] != today:
                hist.append({"date": today, "close": round(values[s["key"]], 2)})
            else:
                hist[-1]["close"] = round(values[s["key"]], 2)
            entry["history"] = hist[-HISTORY_LIMIT:]
            print(f"{s['key']}: appended {today} = {values[s['key']]}")
        else:
            print(f"[warn] no TWSE value for {s['key']}")

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wrote {DATA_FILE}")


if __name__ == "__main__":
    main()
