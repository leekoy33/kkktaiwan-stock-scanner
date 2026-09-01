import pandas as pd
import yfinance as yf
import requests
from datetime import datetime

def get_institutional_data():
    """ 抓取今日全市場上市櫃三大法人買賣超資料 """
    data_dict = {}
    today_str = datetime.now().strftime('%Y%m%d')
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        twse_url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={today_str}&selectType=ALLBUT0999"
        res = requests.get(twse_url, headers=headers, timeout=5)
        if res.status_code == 200:
            json_data = res.json()
            if 'data' in json_data:
                for row in json_data['data']:
                    code = row[0].strip()
                    try:
                        foreign_net = int(row[4].replace(',', ''))
                        trust_net = int(row[10].replace(',', ''))
                        total_net = foreign_net + trust_net
                        data_dict[code] = {"法人買賣超(張)": total_net, "外資": foreign_net, "投信": trust_net}
                    except:
                        continue
    except Exception:
        pass

    try:
        tpex_url = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
        res = requests.get(tpex_url, headers=headers, timeout=5)
        if res.status_code == 200:
            for row in res.json():
                code = str(row.get('SecuritiesCompanyCode', '')).strip()
                try:
                    foreign_net = int(float(row.get('ForeignNetChange', 0)))
                    trust_net = int(float(row.get('TrustNetChange', 0)))
                    total_net = foreign_net + trust_net
                    data_dict[code] = {"法人買賣超(張)": total_net, "外資": foreign_net, "投信": trust_net}
                except:
                    continue
    except Exception:
        pass

    return data_dict

def fetch_realtime_status(df_targets, progress_callback=None):
    results = []
    total = len(df_targets)
    inst_data = get_institutional_data()

    for idx, row in df_targets.iterrows():
        code = str(row['代碼']).zfill(4)
        name = row['股票名稱']
        
        if progress_callback:
            progress_callback(idx + 1, total, code, name)

        try:
            stop_loss = float(row['🛑 ATR動態停損'])
            take_profit_ma20 = float(row['🎯 移動停利(20MA)'])
            scan_price = float(row['收盤價'])
        except (ValueError, KeyError):
            continue

        chip_info = inst_data.get(code, {"法人買賣超(張)": 0, "外資": 0, "投信": 0})
        net_lots = chip_info["法人買賣超(張)"]

        if net_lots > 300:
            chip_check = "🔥 法人大買(>300張)"
        elif net_lots < -300:
            chip_check = "⚠️ 法人倒貨(< -300張)"
        else:
            chip_check = "⚖️ 法人籌碼中性"

        ticker_tw = f"{code}.TW"
        ticker_two = f"{code}.TWO"
        
        df_realtime = yf.download(ticker_tw, period="2d", interval="1m", progress=False)
        if df_realtime.empty:
            df_realtime = yf.download(ticker_two, period="2d", interval="1m", progress=False)

        if df_realtime.empty:
            latest_price = scan_price
            open_price = scan_price
            status_flag = "⚪ 無法取得即時價"
            open_check = "⚪ 無法判定"
        else:
            if isinstance(df_realtime.columns, pd.MultiIndex):
                df_realtime = df_realtime.xs(df_realtime.columns.levels[1][0], level=1, axis=1)

            latest_price = float(df_realtime['Close'].iloc[-1])
            today_data = df_realtime[df_realtime.index.date == df_realtime.index[-1].date()]
            open_price = float(today_data['Open'].iloc[0]) if not today_data.empty else latest_price

            open_pct_change = (open_price - scan_price) / scan_price

            if open_pct_change > 0.035:
                open_check = "🚨 跳空過高(>3.5%)"
            elif open_pct_change < -0.01:
                open_check = "⚠️ 開盤開低(< -1%)"
            else:
                open_check = "🟢 溫和開盤"

            if latest_price <= stop_loss:
                status_flag = "🚨 跌破 ATR 停損"
            elif latest_price <= take_profit_ma20:
                status_flag = "⚠️ 跌破 20MA 停利"
            else:
                status_flag = "🟢 正常持有"

        results.append({
            "代碼": code,
            "股票名稱": name,
            "選股價": f"{scan_price:.2f}",
            "即時價": f"{latest_price:.2f}",
            "開盤健檢": open_check,
            "籌碼面健檢": chip_check,
            "法人買賣超": f"{net_lots:+d} 張",
            "盤中風控": status_flag,
            "🛑 ATR停損": f"{stop_loss:.2f}",
            "🎯 20MA停利": f"{take_profit_ma20:.2f}",
            "觸發買點": row.get('觸發買點', '')
        })

    return pd.DataFrame(results)
