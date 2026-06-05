import telebot
import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time

# ================== CẤU HÌNH ==================
TOKEN = "8728655635:AAFCfai4nE3323W2knPb6lXAsPuyaf2EgcU"
CHAT_ID = 1080023051

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# ================== CÀI ĐẶT THEO TYLER ==================
TIMEFRAME = '30m'
LONDON_START = 7   # UTC (14h VN)
LONDON_END = 11    # UTC (18h VN)

# Cooldown 1 giờ
cooldown = {}

def is_in_cooldown(symbol):
    if symbol in cooldown:
        if datetime.now() - cooldown[symbol] < timedelta(hours=1):
            return True
    return False

def update_cooldown(symbol):
    cooldown[symbol] = datetime.now()

# ================== LẤY TOP 100 VOLUME ==================
def get_top100_volume():
    try:
        print("🔄 Đang lấy Top 100 coin volume cao nhất...")
        tickers = exchange.fetch_tickers()
        futures = []
        
        for sym, data in tickers.items():
            if sym.endswith('USDT') and data.get('quoteVolume'):
                futures.append({'symbol': sym, 'volume': data['quoteVolume']})
        
        futures.sort(key=lambda x: x['volume'], reverse=True)
        top100 = [item['symbol'] for item in futures[:100]]
        
        print(f"✅ Top 100 Volume: {top100[:8]} ...")
        return top100
    except:
        print("⚠️ Dùng danh sách dự phòng")
        return ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT']

SYMBOLS = get_top100_volume()

# ================== HÀM HỖ TRỢ ==================
def get_data(symbol, tf='30m', limit=300):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return None

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

# ================== DETECT SIGNAL THEO TYLER ==================
def detect_signal(df, symbol):
    if df is None or len(df) < 60:
        return None
    
    close = df['close']
    ema5  = ema(close, 5)
    ema9  = ema(close, 9)
    ema13 = ema(close, 13)
    ema21 = ema(close, 21)
    ema200 = ema(close, 200)
    
    last = df.iloc[-1]
    p1 = df.iloc[-2]
    p2 = df.iloc[-3]
    p3 = df.iloc[-4]
    
    # Bias theo EMA200
    bias = "BUY" if last['close'] > ema200.iloc[-1] else "SELL"
    
    # EMA Stack
    stack_ok = False
    if bias == "BUY":
        stack_ok = (ema5.iloc[-1] > ema9.iloc[-1] > ema13.iloc[-1] > ema21.iloc[-1])
    else:
        stack_ok = (ema5.iloc[-1] < ema9.iloc[-1] < ema13.iloc[-1] < ema21.iloc[-1])
    
    if not stack_ok:
        return None
    
    # Trident + FVG Pattern
    if bias == "BUY" and p1['low'] > p3['high']:           # Bullish FVG
        midpoint = (p3['high'] + p1['low']) / 2
        body = abs(p2['open'] - p2['close'])
        candle_range = p2['high'] - p2['low'] + 0.000001
        doji_condition = body / candle_range <= 0.35
        
        if doji_condition and p2['low'] <= midpoint <= p2['high']:
            sl = p2['low'] - 0.0010 if 'BTC' in symbol or 'ETH' in symbol else p2['low'] - 0.0005
            entry = last['close']
            tp = entry + (entry - sl) * 20
            return {"side": "BUY", "entry": entry, "sl": sl, "tp": tp, "symbol": symbol}
    
    elif bias == "SELL" and p1['high'] < p3['low']:        # Bearish FVG
        midpoint = (p3['low'] + p1['high']) / 2
        body = abs(p2['open'] - p2['close'])
        candle_range = p2['high'] - p2['low'] + 0.000001
        doji_condition = body / candle_range <= 0.35
        
        if doji_condition and p2['low'] <= midpoint <= p2['high']:
            sl = p2['high'] + 0.0010 if 'BTC' in symbol or 'ETH' in symbol else p2['high'] + 0.0005
            entry = last['close']
            tp = entry - (sl - entry) * 20
            return {"side": "SELL", "entry": entry, "sl": sl, "tp": tp, "symbol": symbol}
    
    return None

def gui_tin_hieu(signal):
    now = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    emoji = "🟢 BUY" if signal['side'] == "BUY" else "🔴 SELL"
    
    msg = f"""
🚨 **TYLER TRIDENT SIGNAL** 🚨

**Coin:** `{signal['symbol']}`
**Loại:** {emoji}
**Entry:** `{signal['entry']:.5f}`

**SL:** `{signal['sl']:.5f}`
**TP:** `{signal['tp']:.5f}` **(RR 1:20)**

🕒 {now} | London Killzone
    """
    bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
    print(f"✅ Signal Tyler: {signal['symbol']} {signal['side']}")

# ================== CHẠY BOT ==================
print("🤖 Bot Tyler Trident Style - Top 100 Volume đang chạy...")
print("Chỉ quét trong London Kill Zone (14h - 18h VN)")

while True:
    try:
        current_utc_hour = datetime.utcnow().hour
        
        if LONDON_START <= current_utc_hour <= LONDON_END:   # Chỉ chạy trong Kill Zone
            signal_count = 0
            for sym in SYMBOLS:
                if is_in_cooldown(sym):
                    continue
                    
                df = get_data(sym, TIMEFRAME)
                signal = detect_signal(df, sym)
                if signal:
                    gui_tin_hieu(signal)
                    update_cooldown(sym)
                    signal_count += 1
                    break   # Mỗi coin chỉ 1 signal/lần quét
                    
            print(f"✅ Hoàn thành quét London Killzone | Signal: {signal_count} | {datetime.now().strftime('%H:%M:%S')}")
        else:
            print(f"⏳ Ngoài London Killzone ({current_utc_hour} UTC) - Đang chờ...")
        
        time.sleep(45)
    except Exception as e:
        print(f"Lỗi: {e}")
        time.sleep(10)
