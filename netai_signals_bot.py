import requests
import time
import json
import os
from datetime import datetime

# ============================================
# НАСТРОЙКИ
# ============================================
TELEGRAM_TOKEN = "8627627203:AAHIA45pQaoxrFT2en0Szlwfcpc64rBGOhk"
CHAT_ID = "6975085722"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = "1h"  # 1-часовой таймфрейм
SIGNALS_PER_DAY = 10
CHECK_INTERVAL = 180  # проверка каждые 3 минуты (чаще, т.к. таймфрейм короче)
REPORT_EVERY_DAYS = 5
HISTORY_FILE = "signals_history.json"

# ============================================
# ОТПРАВКА СООБЩЕНИЯ В TELEGRAM
# ============================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# ============================================
# ХРАНЕНИЕ ИСТОРИИ СИГНАЛОВ (для отчётов)
# ============================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception as e:
        print(f"Ошибка сохранения истории: {e}")

# ============================================
# ПОЛУЧЕНИЕ ДАННЫХ С OKX
# ============================================
def get_klines(symbol, interval="1h", limit=50):
    interval_map = {"4h": "4H", "1h": "1H", "15m": "15m", "1d": "1D"}
    okx_interval = interval_map.get(interval, "1H")
    okx_symbol = symbol.replace("USDT", "-USDT")

    url = "https://www.okx.com/api/v5/market/candles"
    params = {
        "instId": okx_symbol,
        "bar": okx_interval,
        "limit": limit
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()

        if data.get("code") != "0":
            print(f"Ошибка API OKX: {data}")
            return []

        raw_candles = data["data"]
        raw_candles = list(reversed(raw_candles))

        candles = []
        for d in raw_candles:
            candles.append({
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5])
            })
        return candles
    except Exception as e:
        print(f"Ошибка получения данных с OKX: {e}")
        return []

def get_current_price(symbol):
    okx_symbol = symbol.replace("USDT", "-USDT")
    url = "https://www.okx.com/api/v5/market/ticker"
    params = {"instId": okx_symbol}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        if data.get("code") == "0":
            return float(data["data"][0]["last"])
    except Exception as e:
        print(f"Ошибка получения цены: {e}")
    return None

# ============================================
# АНАЛИЗ ОБЪЁМА И ГЕНЕРАЦИЯ СИГНАЛА
# ============================================
def analyze(symbol, candles):
    if len(candles) < 20:
        return None

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]

    current = candles[-1]
    avg_volume = sum(volumes[-20:-1]) / 19
    volume_spike = current["volume"] / avg_volume

    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    ema9 = ema(closes[-9:], 9)
    ema21 = ema(closes[-21:], 21)

    def rsi(data, period=14):
        gains, losses = [], []
        for i in range(1, len(data)):
            diff = data[i] - data[i-1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    rsi_val = rsi(closes[-15:])
    price = current["close"]

    support = min([c["low"] for c in candles[-10:]])
    resistance = max([c["high"] for c in candles[-10:]])

    signal = None

    if (volume_spike > 1.8 and
        ema9 > ema21 and
        rsi_val < 65 and
        current["close"] > current["open"]):

        stop_loss = round(price * 0.97, 2)
        take_profit1 = round(price * 1.03, 2)
        take_profit2 = round(price * 1.06, 2)

        signal = {
            "type": "🟢 ПОКУПКА (LONG)",
            "direction": "long",
            "symbol": symbol.replace("USDT", "/USDT"),
            "raw_symbol": symbol,
            "price": price,
            "entry": f"{round(price * 0.999, 2)} - {round(price * 1.001, 2)}",
            "stop_loss": stop_loss,
            "take_profit1": take_profit1,
            "take_profit2": take_profit2,
            "volume_spike": round(volume_spike, 2),
            "rsi": round(rsi_val, 1),
            "support": round(support, 2),
            "resistance": round(resistance, 2)
        }

    elif (volume_spike > 1.8 and
          ema9 < ema21 and
          rsi_val > 55 and
          current["close"] < current["open"]):

        stop_loss = round(price * 1.03, 2)
        take_profit1 = round(price * 0.97, 2)
        take_profit2 = round(price * 0.94, 2)

        signal = {
            "type": "🔴 ПРОДАЖА (SHORT)",
            "direction": "short",
            "symbol": symbol.replace("USDT", "/USDT"),
            "raw_symbol": symbol,
            "price": price,
            "entry": f"{round(price * 0.999, 2)} - {round(price * 1.001, 2)}",
            "stop_loss": stop_loss,
            "take_profit1": take_profit1,
            "take_profit2": take_profit2,
            "volume_spike": round(volume_spike, 2),
            "rsi": round(rsi_val, 1),
            "support": round(support, 2),
            "resistance": round(resistance, 2)
        }

    return signal

# ============================================
# ФОРМАТИРОВАНИЕ СООБЩЕНИЯ СИГНАЛА
# ============================================
def format_signal(signal):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    msg = f"""
⚡ <b>NET.AI SIGNAL</b> ⚡
━━━━━━━━━━━━━━━━━━━━
{signal['type']}
📌 <b>Пара:</b> {signal['symbol']}
💰 <b>Текущая цена:</b> ${signal['price']:,}

📍 <b>Вход:</b> ${signal['entry']}
🛑 <b>Стоп-лосс:</b> ${signal['stop_loss']:,}
🎯 <b>Тейк-профит 1:</b> ${signal['take_profit1']:,}
🎯 <b>Тейк-профит 2:</b> ${signal['take_profit2']:,}

📊 <b>Объём:</b> x{signal['volume_spike']} от среднего
📈 <b>RSI:</b> {signal['rsi']}
🔵 <b>Поддержка:</b> ${signal['support']:,}
🔴 <b>Сопротивление:</b> ${signal['resistance']:,}

⏰ <b>Таймфрейм:</b> 1H
🕐 {now}
━━━━━━━━━━━━━━━━━━━━
⚠️ Торгуй осознанно. Это не финансовый совет.
    """
    return msg.strip()

# ============================================
# ПРОВЕРКА РЕЗУЛЬТАТОВ СТАРЫХ СИГНАЛОВ
# ============================================
def check_open_signals(history):
    for entry in history:
        if entry.get("status") != "open":
            continue

        current_price = get_current_price(entry["raw_symbol"])
        if current_price is None:
            continue

        if entry["direction"] == "long":
            if current_price >= entry["take_profit1"]:
                entry["status"] = "win"
                entry["result_price"] = current_price
            elif current_price <= entry["stop_loss"]:
                entry["status"] = "loss"
                entry["result_price"] = current_price
        else:
            if current_price <= entry["take_profit1"]:
                entry["status"] = "win"
                entry["result_price"] = current_price
            elif current_price >= entry["stop_loss"]:
                entry["status"] = "loss"
                entry["result_price"] = current_price

    return history

# ============================================
# ОТЧЁТ КАЖДЫЕ 5 ДНЕЙ
# ============================================
def send_report(history):
    closed = [h for h in history if h.get("status") in ("win", "loss")]

    if not closed:
        send_telegram("📊 <b>NET.AI — Отчёт за 5 дней</b>\n\nПока недостаточно завершённых сигналов для статистики. Продолжаем собирать данные.")
        return

    wins = len([h for h in closed if h["status"] == "win"])
    losses = len([h for h in closed if h["status"] == "loss"])
    total = wins + losses
    winrate = round((wins / total) * 100, 1) if total > 0 else 0
    still_open = len([h for h in history if h.get("status") == "open"])

    msg = f"""
📊 <b>NET.AI — Отчёт за 5 дней</b>
━━━━━━━━━━━━━━━━━━━━
✅ <b>Успешных сигналов:</b> {wins}
❌ <b>Неудачных сигналов:</b> {losses}
📈 <b>Винрейт:</b> {winrate}%
🔄 <b>Ещё в процессе:</b> {still_open}
📦 <b>Всего сигналов:</b> {len(history)}
━━━━━━━━━━━━━━━━━━━━
⚠️ Статистика по достижению первого тейк-профита (TP1) или стоп-лосса (SL).
    """
    send_telegram(msg.strip())

# ============================================
# ОСНОВНОЙ ЦИКЛ
# ============================================
def main():
    print("🚀 NET.AI Signal Bot запущен!")
    send_telegram(f"🚀 <b>NET.AI Signal Bot запущен!</b>\n\nОтслеживаю BTC и ETH на 1H таймфрейме.\nМаксимум {SIGNALS_PER_DAY} сигналов в день.\nОтчёт о результатах — каждые {REPORT_EVERY_DAYS} дней.")

    history = load_history()
    signals_today = 0
    last_date = datetime.now().date()
    sent_signals = set()
    start_date = datetime.now().date()
    last_report_date = start_date

    while True:
        try:
            current_date = datetime.now().date()

            if current_date != last_date:
                signals_today = 0
                sent_signals = set()
                last_date = current_date
                print(f"📅 Новый день — счётчик сброшен")

            history = check_open_signals(history)
            save_history(history)

            days_since_report = (current_date - last_report_date).days
            if days_since_report >= REPORT_EVERY_DAYS:
                send_report(history)
                last_report_date = current_date
                print("📊 Отчёт отправлен")

            if signals_today >= SIGNALS_PER_DAY:
                print(f"✅ Лимит {SIGNALS_PER_DAY} сигналов на сегодня достигнут")
                time.sleep(CHECK_INTERVAL)
                continue

            for symbol in SYMBOLS:
                if signals_today >= SIGNALS_PER_DAY:
                    break

                candles = get_klines(symbol, INTERVAL)
                signal = analyze(symbol, candles)

                if signal:
                    signal_key = f"{symbol}_{signal['type']}_{datetime.now().hour}"
                    if signal_key not in sent_signals:
                        message = format_signal(signal)
                        send_telegram(message)
                        sent_signals.add(signal_key)
                        signals_today += 1

                        history.append({
                            "raw_symbol": signal["raw_symbol"],
                            "direction": signal["direction"],
                            "entry_price": signal["price"],
                            "take_profit1": signal["take_profit1"],
                            "stop_loss": signal["stop_loss"],
                            "timestamp": datetime.now().isoformat(),
                            "status": "open"
                        })
                        save_history(history)

                        print(f"📨 Сигнал отправлен: {symbol} {signal['type']} ({signals_today}/{SIGNALS_PER_DAY})")
                        time.sleep(10)
                else:
                    print(f"🔍 {symbol}: сигнала нет")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
