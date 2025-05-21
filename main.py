import os
import requests
import pandas as pd
from telegram import Bot
from datetime import datetime, timedelta

# 读取环境变量
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
    raise ValueError("请先设置 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 环境变量")

bot = Bot(token=TELEGRAM_TOKEN)


def fetch_binance_data(endpoint: str, futures: bool = False):
    # 可选域名（现货和合约）
    base_urls = (
        ["https://api1.binance.com", "https://api2.binance.com", "https://api3.binance.com"]
        if not futures else
        ["https://fapi.binance.com"]
    )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for base_url in base_urls:
        url = base_url + endpoint
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            print(f"⚠️ HTTP 错误：{url} - {e}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 请求失败：{url} - {e}")

    raise RuntimeError("所有 Binance API 域名请求失败（可能被墙或限制访问）")


def get_spot_data():
    info = fetch_binance_data("/api/v3/exchangeInfo", futures=False)
    if 'symbols' not in info:
        raise RuntimeError("现货 exchangeInfo 响应格式错误")
    active_symbols = {s['symbol'] for s in info['symbols'] if s['status'] == 'TRADING'}

    data = fetch_binance_data("/api/v3/ticker/24hr", futures=False)
    df = pd.DataFrame(data)
    df = df[df['symbol'].isin(active_symbols)]
    df = df[df['symbol'].str.endswith('USDT')]
    df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
    df['lastPrice'] = pd.to_numeric(df['lastPrice'], errors='coerce')
    return df.dropna(subset=['priceChangePercent', 'lastPrice'])


def get_futures_data():
    info = fetch_binance_data("/fapi/v1/exchangeInfo", futures=True)
    if 'symbols' not in info:
        raise RuntimeError("合约 exchangeInfo 响应格式错误")
    active_symbols = {s['symbol'] for s in info['symbols'] if s['status'] == 'TRADING'}

    data = fetch_binance_data("/fapi/v1/ticker/24hr", futures=True)
    df = pd.DataFrame(data)
    df = df[df['symbol'].isin(active_symbols)]
    df = df[df['symbol'].str.endswith('USDT')]
    df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'], errors='coerce')
    df['lastPrice'] = pd.to_numeric(df['lastPrice'], errors='coerce')
    return df.dropna(subset=['priceChangePercent', 'lastPrice'])


def format_table(df):
    lines = []
    for _, row in df.iterrows():
        sign = '+' if row['priceChangePercent'] >= 0 else ''
        lines.append(f"{row['symbol']:<12} {sign}{row['priceChangePercent']:>6.2f}%   ${row['lastPrice']:.4g}")
    return "\n".join(lines)


def send_to_telegram():
    try:
        spot = get_spot_data()
        fut = get_futures_data()
    except Exception as e:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"❌ 获取行情失败：{e}")
        return

    spot_gainers = spot.sort_values("priceChangePercent", ascending=False).head(10)
    spot_losers = spot.sort_values("priceChangePercent").head(10)
    fut_gainers = fut.sort_values("priceChangePercent", ascending=False).head(10)
    fut_losers = fut.sort_values("priceChangePercent").head(10)

    now = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M (UTC+8)")

    msg = "📊 *币安 24H 涨跌榜（USDT）*\n\n"
    msg += "🔸 *现货涨幅榜*\n```text\n" + format_table(spot_gainers) + "\n```\n"
    msg += "🔸 *现货跌幅榜*\n```text\n" + format_table(spot_losers) + "\n```\n"
    msg += "🔸 *合约涨幅榜*\n```text\n" + format_table(fut_gainers) + "\n```\n"
    msg += "🔸 *合约跌幅榜*\n```text\n" + format_table(fut_losers) + "\n```\n"
    msg += f"📅 更新时间：{now}"

    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')


if __name__ == "__main__":
    send_to_telegram()
