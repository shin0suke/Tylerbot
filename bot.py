import ccxt
import pandas as pd
from datetime import datetime, timedelta, time
import asyncio
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ================== CẤU HÌNH ==================
TELEGRAM_TOKEN = "8728655635:AAFCfai4nE3323W2knPb6lXAsPuyaf2EgcU"
CHAT_ID = 1080023051

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

COOLDOWN_MINUTES = 90
USE_LONDON_ONLY = False   # False = 24/7

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# ================== HÀM HỖ TRỢ ==================
def get_top_volume_symbols(limit=100):   # ← Đổi thành 100
    try:
        print(f"🔄 Đang lấy Top {limit} coin volume cao nhất...")
        tickers = exchange.fetch_tickers()
        futures = [
            {'symbol': s, 'volume': d.get('quoteVolume', 0)}
            for s, d in tickers.items()
            if s.endswith('USDT') and d.get('quoteVolume', 0) > 50_000_000
        ]
        futures.sort(key=lambda x: x['volume'], reverse=True)
        top_symbols = [item['symbol'] for item in futures[:limit]]
        print(f"✅ Đã lấy Top {len(top_symbols)} coin (volume > 50M)")
        return top_symbols
    except Exception as e:
        print(f"Lỗi lấy top volume: {e}")
        return ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT']


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def is_london_killzone(dt):
    ny_tz = pytz.timezone('America/New_York')
    ny_time = dt.astimezone(ny_tz)
    return time(3, 0) <= ny_time.time() <= time(6, 30)


def check_higher_tf_bias(symbol, bias):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=80)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for p in [5, 9, 13, 21, 200]:
            df[f'ema{p}'] = ema(df['close'], p)
        curr = df.iloc[-1]
        if bias == "BUY":
            return curr['ema5'] > curr['ema9'] > curr['ema13'] > curr['ema21'] > curr['ema200']
        return curr['ema5'] < curr['ema9'] < curr['ema13'] < curr['ema21'] < curr['ema200']
    except:
        return False


async def send_signal(message: str):
    try:
        await bot.send_message(CHAT_ID, message, parse_mode='HTML')
        print(f"✅ Signal gửi: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"Lỗi Telegram: {e}")


# ================== COMMANDS ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    mode = "🟢 London Killzone" if USE_LONDON_ONLY else "🔴 24/7 Full Scan"
    await message.reply(f"🤖 <b>Tyler Trident Bot</b> đã online!\nMode: <b>{mode}</b>\nQuét: Top 100 coin", parse_mode='HTML')


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    mode = "🟢 London Killzone" if USE_LONDON_ONLY else "🔴 24/7 Full Scan"
    await message.reply(
        f"📊 <b>Bot Status</b>\n"
        f"Mode: <b>{mode}</b>\n"
        f"Quét: Top 100 volume\n"
        f"Cooldown: {COOLDOWN_MINUTES} phút/signal\n"
        f"Time: {datetime.now(pytz.UTC).strftime('%H:%M:%S UTC')}",
        parse_mode='HTML'
    )


@dp.message(Command("london"))
async def cmd_toggle_london(message: types.Message):
    global USE_LONDON_ONLY
    USE_LONDON_ONLY = not USE_LONDON_ONLY
    mode = "🟢 London Killzone" if USE_LONDON_ONLY else "🔴 24/7 Full Scan"
    await message.reply(f"✅ Đã chuyển mode thành: <b>{mode}</b>", parse_mode='HTML')
    print(f"🔄 Mode thay đổi: {mode}")


# ====================== LIVE SCANNER ======================
async def live_scanner():
    print("🚀 Tyler Trident Bot (Top 100 Volume) đang chạy...")
    cooldown = {}

    while True:
        now = datetime.now(pytz.UTC)
        
        if USE_LONDON_ONLY and not is_london_killzone(now):
            await asyncio.sleep(30)
            continue

        symbols = get_top_volume_symbols(100)   # ← Top 100
        signal_count = 0
        mode_str = "London" if USE_LONDON_ONLY else "24/7"

        print(f"[{now.strftime('%H:%M:%S UTC')}] Quét {mode_str} | Top 100 coins")

        for symbol in symbols:
            try:
                if symbol in cooldown and (now - cooldown[symbol]) < timedelta(minutes=COOLDOWN_MINUTES):
                    continue

                ohlcv = exchange.fetch_ohlcv(symbol, '30m', limit=150)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)

                if len(df) < 100:
                    continue

                for p in [5, 9, 13, 21, 200]:
                    df[f'ema{p}'] = ema(df['close'], p)

                df['atr'] = (df['high'] - df['low']).rolling(14).mean().ffill()
                df['vol_ma'] = df['volume'].rolling(8).mean().ffill()

                curr = df.iloc[-1]
                rej = df.iloc[-2]
                left = df.iloc[-3]

                bias = "BUY" if curr['close'] > curr['ema200'] else "SELL"

                ema_ok = (
                    (bias == "BUY" and curr['ema5'] > curr['ema9'] > curr['ema13'] > curr['ema21'] > curr['ema200']) or
                    (bias == "SELL" and curr['ema5'] < curr['ema9'] < curr['ema13'] < curr['ema21'] < curr['ema200'])
                )
                if not ema_ok: continue

                if curr['volume'] < curr['vol_ma'] * 1.35: continue
                if not check_higher_tf_bias(symbol, bias): continue

                signal = None

                # BUY
                if bias == "BUY" and left['low'] > rej['high']:
                    fvg_mid = (left['low'] + rej['high']) / 2
                    body_ratio = abs(rej['close'] - rej['open']) / (rej['high'] - rej['low'] + 1e-8)
                    if (rej['low'] <= fvg_mid <= rej['high'] and body_ratio <= 0.45 and curr['close'] > rej['high']):
                        entry = curr['close']
                        sl = rej['low'] - curr['atr'] * 0.35
                        risk = entry - sl
                        if risk > curr['atr'] * 0.5:
                            tp = entry + risk * 8
                            signal = f"""🚀 <b>TYLER BUY SIGNAL</b> <i>({mode_str})</i>

📍 <b>{symbol}</b>
Entry: <code>{entry:.4f}</code>
SL: <code>{sl:.4f}</code>
TP: <code>{tp:.4f}</code> (1:8)
FVG: <code>{fvg_mid:.4f}</code>"""

                # SELL
                elif bias == "SELL" and left['high'] < rej['low']:
                    fvg_mid = (left['high'] + rej['low']) / 2
                    body_ratio = abs(rej['close'] - rej['open']) / (rej['high'] - rej['low'] + 1e-8)
                    if (rej['high'] >= fvg_mid >= rej['low'] and body_ratio <= 0.45 and curr['close'] < rej['low']):
                        entry = curr['close']
                        sl = rej['high'] + curr['atr'] * 0.35
                        risk = sl - entry
                        if risk > curr['atr'] * 0.5:
                            tp = entry - risk * 8
                            signal = f"""🔴 <b>TYLER SELL SIGNAL</b> <i>({mode_str})</i>

📍 <b>{symbol}</b>
Entry: <code>{entry:.4f}</code>
SL: <code>{sl:.4f}</code>
TP: <code>{tp:.4f}</code> (1:8)
FVG: <code>{fvg_mid:.4f}</code>"""

                if signal:
                    await send_signal(signal)
                    cooldown[symbol] = now
                    signal_count += 1
                    print(f"🚨 SIGNAL {bias} → {symbol}")
                    await asyncio.sleep(8)   # Nghỉ ngắn để tránh spam

            except Exception:
                continue

        print(f"   Hoàn thành vòng quét | Tìm thấy {signal_count} signal\n")
        await asyncio.sleep(20)


async def main():
    print("🤖 Tyler Trident Bot (Top 100) Started!")
    asyncio.create_task(live_scanner())
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
