import sys
import os

# [강제 설정] 현재 파일(app.py)이 있는 위치를 라이브러리 검색 경로 1순위로 등록
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import requests
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from fredapi import Fred
from pykrx import stock
import pytz
import os
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module='pykrx')
import streamlit as st

# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(page_title="내 손안의 주식 앱 (Premium)", layout="wide")

# ==========================================
# [공통 함수] 유틸리티
# ==========================================
def clean_ticker(ticker):
    if not ticker: return ""
    return ticker.strip().upper()

def is_korean_stock(ticker):
    t = clean_ticker(ticker)
    return t.endswith('.KS') or t.endswith('.KQ')

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
# [기능 1] 메모장
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

@st.cache_data
def convert_df(df):
    # 1. 인덱스(날짜)를 일반 컬럼으로 변환 (엑셀에서 보기 편하게)
    output = df.reset_index()
    # 2. 한글 깨짐 방지를 위해 'utf-8-sig' 인코딩 사용
    return output.to_csv(index=False).encode('utf-8-sig')

# ==========================================
# [기능 2] 데이터 수집 함수 (pykrx + yfinance 통합 엔진)
# ==========================================
@st.cache_data(ttl=3600)
def get_stock_data(ticker, days=365):
    try:
        ticker = clean_ticker(ticker)
        
        # 날짜 설정
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=days + 100) # 이동평균선 계산용 여유분
        
        start_str_y = start_dt.strftime('%Y-%m-%d')
        end_str_y = end_dt.strftime('%Y-%m-%d')
        
        start_str_k = start_dt.strftime('%Y%m%d')
        end_str_k = end_dt.strftime('%Y%m%d')

        # -----------------------------------------------------------
        # 1. 한국 주식 (숫자로 된 6자리 티커) -> pykrx 사용 (데이터 끝판왕)
        # -----------------------------------------------------------
        if ticker.isdigit() and len(ticker) == 6:
            # pykrx로 OHLCV 가져오기
            df = stock.get_market_ohlcv_by_date(start_str_k, end_str_k, ticker)
            
            # 컬럼명을 영문으로 통일 (yfinance 포맷과 맞추기 위해)
            df = df.rename(columns={
                '시가': 'Open', '고가': 'High', '저가': 'Low', 
                '종가': 'Close', '거래량': 'Volume'
            })
            df.index.name = 'Date'
            
            # pykrx는 가끔 0인 데이터가 올 수 있어 처리
            df = df[df['Open'] > 0]

        # -----------------------------------------------------------
        # 2. 한국/일본 국채, 코스피 선물 -> Investing.com (FDR)
        # -----------------------------------------------------------
        elif ticker in ['KR10YT=RR', 'JP10YT=XX', 'FKS200']:
            target_ticker = f"INVESTING:{ticker}"
            df = fdr.DataReader(target_ticker, start_str_y, end_str_y)

        # -----------------------------------------------------------
        # 3. 환율 (FDR 사용이 더 안정적)
        # -----------------------------------------------------------
        elif ticker in ['USD/KRW', 'JPY/KRW']:
            df = fdr.DataReader(ticker, start_str_y)

        # -----------------------------------------------------------
        # 4. 미국 주식 / 지수 / 원자재 -> yfinance
        # -----------------------------------------------------------
        else:
            # .KS .KQ가 붙어있으면 떼고 pykrx로 보내는게 좋음 (재귀 호출)
            if ticker.endswith('.KS') or ticker.endswith('.KQ'):
                pure_ticker = ticker.split('.')[0]
                if pure_ticker.isdigit():
                    # 재귀적으로 자기 자신을 호출하여 pykrx 로직을 타게 함
                    return get_stock_data(pure_ticker, days)
            
            # 진짜 해외 주식/지수
            data = yf.download(ticker, start=start_str_y, end=end_str_y, progress=False)
            if isinstance(data.columns, pd.MultiIndex): 
                data.columns = data.columns.get_level_values(0)
            df = data

        if df.empty: return pd.DataFrame()

        # ------------------------------------------
        # 기술적 지표 계산 (공통 로직)
        # ------------------------------------------
        df = df.copy() # 원본 보존
        
        # 이동평균선
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA10'] = df['Close'].rolling(10).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        
        # 볼린저 밴드
        df['BB_Mid'] = df['Close'].rolling(20).mean()
        std = df['Close'].rolling(20).std()
        df['BB_Up'] = df['BB_Mid'] + (std * 2)
        df['BB_Low'] = df['BB_Mid'] - (std * 2)
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # MFI (자금 흐름)
        mfi_period = 10
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        
        if 'Volume' in df.columns:
            vol = df['Volume'].replace(0, np.nan).fillna(0)
            if vol.sum() == 0:
                 df['MFI'] = 50
            else:
                mf = tp * vol
                pos = np.where(tp > tp.shift(1), mf, 0)
                neg = np.where(tp < tp.shift(1), mf, 0)
                pmf = pd.Series(pos, index=df.index).rolling(mfi_period).sum()
                nmf = pd.Series(neg, index=df.index).rolling(mfi_period).sum()
                mr = pmf / nmf.replace(0, np.nan)
                df['MFI'] = 100 - (100 / (1 + mr))
        else:
            df['MFI'] = 50

        # 변동성 돌파 타겟
        k = 0.5
        df['Prev_Range'] = (df['High'].shift(1) - df['Low'].shift(1))
        df['Vol_Breakout_Price'] = df['Open'] + (df['Prev_Range'] * k)
        
        # 요청한 기간만큼 자르기
        return df.iloc[-days:]
        
    except Exception as e:
        print(f"Data Load Error ({ticker}): {e}")
        return pd.DataFrame()
# ==========================================
# [기능 3] 하이일드 스프레드 (FRED API - 강력한 데이터 정제 추가)
# ==========================================
@st.cache_data(ttl=21600)
def get_high_yield_spread():
    try:
        fred = Fred(api_key='c7ece8054e786f8553b38e7585ae689a')
        
        # 최근 90일 데이터
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        series = fred.get_series('BAMLH0A0HYM2', observation_start=start_date)
        
        if series is None or series.empty:
            return pd.DataFrame()

        df = pd.DataFrame(series, columns=['Spread'])
        df.index.name = 'Date'
        
        # [핵심 방어 코드] 문자열이 섞여있으면 강제로 숫자로 변환 (에러는 NaN 처리)
        df['Spread'] = pd.to_numeric(df['Spread'], errors='coerce')
        
        # NaN(결측치) 제거
        df = df.dropna()
        
        # 날짜순 정렬
        df = df.sort_index()
        
        return df
    except Exception as e:
        print(f"FRED Error: {e}")
        return pd.DataFrame()

def analyze_market_risk(current_spread, prev_spread_1week_ago):
    """
    하이일드 스프레드 위험도 판별 (안전 장치 포함)
    """
    # 데이터 유효성 검사 (None, NaN 방지)
    try:
        current_spread = float(current_spread)
        prev_spread_1week_ago = float(prev_spread_1week_ago)
    except:
        return "UNKNOWN", "데이터 확인 불가", "#eeeeee"

    if pd.isna(current_spread) or pd.isna(prev_spread_1week_ago):
        return "UNKNOWN", "데이터 확인 불가", "#eeeeee"

    # 1. 절대 레벨 체크
    if current_spread > 4.0:
        return "RISK_ON", "🚨 RISK_ON: <br>경기 침체 공포 확산 중 (주식 비중 축소)", "#ffcdd2"
        
    # 2. 변화량 체크
    change = current_spread - prev_spread_1week_ago
    
    if current_spread < 3.0:
        if change >= 0.2:
            return "CAUTION", "⚠️ CAUTION: <br>안전 지대 이탈 조짐 (신용 경색 주의)", "#fff9c4"
        else:
            return "RISK_OFF", "✅ RISK_OFF: <br>유동성 풍부, 적극 투자 구간", "#c8e6c9"
    else:
        if change >= 0.15:
            return "CAUTION", "⚠️ CAUTION: <br>위험 신호 감지", "#fff9c4"
        else:
            return "NEUTRAL", "🐢 NEUTRAL: <br>시장 관망 필요", "#e0f7fa"

# ==========================================
# [기능 4] 투자자별 수급 (최종 완성: 순매수 + 백만원 단위 + 상세항목)
# ==========================================
@st.cache_data(ttl=21600)
def get_investor_trend(ticker, days=30):
    # 1. 티커 정리
    if "." in ticker: 
        ticker = ticker.split(".")[0]
    
    # 2. 날짜 설정
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")
    
    try:
        # 3. 데이터 조회 (순매수 + 상세 데이터)
        df = stock.get_market_trading_value_by_date(
            start_str, 
            end_str, 
            ticker, 
            detail=True,   # 연기금, 사모, 투신 등 상세 항목 모두 가져오기
            on="순매수"    # 다시 '순매수'로 복귀
        )
        
        if df is None or df.empty:
            return pd.DataFrame()
            
        # 4. [핵심] 단위 변환 (원 -> 백만 원) 및 반올림
        # 숫자가 너무 길어서 보기 힘들므로 100만으로 나눕니다.
        df = df.div(1000000).round(0) 
        
        # 5. 불필요한 '전체' 컬럼 제거
        # (순매수 총합은 0에 가까워서 차트 왜곡을 일으킬 수 있음)
        if '전체' in df.columns:
            df = df.drop(columns=['전체'])

        # 6. 보기 좋게 컬럼 순서 정렬 (주요 주체 먼저)
        # 데이터에 있는 컬럼만 선택해서 정렬
        priority_cols = ['개인', '외국인', '기관합계', '연기금', '투신', '사모', '금융투자', '보험', '은행', '기타금융', '기타법인']
        # 실제 데이터에 존재하는 컬럼만 남기기 (에러 방지)
        existing_cols = [c for c in priority_cols if c in df.columns]
        # 나머지 컬럼들(혹시 있다면) 뒤에 붙이기
        remaining_cols = [c for c in df.columns if c not in existing_cols]
        
        df = df[existing_cols + remaining_cols]
        
        # 7. 날짜 인덱스 정리 (최신순)
        df.index.name = 'Date'
        df = df.sort_index(ascending=False)
        
        return df

    except Exception as e:
        print(f"Investor Trend Error: {e}") 
        return pd.DataFrame()

# ==========================================
# 사이드바 UI
# ==========================================
st.sidebar.header("🔍 분석 모드 선택")
analysis_mode = st.sidebar.radio("모드 선택", ["개별 종목 분석", "🌏 글로벌 증시 & 매크로"])

ticker = ""
days = 90

if analysis_mode == "개별 종목 분석":
    raw_ticker = st.sidebar.text_input("티커 입력", value="005930.KS", key="ticker_input")
    ticker = clean_ticker(raw_ticker)
    days = st.sidebar.slider("차트 조회 기간", 30, 730, 90)
    
    if ticker:
        if is_korean_stock(ticker):
            st.sidebar.success(f"🇰🇷 한국 주식 ({ticker})")
        else:
            st.sidebar.warning(f"🇺🇸 미국/해외 주식 ({ticker})")

elif analysis_mode == "🌏 글로벌 증시 & 매크로":
    st.sidebar.info("💡 주요 증시, 환율, 금리, 원자재를\n한눈에 확인합니다.")

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
# 메인 화면: 글로벌 증시 & 매크로
# ==========================================
if analysis_mode == "🌏 글로벌 증시 & 매크로":
    korea_tz = pytz.timezone('Asia/Seoul')
    now_str = datetime.now(korea_tz).strftime("%Y-%m-%d %H:%M")
    
    st.markdown(f"### 🌏 글로벌 주요 증시 & 매크로 지표 <span style='font-size:14px; color:gray; font-weight:normal'>({now_str})</span>", unsafe_allow_html=True)
    
    indices = {
        "🇰🇷 코스피": "^KS11",
        "🇰🇷 코스닥": "^KQ11",
        "📉 공포 지수 (VIX)": "^VIX", 
        "🇺🇸 S&P 500": "^GSPC",
        "🇺🇸 나스닥": "^IXIC",
        "🇺🇸 러셀 2000": "^RUT",      
        "🇯🇵 닛케이": "^N225",
        "💵 환율 (USD/KRW)": "USD/KRW",   
        "💴 환율 (JPY/KRW)": "JPY/KRW",   
        "🇺🇸 미 국채 10년물": "^TNX",      
        "🇰🇷 한국 국채 10년": "KR10YT=RR",  
        "🇯🇵 일본 국채 10년": "JP10YT=XX"   
    }
    
    col1, col2, col3 = st.columns(3)
    cols = [col1, col2, col3]
    
    # -------------------------------------
    # 1. 상단: 기존 지표 그리드
    # -------------------------------------
    with st.spinner("글로벌 데이터 수집 중 (Yahoo + Investing.com)..."):
        for i, (name, sym) in enumerate(indices.items()):
            df_idx = get_stock_data(sym, days=60)
            
            with cols[i % 3]:
                if not df_idx.empty:
                    last_val = df_idx['Close'].iloc[-1]
                    if len(df_idx) >= 2:
                        prev_val = df_idx['Close'].iloc[-2]
                        change = last_val - prev_val
                        pct_change = (change / prev_val) * 100
                    else:
                        pct_change = 0.0

                    color = "red" if pct_change > 0 else "blue"
                    
                    if "국채" in name: val_fmt = "{:.3f}%"
                    elif "JPY" in name: val_fmt = "{:,.2f}"
                    else: val_fmt = "{:,.2f}"

                    st.metric(label=name, value=val_fmt.format(last_val), delta=f"{pct_change:.2f}%")
                    
                    fig_mini = go.Figure()
                    fig_mini.add_trace(go.Scatter(x=df_idx.index, y=df_idx['Close'], mode='lines', line=dict(color=color, width=2)))
                    fig_mini.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0),
                        height=100,
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False),
                        showlegend=False
                    )
                    st.plotly_chart(fig_mini, width="stretch")
                else:
                    st.warning(f"{name}: 데이터 로딩 실패")

    st.markdown("---")

    # -------------------------------------
    # 2. 하단: 하이일드 스프레드 (튕김 방지 강화)
    # -------------------------------------
    st.subheader("🔥 미국 하이일드 스프레드 (Risk Signal)")
    
    # [핵심] 렌더링 전체를 try-except로 보호
    try:
        with st.spinner("FRED 데이터 분석 중..."):
            df_hy = get_high_yield_spread()
            
            # 데이터프레임이 비어있지 않고, 행이 1개 이상일 때만 실행
            if not df_hy.empty and len(df_hy) > 0:
                # 안전하게 값 추출 (float 변환 재확인)
                try:
                    current_spread = float(df_hy['Spread'].iloc[-1])
                    current_date = df_hy.index[-1].strftime('%Y-%m-%d')
                    
                    if len(df_hy) >= 5:
                        prev_spread = float(df_hy['Spread'].iloc[-5])
                        prev_date = df_hy.index[-5].strftime('%Y-%m-%d')
                    else:
                        prev_spread = current_spread
                        prev_date = current_date
                        
                    # 위험 분석
                    status_code, msg, bg_color = analyze_market_risk(current_spread, prev_spread)
                    
                    c1, c2 = st.columns([1, 2])
                    
                    with c1:
                        st.markdown(f"""
                        <div style="background-color:{bg_color}; padding:20px; border-radius:10px; border:1px solid #ddd; font-size:1rem; line-height:1.6;">
                            <div style="font-weight:bold; margin-bottom:10px;">📢 시장 위험도 분석</div>
                            <div style="font-weight:bold; margin-bottom:15px;">{msg}</div>
                            <div style="border-top:1px solid #ccc; margin:10px 0;"></div>
                            <div>현재 ({current_date}): <b>{current_spread:.2f}%</b></div>
                            <div style="color:#555;">1주전 ({prev_date}): {prev_spread:.2f}%</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    with c2:
                        fig_hy = go.Figure()
                        fig_hy.add_trace(go.Scatter(
                            x=df_hy.index, y=df_hy['Spread'],
                            mode='lines', name='Spread',
                            line=dict(color='#d32f2f', width=2)
                        ))
                        
                        fig_hy.add_hline(y=4.0, line_dash="dot", line_color="gray", annotation_text="위험 기준 (4.0%)")
                        fig_hy.add_hline(y=3.0, line_dash="dot", line_color="green", annotation_text="안전 기준 (3.0%)")
                        
                        fig_hy.update_layout(
                            title="US High Yield Spread (최근 90일)",
                            height=350,
                            margin=dict(l=20, r=20, t=40, b=20),
                            hovermode="x unified"
                        )
                        st.plotly_chart(fig_hy, width="stretch")
                        
                except ValueError as ve:
                    st.error(f"데이터 형식이 올바르지 않습니다: {ve}")
            else:
                st.warning("⚠️ 하이일드 스프레드 데이터가 없습니다. (FRED API 응답 지연)")
                
    except Exception as e:
        st.error(f"화면 표시 중 오류가 발생했습니다: {e}")

# ==========================================
# 메인 화면: 개별 종목 분석 모드
# ==========================================
else:
    korea_tz = pytz.timezone('Asia/Seoul')
    now_str = datetime.now(korea_tz).strftime("%Y-%m-%d %H:%M")
    
    st.markdown(f"### 📈 {ticker} 분석 <span style='font-size:14px; color:gray; font-weight:normal'>({now_str})</span>", unsafe_allow_html=True)

    with st.spinner("퀀트 데이터 분석 중..."):
        df = get_stock_data(ticker, days)

    if df.empty:
        st.error(f"❌ '{ticker}' 데이터를 찾을 수 없습니다.")
    else:
        last_close = float(df['Close'].iloc[-1])
        
        ma5 = round_price_if_korean(df['MA5'].iloc[-1], ticker)
        ma10 = round_price_if_korean(df['MA10'].iloc[-1], ticker)
        ma20 = round_price_if_korean(df['MA20'].iloc[-1], ticker)
        bb_up = round_price_if_korean(df['BB_Up'].iloc[-1], ticker)
        bb_low = round_price_if_korean(df['BB_Low'].iloc[-1], ticker)
        
        vol_target = round_price_if_korean(df['Vol_Breakout_Price'].iloc[-1], ticker)
        mfi = df['MFI'].iloc[-1]
        
        val_atk_entry = round_price_if_korean(last_close, ticker)
        val_atk_target = round_price_if_korean(last_close * 1.03, ticker)
        val_def_entry = round_price_if_korean(df['MA20'].iloc[-1] * 0.95, ticker)

        t1, t2, t3, t4 = st.tabs(["📊 차트 분석", "📋 가격 데이터", "📋 투자자별 상세(표)", "🏢 수급 차트"])

        with t1:
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.05)
            
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='주가'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Up'], line=dict(color='gray', dash='dot'), name='BB상단'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Low'], line=dict(color='gray', dash='dot'), name='BB하단'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='blue'), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], line=dict(color='#FFD700', dash='dot'), name='MA10'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='MA20'), row=1, col=1)

            lines = [
                (ma10, "blue", "solid", "🌊 눌림목"),
                (bb_up, "red", "solid", "🔥 돌파"),
                (val_def_entry, "green", "solid", "🛡️ 투매"),
                (ma20, "gray", "dot", "🛑 손절")
            ]
            for val, col, dash, txt in lines:
                fig.add_hline(y=val, line_dash=dash, line_color=col, 
                              annotation_text=f"{txt} ({format_price(val, ticker)})",
                              annotation_position="top",
                              annotation=dict(x=0.5, xanchor='center'),
                              row=1, col=1)

            clrs = ['red' if r.Open <= r.Close else 'blue' for i, r in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=clrs, name='거래량'), row=2, col=1)

            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name='RSI'), row=3, col=1)
            fig.add_hline(y=70, line_color='red', row=3, col=1)
            fig.add_hline(y=30, line_color='blue', row=3, col=1)

            fig.update_layout(height=800, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, width="stretch")

            currency = "원화" if is_korean_stock(ticker) else "달러"
            st.markdown("---")
            
            st.subheader(f"🤖 AI 퀀트 & 스마트머니 전략 ({currency})")
            
            q1, q2, q3 = st.columns(3)
            
            with q1:
                target_str = format_price(vol_target, ticker)
                if last_close >= df['Vol_Breakout_Price'].iloc[-1]:
                    html = f"""<div style="background-color:#f3e5f5;padding:15px;border-radius:10px;border:1px solid #ce93d8;">
                    <div style="color:#4a148c;margin:0 0 10px 0;font-weight:bold;font-size:1rem;">⚡ 변동성 돌파 (단타)</div>
                    <div style="color:#4a148c;font-weight:bold;">🔥 매수 체결 신호!</div>
                    <div style="color:#4a148c;font-size:0.9rem;">현재가가 목표가를 돌파했습니다.</div>
                    <div style="color:#4a148c;margin-top:5px;">Target: {target_str}</div></div>"""
                else:
                    html = f"""<div style="background-color:#f3e5f5;padding:15px;border-radius:10px;border:1px solid #ce93d8;">
                    <div style="color:#4a148c;margin:0 0 10px 0;font-weight:bold;font-size:1rem;">⚡ 변동성 돌파 (단타)</div>
                    <div style="color:#5e35b1;font-weight:bold;">⏳ 매수 대기 중</div>
                    <div style="color:#5e35b1;font-size:0.9rem;">오늘 이 가격 넘으면 진입하세요.</div>
                    <div style="color:#5e35b1;margin-top:5px;">Target: {target_str}</div></div>"""
                st.markdown(html, unsafe_allow_html=True)

            with q2:
                mfi_val = f"{mfi:.1f}" if not np.isnan(mfi) else "N/A"
                if np.isnan(mfi):
                    title, desc, color = "⚠️ 계산 불가", "데이터 부족", "#004d40"
                elif mfi >= 75:
                    title, desc, color = "⚠️ 과열권 (매도 우위)", "차익실현 주의", "#b71c1c"
                elif mfi <= 25:
                    title, desc, color = "💎 침체권 (매집 찬스)", "세력 매집 구간", "#004d40"
                elif mfi >= 50:
                    title, desc, color = "↗️ 매수세 유입 중", "자금이 꾸준히 들어오는 중", "#006064"
                else:
                    title, desc, color = "↘️ 매도세 우위", "자금이 빠져나가는 중", "#006064"
                
                html = f"""<div style="background-color:#e0f2f1;padding:15px;border-radius:10px;border:1px solid #80cbc4;">
                <div style="color:#004d40;margin:0 0 10px 0;font-weight:bold;font-size:1rem;">🌊 스마트머니 (Fast MFI)</div>
                <div style="color:{color};font-weight:bold;">{title}</div>
                <div style="color:#004d40;font-size:0.9rem;">{desc}</div>
                <div style="color:#004d40;margin-top:5px;">MFI Score: {mfi_val}</div></div>"""
                st.markdown(html, unsafe_allow_html=True)

            with q3:
                is_uptrend = last_close > ma20
                if is_uptrend and mfi > 40:
                    title, desc, color = "📈 상승 추세 (Strong)", "추세와 수급이 모두 좋습니다. 홀딩!", "#e65100"
                elif not is_uptrend:
                    title, desc, color = "📉 하락 추세 (Weak)", "리스크 관리가 필요한 구간입니다.", "#bf360c"
                else:
                    title, desc, color = "🐢 방향성 탐색 중", "상승 힘(거래량)이 아직 부족합니다.", "#f57f17"

                html = f"""<div style="background-color:#fff3e0;padding:15px;border-radius:10px;border:1px solid #ffcc80;">
                <div style="color:#e65100;margin:0 0 10px 0;font-weight:bold;font-size:1rem;">🛡️ 추세 판단 (MA+MFI)</div>
                <div style="color:{color};font-weight:bold;">{title}</div>
                <div style="color:#e65100;font-size:0.9rem;">{desc}</div></div>"""
                st.markdown(html, unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("#### 🔻 기존 고전 전략 (일반/공격/보수)")
            c1, c2, c3 = st.columns(3)
            with c1: 
                st.info(f"**🌊 일반형**\n\n"
                        f"- 정찰: {format_price(last_close, ticker)}\n"
                        f"- 불타기: {format_price(ma5, ticker)}\n"
                        f"- 눌림목: {format_price(ma10, ticker)}")
            with c2: 
                st.error(f"**🔥 공격형**\n\n"
                         f"- 즉시: {format_price(val_atk_entry, ticker)}\n"
                         f"- 돌파: {format_price(bb_up, ticker)}\n"
                         f"- 슈팅: {format_price(val_atk_target, ticker)}")
            with c3: 
                st.success(f"**🛡️ 보수형**\n\n"
                           f"- 생명선: {format_price(ma20, ticker)}\n"
                           f"- 투매: {format_price(val_def_entry, ticker)}\n"
                           f"- 과매도: {format_price(bb_low, ticker)}")

        with t2:
            st.subheader(f"📋 최근 {days}일 데이터")
            
            # 데이터프레임 표시
            st.dataframe(df.sort_index(ascending=False), width="stretch")
            
            # [수정] CSV 다운로드 버튼 기능 강화
            if not df.empty:
                csv = convert_df(df.sort_index(ascending=False))
                
                # 현재 날짜/시간으로 파일명 생성 (중복 방지)
                file_name = f"{ticker}_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                
                st.download_button(
                    label="📥 CSV 데이터 다운로드",
                    data=csv,
                    file_name=file_name,
                    mime='text/csv',
                    key='download-csv'
                )
        # [NEW] 투자자별 상세 데이터 (표 + 다운로드)
        with t3:
            st.subheader("📋 투자자별 매매동향 (최근 90일)")
            
            if is_korean_stock(ticker):
                with st.spinner("KRX 데이터 분석 중..."):
                    df_investor = get_investor_trend(ticker, days=90)
                    
                    if not df_investor.empty:
                        # 사용자 요청 컬럼 순서대로 정리
                        target_cols = ['개인', '외국인', '기관합계', '금융투자', '투신', '연기금', '프로그램']
                        # 실제 데이터에 있는 컬럼만 골라내기 (오류 방지)
                        valid_cols = [c for c in target_cols if c in df_investor.columns]
                        
                        df_table = df_investor[valid_cols].copy()
                        
                        # 1. 표 표시
                        st.dataframe(df_table, width="stretch", height=500)
                        
                        # 2. 다운로드 버튼
                        csv_inv = convert_df(df_table)
                        file_name_inv = f"{ticker}_investor_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                        st.download_button(
                            label="📥 투자자별 데이터 CSV 다운로드",
                            data=csv_inv,
                            file_name=file_name_inv,
                            mime='text/csv',
                            key='down-investor'
                        )
                    else:
                        st.warning("투자자별 데이터를 가져올 수 없습니다.")
            else:
                st.info("🚫 투자자별 수급 데이터는 한국 주식만 지원합니다.")

        # [NEW] 수급 차트 (기존 t3 -> t4 이동)
        with t4:
            st.subheader(f"📈 {ticker} 누적 수급 vs 주가 추세 (최근 90일)")
            
            if is_korean_stock(ticker):
                clean_ticker = ticker.split(".")[0]
                
                # -----------------------------------------------------------
                # 1. 수급 데이터 가져오기
                # -----------------------------------------------------------
                days = 90
                df_investor = get_investor_trend(clean_ticker, days=days)
                
                if not df_investor.empty:
                    # 5대 핵심 항목만 추출
                    target_cols = ['개인', '외국인', '연기금', '금융투자', '투신']
                    valid_cols = [c for c in target_cols if c in df_investor.columns]
                    
                    # 수급 데이터 누적(Cumsum) 계산
                    df_cumsum = df_investor[valid_cols].sort_index(ascending=True).cumsum()
                    
                    # -------------------------------------------------------
                    # 2. 주가 데이터 가져오기 (안전 모드)
                    # -------------------------------------------------------
                    df_price_aligned = pd.DataFrame()
                    try:
                        end_dt = datetime.now()
                        start_dt = end_dt - timedelta(days=days * 1.5)
                        
                        s_str = start_dt.strftime("%Y%m%d")
                        e_str = end_dt.strftime("%Y%m%d")
                        
                        df_price = stock.get_market_ohlcv_by_date(s_str, e_str, clean_ticker)
                        
                        if not df_price.empty:
                            df_cumsum.index = pd.to_datetime(df_cumsum.index)
                            df_price.index = pd.to_datetime(df_price.index)
                            
                            common_index = df_cumsum.index.intersection(df_price.index)
                            df_price_aligned = df_price.loc[common_index, ['종가']]
                            
                    except Exception as e:
                        pass

                    # -------------------------------------------------------
                    # 3. 그래프 그리기
                    # -------------------------------------------------------
                    fig_inv = go.Figure()
                    
                    colors = {
                        '개인': '#A9A9A9', '외국인': '#FF0000', '연기금': '#008000',
                        '금융투자': '#0000FF', '투신': '#FFA500'
                    }

                    # [왼쪽 축] 투자자별 누적 순매수
                    for col in valid_cols:
                        fig_inv.add_trace(go.Scatter(
                            x=df_cumsum.index, 
                            y=df_cumsum[col], 
                            mode='lines', 
                            name=col,
                            yaxis='y1',
                            line=dict(width=2, color=colors.get(col, 'gray'))
                        ))
                    
                    # [오른쪽 축] 주가
                    if not df_price_aligned.empty:
                        fig_inv.add_trace(go.Scatter(
                            x=df_price_aligned.index,
                            y=df_price_aligned['종가'],
                            mode='lines',
                            name='주가(종가)',
                            yaxis='y2',
                            line=dict(width=3, color='black', dash='dot'),
                            opacity=0.7
                        ))
                    
                    # -------------------------------------------------------
                    # [수정] 최신 문법으로 레이아웃 설정 (titlefont 제거 -> title dict 사용)
                    # -------------------------------------------------------
                    layout_opts = dict(
                        title=dict(text=f"투자자별 누적 수급 추이 (단위: 백만 원)"),
                        height=500,
                        hovermode="x unified",
                        legend=dict(orientation="h", y=1.02, x=1, xanchor="right"),
                        
                        # 왼쪽 Y축 설정 (수급)
                        yaxis=dict(
                            title=dict(text="누적 순매수", font=dict(color="#1f77b4")),
                            tickfont=dict(color="#1f77b4")
                        ),
                        xaxis=dict(tickformat="%m-%d")
                    )
                    
                    # 오른쪽 Y축 설정 (주가) - 데이터가 있을 때만
                    if not df_price_aligned.empty:
                        layout_opts['yaxis2'] = dict(
                            title=dict(text="주가 (원)", font=dict(color="black")),
                            tickfont=dict(color="black"),
                            overlaying="y",
                            side="right",
                            showgrid=False
                        )
                    
                    fig_inv.update_layout(**layout_opts)
                    fig_inv.add_hline(y=0, line_width=1, line_color="gray", opacity=0.5)
                    
                    st.plotly_chart(fig_inv, width="stretch")
                    
                    if df_price_aligned.empty:
                        st.caption("※ 현재 주가 데이터를 불러오지 못해 '수급 차트'만 표시되었습니다.")
                    else:
                        st.caption("💡 **Tip:** 검은 점선(주가)과 같이 움직이는 색깔(세력)을 찾으세요.")

                    with st.expander("📄 데이터 상세 보기"):
                        st.dataframe(df_investor[valid_cols].style.format("{:,.0f}"))
                
                else:
                    st.warning("수급 데이터를 불러오지 못했습니다.")
            else:
                st.info("🚫 투자자별 수급 차트는 한국 주식만 지원합니다.")