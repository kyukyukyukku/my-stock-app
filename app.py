import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# [핵심] 한국 주식 데이터 라이브러리 (설치 필요: py -m pip install pykrx)
try:
    from pykrx import stock
    HAS_PYKRX = True
except ImportError:
    HAS_PYKRX = False

# 1. 페이지 설정
st.set_page_config(page_title="내 손안의 주식 앱", layout="wide")

# ==========================================
# [기능 1] 가격 포맷팅 함수 (원화 vs 달러)
# ==========================================
def format_price(price, ticker):
    """
    한국 주식(.KS, .KQ)은 50원 단위 반올림 + '원'
    미국 주식은 소수점 2자리 + '$'
    """
    if pd.isna(price):
        return "-"
        
    if ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'):
        # 50원 단위 반올림
        rounded_price = round(price / 50) * 50
        return f"{int(rounded_price):,}원"
    else:
        # 미국 주식 (달러)
        return f"${price:,.2f}"

# ==========================================
# [기능 2] 메모장 관리 함수
# ==========================================
MEMO_FILE = "memos.txt"

def load_memos():
    if not os.path.exists(MEMO_FILE):
        return []
    with open(MEMO_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def save_memo(memo):
    with open(MEMO_FILE, "a", encoding="utf-8") as f:
        f.write(memo + "\n")

def delete_memo(index):
    memos = load_memos()
    if 0 <= index < len(memos):
        del memos[index]
        with open(MEMO_FILE, "w", encoding="utf-8") as f:
            for m in memos:
                f.write(m + "\n")

# ==========================================

# 2. 사이드바: 종목 및 기간 입력
st.sidebar.header("🔍 종목 검색")
ticker = st.sidebar.text_input("티커 입력", value="005930.KS") # 기본값 삼성전자
days = st.sidebar.slider("차트 조회 기간 (일)", min_value=30, max_value=730, value=90)

# --- 사이드바 메모장 UI ---
st.sidebar.markdown("---")
st.sidebar.subheader("📝 내 메모장")
new_memo = st.sidebar.text_input("메모 입력", placeholder="종목코드 메모")
if st.sidebar.button("메모 저장"):
    if new_memo:
        save_memo(new_memo)
        st.success("저장됨!")
        st.rerun()

st.sidebar.markdown("---")
memos = load_memos()
if memos:
    st.sidebar.caption(f"총 {len(memos)}개의 메모")
    for i, memo in enumerate(memos):
        col_memo, col_del = st.sidebar.columns([0.8, 0.2])
        col_memo.text(f"• {memo}")
        if col_del.button("X", key=f"del_{i}"):
            delete_memo(i)
            st.rerun()

# ==========================================
# 3. 데이터 가져오기 (캐싱 적용)
# ==========================================
@st.cache_data
def get_data(ticker, days):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data

@st.cache_data
def get_investor_data(ticker, days):
    """pykrx를 이용해 수급 데이터 가져오기"""
    if not HAS_PYKRX:
        return None
        
    # 티커 정리 (005930.KS -> 005930)
    code = ticker.split('.')[0] 
    
    end_date = datetime.today().strftime("%Y%m%d")
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")
    
    try:
        # 일별 거래실적 (순매수)
        df = stock.get_market_trading_volume_by_date(start_date, end_date, code)
        
        # 필요한 컬럼만 선택 및 누적합 계산
        cols = ['개인', '외국인', '기관합계']
        if not all(col in df.columns for col in cols):
             return None
             
        df_cumsum = df[cols].cumsum() # 누적 순매수로 변환
        return df_cumsum
    except:
        return None

# ==========================================
# 메인 화면 구성
# ==========================================
st.title(f"📈 {ticker} 주가 분석")

try:
    with st.spinner('데이터를 불러오는 중...'):
        df = get_data(ticker, days)

    if df.empty:
        st.error("❌ 데이터를 찾을 수 없습니다. 티커를 확인해주세요.")
    else:
        # 지표 계산
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 탭 구성 (3개)
        tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "📋 최근 데이터", "💰 수급 분석"])

        # -------------------------------------------------------
        # TAB 1: 차트 분석
        # -------------------------------------------------------
        with tab1:
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])

            # 1. 주가
            fig.add_trace(go.Scatter(x=list(df.index)+list(df.index[::-1]), y=list(df['BB_Upper'])+list(df['BB_Lower'][::-1]),
                fill='toself', fillcolor='rgba(128,128,128,0.1)', line=dict(width=0), showlegend=False), row=1, col=1)
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='주가'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='blue', width=2), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=2), name='MA20'), row=1, col=1)

            # 2. 거래량
            colors = ['red' if r['Open'] <= r['Close'] else 'blue' for i, r in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

            # 3. RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1), name='RSI'), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="blue", row=3, col=1)

            fig.update_layout(height=800, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

            # 매매 타점 계산 (format_price 적용)
            last_close = float(df['Close'].iloc[-1])
            last_ma5 = float(df['MA5'].iloc[-1])
            last_ma10 = float(df['MA10'].iloc[-1])
            last_ma20 = float(df['MA20'].iloc[-1])
            last_bb_upper = float(df['BB_Upper'].iloc[-1])
            last_bb_lower = float(df['BB_Lower'].iloc[-1])

            st.write("---")
            st.markdown(f"### 🎯 3-Scenario AI 매수 전략 ({'원화/50원 단위' if '원' in format_price(last_close, ticker) else '달러'})")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.info(f"**🌊 일반형**\n\n"
                        f"1. 정찰: {format_price(last_close, ticker)}\n"
                        f"2. 불타기: {format_price(last_ma5, ticker)}\n"
                        f"3. 눌림목: {format_price(last_ma10, ticker)}")
            with c2:
                st.error(f"**🔥 공격형**\n\n"
                         f"1. 즉시: {format_price(last_close, ticker)}\n"
                         f"2. 돌파: {format_price(last_bb_upper, ticker)}\n"
                         f"3. 슈팅: {format_price(last_close*1.03, ticker)}")
            with c3:
                st.success(f"**🛡️ 보수형**\n\n"
                           f"1. 생명선: {format_price(last_ma20, ticker)}\n"
                           f"2. 투매: {format_price(last_ma20*0.95, ticker)}\n"
                           f"3. 과매도: {format_price(last_bb_lower, ticker)}")
            
            # 매도 시나리오
            st.markdown("### 📉 AI 매도/청산 시나리오")
            st.warning(f"**🎯 1차 저항:** {format_price(last_bb_upper, ticker)}  |  "
                       f"**🚀 2차 슈팅:** {format_price(last_bb_upper*1.05, ticker)}  |  "
                       f"**🛑 손절선:** {format_price(last_ma20, ticker)}")

        # -------------------------------------------------------
        # TAB 2: 최근 데이터
        # -------------------------------------------------------
        with tab2:
            st.subheader("🗓️ 최근 데이터")
            three_months = df[df.index >= (datetime.now() - timedelta(days=90))].sort_index(ascending=False)
            
            # 데이터프레임 표시 포맷 (한국: 정수, 미국: 소수점)
            if '원' in format_price(last_close, ticker):
                st.dataframe(three_months[['Open','High','Low','Close','Volume']].style.format("{:,.0f}"), use_container_width=True)
            else:
                st.dataframe(three_months[['Open','High','Low','Close','Volume']].style.format("{:,.2f}"), use_container_width=True)

        # -------------------------------------------------------
        # TAB 3: 수급 분석 (NEW!)
        # -------------------------------------------------------
        with tab3:
            st.subheader("💰 투자자별 누적 순매수 추이 (최근 90일)")
            
            if ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ'):
                if not HAS_PYKRX:
                    st.error("⚠️ pykrx 라이브러리가 설치되지 않았습니다. (터미널에 `py -m pip install pykrx` 입력)")
                else:
                    with st.spinner("수급 데이터를 분석 중입니다..."):
                        # 수급 데이터 조회 (항상 최근 90일 기준)
                        df_investor = get_investor_data(ticker, days=90)
                    
                    if df_investor is not None and not df_investor.empty:
                        # 선 그래프 그리기
                        fig_inv = go.Figure()
                        fig_inv.add_trace(go.Scatter(x=df_investor.index, y=df_investor['개인'], name='개인', line=dict(color='green')))
                        fig_inv.add_trace(go.Scatter(x=df_investor.index, y=df_investor['외국인'], name='외국인', line=dict(color='red')))
                        fig_inv.add_trace(go.Scatter(x=df_investor.index, y=df_investor['기관합계'], name='기관', line=dict(color='blue')))
                        
                        fig_inv.update_layout(title=f"{ticker} 누적 수급 현황", xaxis_title="날짜", yaxis_title="누적 순매수량", height=500)
                        st.plotly_chart(fig_inv, use_container_width=True)
                        
                        st.caption("※ 빨간선(외국인)과 파란선(기관)이 우상향할수록 수급이 좋은 종목입니다.")
                    else:
                        st.info("데이터를 가져올 수 없습니다. (장 시작 전이거나 데이터 오류)")
            else:
                st.warning("🚫 미국 주식 및 해외 주식은 상세 수급 데이터를 제공하지 않습니다.")

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")