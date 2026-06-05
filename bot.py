import telebot
import ccxt
import pandas as pd
from datetime import datetime, timedelta
import time

# ================== CẤU HÌNH ==================
TOKEN = "8728655635:AAFCfai4nE3323W2knPb6lXAsPuyaf2EgcU"   # Nếu dùng secret thì bỏ dòng này
CHAT_ID = 1080023051

bot = telebot.TeleBot(TOKEN)

exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

TIMEFRAME = '30m'

# ================== COOLDOWN 1 GIỜ ==================
cooldown = {}

def is_in_cooldown(symbol):
    if symbol in cooldown:
        if datetime.now() - cooldown[symbol] < timedelta(hours=1):
            return True
    return False

def update_cooldown(symbol):
    cooldown[symbol] = datetime.now()

# ================== TOP 100 VOLUME ==================
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
        print(f"✅ Top 100 Volume: {top100[:6]} ...")
        return top100
    except:
        print("⚠️ Dùng danh sách dự phòng")
        return ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']

SYMBOLS = get_top100_volume()

# ================== HÀM PHÂN TÍCH ==================
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
    
    bias = "BUY" if last['close'] > ema200.iloc[-1] else "SELL"
    
    stack_ok = False
    if bias == "BUY":
        stack_ok = (ema5.iloc[-1] > ema9.iloc[-1] > ema13.iloc[-1] > ema21.iloc[-1])
    else:
        stack_ok = (ema5.iloc[-1] < ema9.iloc[-1] < ema13.iloc[-1] < ema21.iloc[-1])
    
    if not stack_ok:
        return None
    
    if bias == "BUY" and p1['low'] > p3['high']:
        midpoint = (p3['high'] + p1['low']) / 2
        body = abs(p2['open'] - p2['close'])
        range_c = p2['high'] - p2['low'] + 0.000001
        doji = body / range_c <= 0.35
        if doji and p2['low'] <= midpoint <= p2['high']:
            sl = p2['low'] - 0.0010 if any(x in symbol for x in ['BTC','ETH']) else p2['low'] - 0.0005
            entry = last['close']
            tp = entry + (entry - sl) * 20
            return {"side": "BUY", "entry": entry, "sl": sl, "tp": tp, "symbol": symbol}
    
    elif bias == "SELL" and p1['high'] < p3['low']:
        midpoint = (p3['low'] + p1['high']) / 2
        body = abs(p2['open'] - p2['close'])
        range_c = p2['high'] - p2['low'] + 0.000001
        doji = body / range_c <= 0.35
        if doji and p2['low'] <= midpoint <= p2['high']:
            sl = p2['high'] + 0.0010 if any(x in symbol for x in ['BTC','ETH']) else p2['high'] + 0.0005
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
**TP:** `{signal['tp']:.5f}` **(1:20)**

🕒 {now} | 24/7 Mode
    """
    bot.send_message(CHAT_ID, msg, parse_mode='Markdown')
    print(f"✅ Signal: {signal['symbol']} {signal['side']}")

# ================== CHẠY BOT 24/7 ==================
print("🤖 Bot Tyler Trident Style - 24/7 Mode đang chạy...")

while True:
    try:
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
                break   # Chỉ gửi 1 signal mỗi coin mỗi lần quét
        
        print(f"✅ Hoàn thành vòng quét | Signal: {signal_count} | {datetime.now().strftime('%H:%M:%S')}")
        time.sleep(40)
    except Exception as e:
        print(f"Lỗi: {e}")
        time.sleep(10)
