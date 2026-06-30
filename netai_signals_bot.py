import requests
import time
from datetime import datetime

# ============================================
# НАСТРОЙКИ
# ============================================
TELEGRAM_TOKEN = "8627627203:AAHIA45pQaoxrFT2en0Szlwfcpc64rBGOhk"
CHAT_ID = "6975085722"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = "4h"  # 4-часовой таймфрейм
SIGNALS_PER_DAY = 5
CHECK_INTERVAL = 300  # проверка каждые 5 минут

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
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

# ============================================
# ПОЛУЧЕНИЕ ДАННЫХ С BINANCE
# ============================================
def get_klines(symbol, interval="4h", limit=50):
    # OKX expects symbols like BTC-USDT and a specific interval format
    interval_map = {"4h": "4H", "1h": "1H", "15m": "15m", "1d": "1D"}
    okx_interval = interval_map.get(interval, "4H")
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
        # OKX возвращает данные от новых к старым - разворачиваем
        raw_candles = list(reversed(raw_candles))

        candles = []
        for d in raw_candles:
            # Формат OKX: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
            candles.append({
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5])
            })
        return candles
    except Exception as e:
        print(f"Ошибка получения данных с Bybit: {e}")
        return []

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

    # EMA расчёт
    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    ema9 = ema(closes[-9:], 9)
    ema21 = ema(closes[-21:], 21)

    # RSI расчёт
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

    # Уровни входа и выхода
    support = min([c["low"] for c in candles[-10:]])
    resistance = max([c["high"] for c in candles[-10:]])

    signal = None

    # СИГНАЛ НА ПОКУПКУ
    if (volume_spike > 1.8 and
        ema9 > ema21 and
        rsi_val < 65 and
        current["close"] > current["open"]):

        stop_loss = round(price * 0.97, 2)
        take_profit1 = round(price * 1.03, 2)
        take_profit2 = round(price * 1.06, 2)

        signal = {
            "type": "🟢 ПОКУПКА (LONG)",
            "symbol": symbol.replace("USDT", "/USDT"),
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

    # СИГНАЛ НА ПРОДАЖУ
    elif (volume_spike > 1.8 and
          ema9 < ema21 and
          rsi_val > 55 and
          current["close"] < current["open"]):

        stop_loss = round(price * 1.03, 2)
        take_profit1 = round(price * 0.97, 2)
        take_profit2 = round(price * 0.94, 2)

        signal = {
            "type": "🔴 ПРОДАЖА (SHORT)",
            "symbol": symbol.replace("USDT", "/USDT"),
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
# ФОРМАТИРОВАНИЕ СООБЩЕНИЯ
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

⏰ <b>Таймфрейм:</b> 4H
🕐 {now}
━━━━━━━━━━━━━━━━━━━━
⚠️ Торгуй осознанно. Это не финансовый совет.
    """
    return msg.strip()

# ============================================
# ОСНОВНОЙ ЦИКЛ
# ============================================
def main():
    print("🚀 NET.AI Signal Bot запущен!")
    send_telegram("🚀 <b>NET.AI Signal Bot запущен!</b>\n\nОтслеживаю BTC и ETH на 4H таймфрейме.\nМаксимум 5 сигналов в день.")

    signals_today = 0
    last_date = datetime.now().date()
    sent_signals = set()

    while True:
        try:
            current_date = datetime.now().date()

            # Сброс счётчика в новый день
            if current_date != last_date:
                signals_today = 0
                sent_signals = set()
                last_date = current_date
                print(f"📅 Новый день — счётчик сброшен")

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
