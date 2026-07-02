import requests
import time
import json
import os
from datetime import datetime, timezone, timedelta

# ============================================
# НАСТРОЙКИ
# ============================================
TELEGRAM_TOKEN = "8627627203:AAHIA45pQaoxrFT2en0Szlwfcpc64rBGOhk"
CHAT_ID = "6975085722"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
INTERVAL = "30m"
SIGNALS_PER_DAY = 10
CHECK_INTERVAL = 180
HISTORY_FILE = "signals_history.json"
YEREVAN_OFFSET = timedelta(hours=4)

def yerevan_now():
    return datetime.now(timezone.utc) + YEREVAN_OFFSET

# ============================================
# ОТПРАВКА СООБЩЕНИЯ В TELEGRAM
# ============================================
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# ============================================
# ИСТОРИЯ СИГНАЛОВ
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
def get_klines(symbol, interval="30m", limit=50):
    interval_map = {"4h": "4H", "1h": "1H", "30m": "30m", "15m": "15m"}
    okx_interval = interval_map.get(interval, "30m")
    okx_symbol = symbol.replace("USDT", "-USDT")
    url = "https://www.okx.com/api/v5/market/candles"
    params = {"instId": okx_symbol, "bar": okx_interval, "limit": limit}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        if data.get("code") != "0":
            print(f"Ошибка API OKX: {data}")
            return []
        raw_candles = list(reversed(data["data"]))
        return [{"open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5])} for d in raw_candles]
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
# АНАЛИЗ
# ============================================
def analyze(symbol, candles):
    if len(candles) < 21:
        return None, None

    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    current = candles[-1]
    avg_volume = sum(volumes[-20:-1]) / 19
    volume_spike = current["volume"] / avg_volume

    def ema(data, period):
        k = 2 / (period + 1)
        val = data[0]
        for p in data[1:]:
            val = p * k + val * (1 - k)
        return val

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
        return 100 - (100 / (1 + avg_gain / avg_loss))

    ema9 = ema(closes[-9:], 9)
    ema21 = ema(closes[-21:], 21)
    rsi_val = rsi(closes[-15:])
    price = current["close"]

    support = min([c["low"] for c in candles[-10:]])
    resistance = max([c["high"] for c in candles[-10:]])

    # Поддержка и сопротивление
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    key_resistances = sorted(set([round(h, 0) for h in highs]), reverse=True)[:5]
    key_supports = sorted(set([round(l, 0) for l in lows]))[:5]

    sr_signal = None
    for level in key_resistances:
        if abs(price - level) / level < 0.005:
            sr_signal = {"zone_type": "🔴 СОПРОТИВЛЕНИЕ", "action": "возможный разворот вниз или пробой вверх", "level": level}
            break
    if not sr_signal:
        for level in key_supports:
            if abs(price - level) / level < 0.005:
                sr_signal = {"zone_type": "🔵 ПОДДЕРЖКА", "action": "возможный отскок вверх или пробой вниз", "level": level}
                break

    signal = None

    if (volume_spike > 1.3 and ema9 > ema21 and rsi_val < 70 and current["close"] > current["open"]):
        stop_loss = round(price * 0.97, 2)
        take_profit1 = round(price * 1.03, 2)
        take_profit2 = round(price * 1.06, 2)
        signal = {
            "type": "🟢 ПОКУПКА (LONG)", "direction": "long",
            "symbol": symbol.replace("USDT", "/USDT"), "raw_symbol": symbol,
            "price": price, "entry": f"{round(price * 0.999, 2)} - {round(price * 1.001, 2)}",
            "stop_loss": stop_loss, "take_profit1": take_profit1, "take_profit2": take_profit2,
            "volume_spike": round(volume_spike, 2), "rsi": round(rsi_val, 1),
            "support": round(support, 2), "resistance": round(resistance, 2)
        }
    elif (volume_spike > 1.3 and ema9 < ema21 and rsi_val > 45 and current["close"] < current["open"]):
        stop_loss = round(price * 1.03, 2)
        take_profit1 = round(price * 0.97, 2)
        take_profit2 = round(price * 0.94, 2)
        signal = {
            "type": "🔴 ПРОДАЖА (SHORT)", "direction": "short",
            "symbol": symbol.replace("USDT", "/USDT"), "raw_symbol": symbol,
            "price": price, "entry": f"{round(price * 0.999, 2)} - {round(price * 1.001, 2)}",
            "stop_loss": stop_loss, "take_profit1": take_profit1, "take_profit2": take_profit2,
            "volume_spike": round(volume_spike, 2), "rsi": round(rsi_val, 1),
            "support": round(support, 2), "resistance": round(resistance, 2)
        }

    return signal, sr_signal

# ============================================
# ФОРМАТИРОВАНИЕ СИГНАЛА
# ============================================
def format_signal(signal):
    now = yerevan_now().strftime("%d.%m.%Y %H:%M")
    return f"""⚡ <b>NET.AI SIGNAL</b> ⚡
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

⏰ <b>Таймфрейм:</b> 30M
🕐 {now}
━━━━━━━━━━━━━━━━━━━━
⚠️ Торгуй осознанно. Это не финансовый совет."""

# ============================================
# ПРОВЕРКА РЕЗУЛЬТАТОВ
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
# УТРЕННЕЕ ПРИВЕТСТВИЕ (10:00 Ереван)
# ============================================
def send_morning_greeting(history):
    today = yerevan_now().strftime("%d.%m.%Y")
    btc_price = get_current_price("BTCUSDT")
    eth_price = get_current_price("ETHUSDT")

    btc_str = f"${btc_price:,}" if btc_price else "N/A"
    eth_str = f"${eth_price:,}" if eth_price else "N/A"

    msg = f"""🌅 {today} — Доброе утро!

BTC: {btc_str} 📈
ETH: {eth_str} 📈

Бот активен. Слежу за рынком 👁"""
    send_telegram(msg)
    print("🌅 Утреннее приветствие отправлено")

# ============================================
# ДНЕВНОЙ ИТОГ (23:00 Ереван)
# ============================================
def send_daily_summary(today_signals):
    today = yerevan_now().strftime("%d.%m.%Y")

    if not today_signals:
        send_telegram(f"📊 Итог дня — {today}\n\nСигналов сегодня не было.")
        return

    wins = [s for s in today_signals if s.get("status") == "win"]
    losses = [s for s in today_signals if s.get("status") == "loss"]
    open_s = [s for s in today_signals if s.get("status") == "open"]
    total_closed = len(wins) + len(losses)
    winrate = round((len(wins) / total_closed) * 100, 1) if total_closed > 0 else 0

    lines = []
    for i, s in enumerate(today_signals, 1):
        direction = "LONG" if s["direction"] == "long" else "SHORT"
        symbol = s["raw_symbol"].replace("USDT", "")
        if s["status"] == "win":
            result = "✅ +3%"
        elif s["status"] == "loss":
            result = "❌ -3%"
        else:
            result = "🔄 открыта"
        lines.append(f"{i}. {symbol} {direction} {result}")

    summary = "\n".join(lines)
    msg = f"""📊 Итог дня — {today}

{summary}

Итого: {len(wins)}✅ {len(losses)}❌ | Винрейт: {winrate}%"""
    send_telegram(msg)
    print("📊 Дневной итог отправлен")

# ============================================
# ОСНОВНОЙ ЦИКЛ
# ============================================
def main():
    print("🚀 NET.AI Signal Bot запущен!")
    send_telegram(f"🚀 <b>NET.AI Signal Bot запущен!</b>\n\nОтслеживаю BTC, ETH, SOL, BNB на 30M таймфрейме.\nМаксимум {SIGNALS_PER_DAY} сигналов в день.\n\n🌅 Приветствие в 10:00\n📊 Итог дня в 23:00")

    history = load_history()
    signals_today = 0
    today_signals = []
    last_date = yerevan_now().date()
    sent_signals = set()
    morning_sent = False
    summary_sent = False
    last_signal_time = time.time()

    while True:
        try:
            now = yerevan_now()
            current_date = now.date()
            current_hour = now.hour
            current_minute = now.minute

            # Новый день
            if current_date != last_date:
                signals_today = 0
                today_signals = []
                sent_signals = set()
                morning_sent = False
                summary_sent = False
                last_date = current_date
                last_signal_time = time.time()
                print(f"📅 Новый день — счётчик сброшен")

            # Утреннее приветствие в 10:00
            if current_hour == 10 and current_minute < 3 and not morning_sent:
                send_morning_greeting(history)
                morning_sent = True

            # Дневной итог в 23:00
            if current_hour == 23 and current_minute < 3 and not summary_sent:
                history = check_open_signals(history)
                save_history(history)
                # Обновляем статусы сигналов за сегодня
                for ts in today_signals:
                    for h in history:
                        if h.get("timestamp") == ts.get("timestamp"):
                            ts["status"] = h.get("status", "open")
                send_daily_summary(today_signals)
                summary_sent = True

            # Сообщение "рынок спокойный" если нет сигналов 3+ часа
            if time.time() - last_signal_time > 10800 and signals_today < SIGNALS_PER_DAY:
                send_telegram("😴 <b>Рынок спокойный</b>\n\nПоследние 3 часа сигналов нет. Продолжаю следить за рынком...")
                last_signal_time = time.time()
                print("😴 Сообщение о спокойном рынке отправлено")

            history = check_open_signals(history)
            save_history(history)

            if signals_today >= SIGNALS_PER_DAY:
                print(f"✅ Лимит {SIGNALS_PER_DAY} сигналов достигнут")
                time.sleep(CHECK_INTERVAL)
                continue

            for symbol in SYMBOLS:
                if signals_today >= SIGNALS_PER_DAY:
                    break

                candles = get_klines(symbol, INTERVAL)
                signal, sr_signal = analyze(symbol, candles)

                if signal:
                    signal_key = f"{symbol}_{signal['type']}_{now.hour}"
                    if signal_key not in sent_signals:
                        send_telegram(format_signal(signal))
                        sent_signals.add(signal_key)
                        signals_today += 1
                        last_signal_time = time.time()

                        entry = {
                            "raw_symbol": signal["raw_symbol"],
                            "direction": signal["direction"],
                            "entry_price": signal["price"],
                            "take_profit1": signal["take_profit1"],
                            "stop_loss": signal["stop_loss"],
                            "timestamp": now.isoformat(),
                            "status": "open"
                        }
                        history.append(entry)
                        today_signals.append(entry)
                        save_history(history)

                        print(f"📨 Сигнал: {symbol} {signal['type']} ({signals_today}/{SIGNALS_PER_DAY})")
                        time.sleep(10)
                else:
                    print(f"🔍 {symbol}: сигнала нет")

                if sr_signal:
                    sr_key = f"{symbol}_SR_{sr_signal['zone_type']}_{now.hour}"
                    if sr_key not in sent_signals:
                        sr_msg = f"""📍 <b>КЛЮЧЕВОЙ УРОВЕНЬ — {symbol.replace("USDT", "/USDT")}</b>
━━━━━━━━━━━━━━━━━━━━
{sr_signal["zone_type"]}
💰 <b>Цена:</b> ${candles[-1]["close"]:,}
🎯 <b>Уровень:</b> ${sr_signal["level"]:,}
⚡ <b>Сигнал:</b> {sr_signal["action"]}
🕐 {now.strftime("%d.%m.%Y %H:%M")}
━━━━━━━━━━━━━━━━━━━━
⚠️ Торгуй осознанно. Это не финансовый совет."""
                        send_telegram(sr_msg)
                        sent_signals.add(sr_key)
                        print(f"📍 Уровень: {symbol} {sr_signal['zone_type']}")

            time.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
