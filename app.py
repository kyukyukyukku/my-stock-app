import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(page_title="내 손안의 주식 앱 (Premium)", layout="wide")

# ==========================================
# [핵심 기능] 티커 정리 및 한국 주식 판별
# ==========================================
def clean_ticker(ticker):
    """티커의 공백 제거 및 대문자 변환"""
    if not ticker: return ""
    return ticker.strip().upper()

def is_korean_stock(ticker):
    """한국 주식인지 판별"""
    t = clean_ticker(ticker)
    return t.endswith('.KS') or t.endswith('.KQ')

# ==========================================
# [기능 1] 가격 포맷팅 함수
# ==========================================
def format_price(price, ticker):
    if pd.isna(price) or price is None: return "-"
    if is_korean_stock(ticker):
        rounded_price = int(round(price / 50) * 50)
        return f"{rounded_price:,}원"
    else:
        return f"${price:,.2f}"

def round_price_if_korean(price, ticker):
    if is_korean_stock(ticker):
        return round(price / 50) * 50
    return price

# ==========================================
# [기능 2] 메모장 관리 함수
# ==========================================
MEMO_FILE = "memos.txt"
def load_memos():
    if not os.path.exists(MEMO_FILE): return []
    try:
        with open(MEMO_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except: return []

def save_memo(memo):
    try:
        with open(MEMO_FILE, "a", encoding="utf-8") as f: f.write(memo + "\n")
        return True
    except: return False

def delete_memo(index):
    memos = load_memos()
    if 0 <= index < len(memos):
        del memos[index]
        try:
            with open(MEMO_FILE, "w", encoding="utf-8") as f:
                for m in memos: f.write(m + "\n")
            return True
        except: return False
    return False

# ==========================================
# [기능 3] 데이터 수집 함수 (Fast MFI 적용)
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker, days):
    try:
        ticker = clean_ticker(ticker)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 100)
        
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        if data.empty:
            return pd.DataFrame()

        # ------------------------------------------
        # 기술적 지표 계산
        # ------------------------------------------
        df = data.copy()
        
        # 1. 이동평균선
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        # 2. 볼린저 밴드
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        std = df['Close'].rolling(window=20).std()
        df['BB_Up'] = df['BB_Mid'] + (std * 2)
        df['BB_Low'] = df['BB_Mid'] - (std * 2)
        
        # 3. RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # ---------------------------------------------------------
        # [수정됨] 4. Fast MFI (기간 10일)
        # ---------------------------------------------------------
        mfi_period = 10 # 기존 14일 -> 10일로 단축 (민감도 Up)
        
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        money_flow = typical_price * df['Volume']
        
        pos_flow = np.where(typical_price > typical_price.shift(1), money_flow, 0)
        neg_flow = np.where(typical_price < typical_price.shift(1), money_flow, 0)
        
        pos_mf = pd.Series(pos_flow, index=df.index).rolling(window=mfi_period).sum()
        neg_mf = pd.Series(neg_flow, index=df.index).rolling(window=mfi_period).sum()
        
        mfi_ratio = pos_mf / neg_mf.replace(0, np.nan) 
        df['MFI'] = 100 - (100 / (1 + mfi_ratio))

        # 5. 변동성 돌파 전략
        k = 0.5
        df['Prev_Range'] = (df['High'].shift(1) - df['Low'].shift(1))
        df['Vol_Breakout_Price'] = df['Open'] + (df['Prev_Range'] * k)
        
        return df.iloc[-days:]
        
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# 사이드바 UI
# ==========================================
st.sidebar.header("🔍 종목 검색")
raw_ticker = st.sidebar.text_input("티커 입력", value="005930.KS")
ticker = clean_ticker(raw_ticker)
days = st.sidebar.slider("차트 조회 기간", 30, 730, 90)

if ticker:
    if is_korean_stock(ticker):
        st.sidebar.success(f"🇰🇷 한국 주식 ({ticker})")
    else:
        st.sidebar.warning(f"🇺🇸 미국/해외 주식 ({ticker})")

st.sidebar.markdown("---")
st.sidebar.subheader("📝 메모장")
new_memo = st.sidebar.text_input("메모 입력", key="new_memo")
if st.sidebar.button("저장"):
    if new_memo:
        save_memo(new_memo)
        st.rerun()

memos = load_memos()
if memos:
    st.sidebar.markdown("---")
    for i, m in enumerate(memos):
        c1, c2 = st.sidebar.columns([0.8, 0.2])
        c1.text(f"• {m}")
        if c2.button("X", key=f"d_{i}"):
            delete_memo(i)
            st.rerun()

# ==========================================
# 메인 화면
# ==========================================
st.title(f"📈 {ticker} 분석")

with st.spinner("데이터 분석 중..."):
    df = get_stock_data(ticker, days)

if df.empty:
    st.error(f"❌ '{ticker}' 데이터를 가져올 수 없습니다.")
    st.info(f"시스템 기준 오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}")
else:
    last_close = float(df['Close'].iloc[-1])
    
    # ----------------------------------
    # 가격 및 지표 계산 (반올림 적용)
    # ----------------------------------
    ma5_rounded = round_price_if_korean(df['MA5'].iloc[-1], ticker)
    ma10_rounded = round_price_if_korean(df['MA10'].iloc[-1], ticker)
    ma20_rounded = round_price_if_korean(df['MA20'].iloc[-1], ticker)
    bb_upper_rounded = round_price_if_korean(df['BB_Up'].iloc[-1], ticker)
    bb_lower_rounded = round_price_if_korean(df['BB_Low'].iloc[-1], ticker)
    
    val_def_entry = round_price_if_korean(df['MA20'].iloc[-1] * 0.95, ticker)
    val_sell_2 = round_price_if_korean(df['BB_Up'].iloc[-1] * 1.05, ticker)
    
    # 퀀트 지표 값
    vol_breakout_target = round_price_if_korean(df['Vol_Breakout_Price'].iloc[-1], ticker)
    last_mfi = df['MFI'].iloc[-1]
    
    # 공격형 진입가 (현재가)
    val_atk_entry = round_price_if_korean(last_close, ticker)
    # 공격형 슈팅가 (3%)
    val_atk_target = round_price_if_korean(last_close * 1.03, ticker)

    # 탭 구성
    tab1, tab2 = st.tabs(["📊 차트 분석", "📋 최근 데이터"])

    # ==========================================
    # Tab 1: 메인 차트
    # ==========================================
    with tab1:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.05,
                            subplot_titles=("주가 & 전략 타점", "거래량", "RSI"))
        
        # 1. 주가 & 밴드
        fig.add_trace(go.Scatter(x=list(df.index)+list(df.index[::-1]), y=list(df['BB_Up'])+list(df['BB_Low'][::-1]),
                                 fill='toself', fillcolor='rgba(128,128,128,0.1)', line=dict(width=0), showlegend=False), row=1, col=1)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='주가'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='blue', width=1), name='MA5'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], line=dict(color='#FFD700', width=1, dash='dot'), name='MA10'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1), name='MA20'), row=1, col=1)

        # 전략 가로선
        hlines = [
            (ma10_rounded, "blue", "solid", 3, "🌊 일반형 눌림목"),
            (bb_upper_rounded, "red", "solid", 3, "🔥 공격형 돌파"),
            (val_def_entry, "green", "solid", 3, "🛡️ 보수형 투매"),
            (val_sell_2, "gold", "dash", 2, "🚀 2차 목표"),
            (ma20_rounded, "gray", "dot", 2, "🛑 손절선")
        ]
        
        for val, col, dash, width, txt in hlines:
            txt_fmt = f"{txt} ({format_price(val, ticker)})"
            fig.add_hline(y=val, line_dash=dash, line_color=col, line_width=width,
                          annotation_text=txt_fmt, 
                          annotation_position="bottom", 
                          annotation=dict(x=0.5, xanchor='center'), 
                          row=1, col=1)

        # 2. 거래량
        colors = ['red' if r.Open <= r.Close else 'blue' for i, r in df.iterrows()]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

        # 3. RSI
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
        fig.add_hline(y=70, line_color='red', line_dash='dash', row=3, col=1)
        fig.add_hline(y=30, line_color='blue', line_dash='dash', row=3, col=1)

        fig.update_layout(height=800, xaxis_rangeslider_visible=False, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        currency_text = "원화" if is_korean_stock(ticker) else "달러"

        # -------------------------------------------------------------
        # 퀀트 & 스마트머니 전략 카드 (설명 상세화)
        # -------------------------------------------------------------
        st.subheader(f"🤖 AI 퀀트 & 스마트머니 전략 ({currency_text})")
        
        q1, q2, q3 = st.columns(3)
        
        # 1. 변동성 돌파
        with q1:
            st.markdown("**⚡ 변동성 돌파 (단타)**") 
            
            if last_close >= df['Vol_Breakout_Price'].iloc[-1]:
                 st.success(f"**🔥 매수 체결 신호!**\n\n현재가가 목표가를 돌파했습니다.\nTarget: {format_price(vol_breakout_target, ticker)}")
            else:
                 st.info(f"**⏳ 매수 대기 중**\n\n오늘 이 가격 넘으면 진입하세요.\nTarget: {format_price(vol_breakout_target, ticker)}")
        
        # 2. 스마트머니 (MFI) - [수정됨] 고감도 설정 (75/25) 및 중립 세분화
        with q2:
            st.markdown(f"**🌊 스마트머니 (Fast MFI 10일)**") 
            
            mfi_val = f"{last_mfi:.1f}" if not np.isnan(last_mfi) else "데이터 부족"
            
            if np.isnan(last_mfi):
                st.warning("**⚠️ 계산 불가**\n\n거래량 데이터가 없거나 부족합니다.")
            elif last_mfi >= 75: # 기준 80->75 완화
                st.error(f"**⚠️ 과열권 (매도 우위)**\n\n단기 고점일 수 있습니다.\nMFI: {mfi_val}")
            elif last_mfi <= 25: # 기준 20->25 완화
                st.success(f"**💎 침체권 (매집 찬스)**\n\n단기 저점일 수 있습니다.\nMFI: {mfi_val}")
            elif last_mfi >= 50: # 중립 상단
                st.write(f"**↗️ 매수세 유입 중**\n\n자금이 들어오고 있습니다.\nMFI: {mfi_val}")
            else: # 중립 하단
                st.write(f"**↘️ 매도세 우위**\n\n자금이 빠져나가고 있습니다.\nMFI: {mfi_val}")

        # 3. 추세 판단
        with q3:
            st.markdown("**🛡️ 추세 판단 (MA+MFI)**") 
            
            is_uptrend = df['Close'].iloc[-1] > df['MA20'].iloc[-1]
            has_momentum = last_mfi > 40 if not np.isnan(last_mfi) else False
            
            if is_uptrend and has_momentum:
                 st.success(f"**📈 상승 추세 (Strong)**\n\n추세가 살아있습니다.\n홀딩 추천")
            elif not is_uptrend:
                 st.warning(f"**📉 하락 추세 (Weak)**\n\n리스크 관리가 필요합니다.")
            else:
                 st.info(f"**🐢 방향성 탐색 중**\n\n주가가 20일선 위에 있지만 상승 힘(거래량)이 부족합니다.")

        st.markdown("---")
        
        # -------------------------------------------------------------
        # 기존 3-Scenario 전략
        # -------------------------------------------------------------
        st.markdown("#### 🔻 기존 고전 전략 (일반/공격/보수)") 
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.info(f"**🌊 일반형**\n\n1. 정찰: {format_price(last_close, ticker)}\n2. 불타기: {format_price(ma5_rounded, ticker)}\n3. 눌림목: {format_price(ma10_rounded, ticker)}")
        with c2:
            st.error(f"**🔥 공격형**\n\n1. 즉시: {format_price(val_atk_entry, ticker)}\n2. 돌파: {format_price(bb_upper_rounded, ticker)}\n3. 슈팅: {format_price(val_atk_target, ticker)}")
        with c3:
            st.success(f"**🛡️ 보수형**\n\n1. 생명선: {format_price(ma20_rounded, ticker)}\n2. 투매: {format_price(val_def_entry, ticker)}\n3. 과매도: {format_price(bb_lower_rounded, ticker)}")

    # ==========================================
    # Tab 2: 데이터
    # ==========================================
    with tab2:
        st.subheader(f"🗓️ 최근 {days}일 데이터")
        fmt = "{:,.0f}" if is_korean_stock(ticker) else "{:,.2f}"
        st.dataframe(df[['Open','High','Low','Close','Volume', 'MFI']].sort_index(ascending=False), use_container_width=True)