import streamlit as st
import pandas as pd
import os
from datetime import datetime

from scanner import run_daily_scan, export_sanjuk_format
from monitor import fetch_realtime_status

st.set_page_config(page_title="台股高勝率短線/波段選股儀表板", page_icon="📈", layout="wide")

st.title("📈 台股高勝率強勢股選股與盤中風控儀表板")
st.caption("核心策略：大趨勢多頭 + MACD零軸上控盤 + 葛蘭碧波段 (B1/B2/B3) + 強勢短線爆發 (S1/S2/S3)")

# 側邊欄控制
st.sidebar.header("⚙️ 系統控制區")

if st.sidebar.button("🚀 執行全台股盤後掃描"):
    progress_bar = st.sidebar.progress(0)
    status_text = st.sidebar.empty()

    def update_scan_progress(current, total, ticker, name):
        percent = min(max(current / total, 0.0), 1.0)
        progress_bar.progress(percent)
        status_text.text(f"掃描中 ({current}/{total})\n{ticker} {name}")

    df_results = run_daily_scan(progress_callback=update_scan_progress)
    st.session_state['scan_df'] = df_results
    
    status_text.success("掃描完成！")
    progress_bar.empty()

# 讀取暫存/歷史結果
csv_path = os.path.join(os.getcwd(), "scan_results.csv")
if 'scan_df' not in st.session_state:
    if os.path.exists(csv_path):
        st.session_state['scan_df'] = pd.read_csv(csv_path)
    else:
        st.session_state['scan_df'] = pd.DataFrame()

df_results = st.session_state['scan_df']

if not df_results.empty:
    st.markdown("### 🔍 買點訊號快速篩選")
    all_signals = ["全部買點", "B1 強勢帶量突破", "B2 假跌破成功站回", "B3 縮量回測月線支撐", 
                   "S1 KD低檔金叉爆量攻", "S2 布林壓縮爆發突破", "S3 多頭吞噬強勢反轉"]
    selected_signal = st.selectbox("依買點類型篩選股票：", all_signals)

    if selected_signal != "全部買點":
        filtered_df = df_results[df_results['觸發買點'].str.contains(selected_signal, na=False)]
    else:
        filtered_df = df_results

    st.markdown("---")

    st.subheader("⚡ 盤中即時風險與籌碼監控")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.caption("即時連線抓取開盤價、即時價、三大法人籌碼，並比對 ATR 停損與 20MA 停利。")
    with col2:
        btn_monitor = st.button("🔄 刷新盤中即時行情", type="primary")

    if btn_monitor or st.session_state.get('run_monitor_flag', False):
        st.session_state['run_monitor_flag'] = True
        
        m_progress_bar = st.progress(0)
        m_status_text = st.empty()

        def update_monitor_progress(current, total, code, name):
            m_status_text.text(f"【即時監控】連線中... ({current}/{total}) {code} {name}")
            m_progress_bar.progress(current / total)

        df_monitor = fetch_realtime_status(filtered_df, progress_callback=update_monitor_progress)
        st.session_state['monitor_df'] = df_monitor

        m_status_text.empty()
        m_progress_bar.empty()

        if 'monitor_df' in st.session_state and not st.session_state['monitor_df'].empty:
            m_df = st.session_state['monitor_df']
            
            stop_count = len(m_df[m_df['盤中風控'].str.contains('🚨')])
            profit_count = len(m_df[m_df['盤中風控'].str.contains('⚠️')])
            normal_count = len(m_df[m_df['盤中風控'].str.contains('🟢')])

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("🟢 正常持有標的", f"{normal_count} 檔")
            mc2.metric("⚠️ 跌破月線建議停利", f"{profit_count} 檔")
            mc3.metric("🚨 觸發 ATR 嚴格停損", f"{stop_count} 檔")

            def style_status(val):
                if '🚨' in str(val):
                    return 'background-color: #ff4b4b; color: white; font-weight: bold;'
                elif '⚠️' in str(val):
                    return 'background-color: #ffa726; color: black; font-weight: bold;'
                elif '🟢' in str(val):
                    return 'background-color: #2e7d32; color: white;'
                return ''

            st.write(f"最後更新時間：`{datetime.now().strftime('%H:%M:%S')}`")
            st.dataframe(
                m_df.style.map(style_status, subset=['盤中風控']),
                use_container_width=True,
                hide_index=True
            )

    st.markdown("---")

    st.subheader("📱 三竹股市 / 券商 App 匯入字串")
    sanjuk_code_str = export_sanjuk_format(filtered_df)
    st.info("💡 提示：可直接複製下方字串，或使用專案資料夾內自動產出的 `sanjuk_watchlist.txt` 檔案至電腦版券商軟體批次匯入。")
    st.code(sanjuk_code_str, language="text")

    st.markdown("---")

    st.subheader(f"📋 盤後選股結果清單 (共 {len(filtered_df)} 檔標的)")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

else:
    st.warning("目前尚無選股資料。請先點擊左側邊欄按鈕「🚀 執行全台股盤後掃描」。")
