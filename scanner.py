import pandas as pd
import yfinance as yf
import requests
import numpy as np
import os

def export_sanjuk_format(df_results, filename="sanjuk_watchlist.txt"):
    """
    將選股結果轉換為三竹股市專用的快速複製字串與檔案
    """
    if df_results.empty:
        return ""

    codes = [str(row['代碼']).strip() for _, row in df_results.iterrows()]
    
    # 支援空白與逗號格式
    sanjuk_str = ",".join(codes)

    output_path = os.path.join(os.getcwd(), filename)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(codes))

    return sanjuk_str


def get_all_taiwan_tickers():
    """ 抓取全台股上市 (.TW) + 上櫃 (.TWO) 股票清單 """
    print("1. 正在從政府開放資料 API 抓取全台股上市+上櫃清單...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    tickers = {}

    # 1. 抓取上市股票 (.TW)
    try:
        twse_url = "https://www.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
        res = requests.get(twse_url, headers=headers, timeout=10)
        if res.status_code == 200:
            for row in res.json():
                code = str(row.get('Code', '')).strip()
                name = str(row.get('Name', '')).strip()
                if len(code) == 4 and code.isdigit():
                    tickers[f"{code}.TW"] = name
    except Exception:
        pass

    # 2. 抓取上櫃股票 (.TWO)
    tpex_sources = [
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
        "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratios",
        "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
    ]

    for url in tpex_sources:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list) and len(data) > 0:
                    for row in data:
                        code = str(
                            row.get('SecuritiesCompanyCode') or 
                            row.get('SecCode') or 
                            row.get('CompanyCode') or 
                            row.get('Code') or ''
                        ).strip()
                        
                        name = str(
                            row.get('CompanyName') or 
                            row.get('SecName') or 
                            row.get('Name') or 
                            row.get('AbbreviatedCompanyServices') or ''
                        ).strip()
                        
                        if len(code) == 4 and code.isdigit():
                            tickers[f"{code}.TWO"] = name
                    if len(tickers) > 0:
                        break
        except Exception:
            continue

    return tickers


def calculate_atr(df, period=14):
    """ 計算真實波動區間 ATR """
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()


def run_daily_scan(progress_callback=None):
    stock_map = get_all_taiwan_tickers()
    total = len(stock_map)

    if total == 0:
        return pd.DataFrame()

    results = []
    ticker_list = list(stock_map.keys())
    
    for idx, ticker in enumerate(ticker_list):
        try:
            df = yf.download(ticker, period="1y", interval="1d", progress=False)
            if df.empty or len(df) < 200:
                if progress_callback:
                    progress_callback(idx + 1, total, ticker, stock_map[ticker])
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs(ticker, level=1, axis=1)
                
            # 技術指標基礎計算
            df['MA_20'] = df['Close'].rolling(window=20).mean()
            df['MA_60'] = df['Close'].rolling(window=60).mean()
            df['MA_200'] = df['Close'].rolling(window=200).mean()
            df['MA_Slope'] = df['MA_20'].diff(3)
            
            # 成交量單位換算為張數
            df['Vol_MA_Lots'] = (df['Volume'].rolling(window=20).mean()) / 1000.0
            df['Vol_Ratio'] = df['Volume'] / (df['Vol_MA_Lots'] * 1000.0)
            df['ATR'] = calculate_atr(df)
            
            # MACD 計算
            ema12 = df['Close'].ewm(span=12, adjust=False).mean()
            ema26 = df['Close'].ewm(span=26, adjust=False).mean()
            df['DIF'] = ema12 - ema26
            df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()

            # 布林通道
            std20 = df['Close'].rolling(window=20).std()
            df['BB_Upper'] = df['MA_20'] + (std20 * 2)
            df['BB_Lower'] = df['MA_20'] - (std20 * 2)
            df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['MA_20']

            # KD 指標
            low_min = df['Low'].rolling(window=9).min()
            high_max = df['High'].rolling(window=9).max()
            rsv = (df['Close'] - low_min) / (high_max - low_min) * 100
            df['K'] = rsv.ewm(com=2, adjust=False).mean()
            df['D'] = df['K'].ewm(com=2, adjust=False).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            curr_price = float(curr['Close'])
            prev_price = float(prev['Close'])
            curr_open = float(curr['Open'])
            curr_ma20 = float(curr['MA_20'])
            curr_ma60 = float(curr['MA_60'])
            curr_ma200 = float(curr['MA_200'])
            slope = float(curr['MA_Slope'])
            vol_ratio = float(curr['Vol_Ratio'])
            atr = float(curr['ATR'])
            pct_change = (curr_price - prev_price) / prev_price
            
            vol_ma_lots = float(curr['Vol_MA_Lots'])
            recent_high = float(df['High'].tail(60).max())
            dist_to_high = (recent_high - curr_price) / curr_price

            curr_k, curr_d = float(curr['K']), float(curr['D'])
            prev_k, prev_d = float(prev['K']), float(prev['D'])
            
            k_candle_body = (curr_price - curr_open) / curr_open
            upper_shadow = float(curr['High']) - max(curr_price, curr_open)
            body_length = abs(curr_price - curr_open)

            # 流動性與假突破濾網
            if np.isnan(vol_ma_lots) or vol_ma_lots < 300.0:
                if progress_callback:
                    progress_callback(idx + 1, total, ticker, stock_map[ticker])
                continue

            if upper_shadow > (body_length * 1.5) and upper_shadow > 0:
                if progress_callback:
                    progress_callback(idx + 1, total, ticker, stock_map[ticker])
                continue

            # 多頭總體濾網
            macro_bull = (curr_price > curr_ma60) and (curr_ma60 > curr_ma200)
            macd_bull = (float(curr['DIF']) > float(curr['DEA'])) and (float(curr['DIF']) > 0)
            
            if macro_bull and macd_bull:
                signals = []
                
                # 波段買點
                if slope >= 0 and prev['Close'] < prev['MA_20'] and curr_price > curr_ma20:
                    if vol_ratio >= 1.3 and pct_change >= 0.015:
                        signals.append("B1 強勢帶量突破")
                elif slope > 0 and prev['Close'] < prev['MA_20'] and curr_price > curr_ma20:
                    if vol_ratio >= 1.2:
                        signals.append("B2 假跌破成功站回")
                elif slope > 0 and curr_price > curr_ma20 and pct_change > 0:
                    if (prev['Close'] - prev['MA_20']) / prev['MA_20'] < 0.02 and vol_ratio <= 1.1:
                        signals.append("B3 縮量回測月線支撐")

                # 短線買點
                kd_gold_cross = (prev_k < prev_d) and (curr_k > curr_d)
                if kd_gold_cross and curr_k < 50 and vol_ratio >= 1.3 and k_candle_body > 0.015:
                    signals.append("S1 KD低檔金叉爆量攻")

                bb_compressed = float(prev['BB_Width']) < 0.12
                bb_breakout = curr_price > float(curr['BB_Upper'])
                if bb_compressed and bb_breakout and vol_ratio >= 1.4:
                    signals.append("S2 布林壓縮爆發突破")

                prev_open = float(prev['Open'])
                prev_close = float(prev['Close'])
                is_engulfing = (prev_close < prev_open) and (curr_open <= prev_close) and (curr_price > prev_open) and (vol_ratio >= 1.2)
                if is_engulfing and k_candle_body > 0.02:
                    signals.append("S3 多頭吞噬強勢反轉")

                if signals:
                    atr_stop_loss = curr_price - (2 * atr)
                    results.append({
                        "代碼": ticker.split('.')[0],
                        "股票名稱": stock_map[ticker],
                        "收盤價": f"{curr_price:.2f}",
                        "漲跌幅": f"{pct_change:.2%}",
                        "20日均量(張)": int(round(vol_ma_lots)),
                        "觸發買點": ", ".join(signals),
                        "🛑 ATR動態停損": f"{atr_stop_loss:.2f}",
                        "🎯 移動停利(20MA)": f"{curr_ma20:.2f}",
                        "量能倍數": f"{vol_ratio:.2f}x",
                        "距離60日高點": f"{dist_to_high:.2%}"
                    })
        except Exception:
            pass
        
        # 即時回報進度給前端 UI
        if progress_callback:
            progress_callback(idx + 1, total, ticker, stock_map.get(ticker, ""))

    result_df = pd.DataFrame(results)
    output_path = os.path.join(os.getcwd(), "scan_results.csv")
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    export_sanjuk_format(result_df)
    
    return result_df
