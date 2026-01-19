import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os

# 1. 페이지 설정
st.set_page_config(page_title="내 손안의 주식 앱", layout="wide")

# ==========================================
# [기능 유지] 메모장 관리 함수
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
ticker = st.sidebar.text_input("티커 입력 (예: 005930.KS, TSLA)", value="005930.KS")
days = st.sidebar.slider("차트 조회 기간 (일)", min_value=30, max_value=730, value=90)

# --- 사이드바 메모장 UI ---
st.sidebar.markdown("---")
st.sidebar.subheader("📝 내 메모장")
new_memo = st.sidebar.text_input("메모 입력", placeholder="예: 005930.KS 삼성")
if st.sidebar.button("메모 저장"):
    if new_memo:
        save_memo(new_memo)
        st.success("저장됨!")
        st.rerun()

st.sidebar.markdown("---")
memos = load_memos()
if memos:
    st.sidebar.caption(f"총 {len(memos)}개의 메모가 있습니다.")
    for i, memo in enumerate(memos):
        col_memo, col_del = st.sidebar.columns([0.8, 0.2])
        col_memo.text(f"• {memo}")
        if col_del.button("X", key=f"del_{i}"):
            delete_memo(i)
            st.rerun()
else:
    st.sidebar.info("저장된 메모가 없습니다.")

# ==========================================

# 3. 데이터 가져오기 함수
def get_data(ticker, days):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data

# [NEW] 50원 단위 반올림 함수
def round_to_50(price):
    return round(price / 50) * 50

# 메인 화면 구성
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

        tab1, tab2 = st.tabs(["📊 차트 분석", "📋 최근 데이터"])

        with tab1:
            # 3단 차트 (주가 / 거래량 / RSI)
            fig = make_subplots(
                rows=3, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.05, 
                row_heights=[0.6, 0.2, 0.2]
            )

            # 1. 주가 차트
            fig.add_trace(go.Scatter(x=list(df.index) + list(df.index[::-1]), y=list(df['BB_Upper']) + list(df['BB_Lower'][::-1]),
                fill='toself', fillcolor='rgba(128, 128, 128, 0.1)', line=dict(color='rgba(255,255,255,0)'),
                name='볼린저 밴드', showlegend=False, hoverinfo='skip'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB 상단'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), name='BB 하단'), row=1, col=1)

            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='주가'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='blue', width=2), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], line=dict(color='#FFD700', width=2, dash='dot'), name='MA10'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=2), name='MA20'), row=1, col=1)

            # 2. 거래량 차트
            colors = ['red' if row['Open'] <= row['Close'] else 'blue' for index, row in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

            # 3. RSI 차트
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1), name='RSI'), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="blue", row=3, col=1)

            fig.update_layout(xaxis_rangeslider_visible=False, height=800, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # --- 매매 타점 계산 (50원 단위 적용) ---
            last_close = float(df['Close'].iloc[-1])
            last_ma5 = float(df['MA5'].iloc[-1])
            last_ma10 = float(df['MA10'].iloc[-1])
            last_ma20 = float(df['MA20'].iloc[-1])
            last_bb_upper = float(df['BB_Upper'].iloc[-1])
            last_bb_lower = float(df['BB_Lower'].iloc[-1])

            # S1. 일반형 (추세)
            s1_p1 = round_to_50(last_close)
            s1_p2 = round_to_50(last_ma5)
            s1_p3 = round_to_50(last_ma10)

            # S2. 공격형 (돌파)
            s2_p1 = round_to_50(last_close)
            s2_p2 = round_to_50(last_bb_upper)
            s2_p3 = round_to_50(last_close * 1.03)

            # S3. 보수형 (저점)
            s3_p1 = round_to_50(last_ma20)
            s3_p2 = round_to_50(last_ma20 * 0.95)
            s3_p3 = round_to_50(last_bb_lower)

            # 매도 시나리오
            sell_p1 = round_to_50(last_bb_upper)
            sell_p2 = round_to_50(last_bb_upper * 1.05)
            stop_loss = round_to_50(last_ma20)

            st.write("---")
            
            # --- 매수 전략 섹션 ---
            st.markdown("""
            <div style='background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); 
                        padding: 15px; border-radius: 15px; margin-bottom: 20px; color: white; text-align: center;'>
                <h3 style='margin:0; color:white;'>🎯 3-Scenario AI 매수 전략 (50원 단위)</h3>
            </div>
            """, unsafe_allow_html=True)

            col_s1, col_s2, col_s3 = st.columns(3)

            with col_s1: # 일반형
                st.markdown(f"""
                <div style='background-color:#e3f2fd; padding:15px; border-radius:10px; border:2px solid #2196f3; height:100%;'>
                    <h4 style='color:#0d47a1; text-align:center; margin:0;'>🌊 일반형 (추세)</h4>
                    <hr style='margin:10px 0;'>
                    <div style='font-size:0.9rem;'>
                        <strong>1. 정찰:</strong> <span style='float:right; color:#d32f2f;'>{s1_p1:,.0f}</span><br>
                        <strong>2. 불타기:</strong> <span style='float:right; color:#d32f2f;'>{s1_p2:,.0f}</span><br>
                        <strong>3. 눌림목:</strong> <span style='float:right; color:#d32f2f;'>{s1_p3:,.0f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_s2: # 공격형
                st.markdown(f"""
                <div style='background-color:#ffebee; padding:15px; border-radius:10px; border:2px solid #f44336; height:100%;'>
                    <h4 style='color:#b71c1c; text-align:center; margin:0;'>🔥 공격형 (돌파)</h4>
                    <hr style='margin:10px 0;'>
                    <div style='font-size:0.9rem;'>
                        <strong>1. 즉시:</strong> <span style='float:right; color:#d32f2f;'>{s2_p1:,.0f}</span><br>
                        <strong>2. 돌파:</strong> <span style='float:right; color:#d32f2f;'>{s2_p2:,.0f}</span><br>
                        <strong>3. 슈팅:</strong> <span style='float:right; color:#d32f2f;'>{s2_p3:,.0f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with col_s3: # 보수형
                st.markdown(f"""
                <div style='background-color:#e8f5e9; padding:15px; border-radius:10px; border:2px solid #4caf50; height:100%;'>
                    <h4 style='color:#1b5e20; text-align:center; margin:0;'>🛡️ 보수형 (저점)</h4>
                    <hr style='margin:10px 0;'>
                    <div style='font-size:0.9rem;'>
                        <strong>1. 생명선:</strong> <span style='float:right; color:#d32f2f;'>{s3_p1:,.0f}</span><br>
                        <strong>2. 투매:</strong> <span style='float:right; color:#d32f2f;'>{s3_p2:,.0f}</span><br>
                        <strong>3. 과매도:</strong> <span style='float:right; color:#d32f2f;'>{s3_p3:,.0f}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # --- 매도 전략 섹션 ---
            st.write("")
            st.markdown("""
            <div style='background: linear-gradient(135deg, #FF512F 0%, #DD2476 100%); 
                        padding: 15px; border-radius: 15px; margin: 20px 0 10px 0; color: white; text-align: center;'>
                <h3 style='margin:0; color:white;'>📉 AI 매도/청산 시나리오</h3>
            </div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style='background-color:#fff3cd; padding:20px; border-radius:10px; border:2px solid #ffc107; text-align:center;'>
                <div style='display:flex; justify-content:space-around; align-items:center; flex-wrap:wrap;'>
                    <div style='margin:10px;'>
                        <strong style='color:#856404; font-size:1.1rem;'>🎯 1차 목표 (저항)</strong><br>
                        <span style='font-size:1.5rem; color:#333; font-weight:bold;'>{sell_p1:,.0f}원</span><br>
                        <small style='color:#666;'>볼린저 밴드 상단</small>
                    </div>
                    <div style='margin:10px; border-left:1px solid #ddd; padding-left:20px;'>
                        <strong style='color:#d32f2f; font-size:1.1rem;'>🚀 2차 목표 (슈팅)</strong><br>
                        <span style='font-size:1.5rem; color:#333; font-weight:bold;'>{sell_p2:,.0f}원</span><br>
                        <small style='color:#666;'>상단 돌파 후 +5%</small>
                    </div>
                    <div style='margin:10px; border-left:1px solid #ddd; padding-left:20px;'>
                        <strong style='color:#1b5e20; font-size:1.1rem;'>🛑 손절/익절 (추세)</strong><br>
                        <span style='font-size:1.5rem; color:#333; font-weight:bold;'>{stop_loss:,.0f}원</span><br>
                        <small style='color:#666;'>20일선 이탈 시 전량 청산</small>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)


        with tab2:
            st.subheader("🗓️ 최근 데이터")
            three_months_ago = datetime.now() - timedelta(days=90)
            recent_df = df[df.index >= three_months_ago].copy().sort_index(ascending=False)
            st.dataframe(recent_df[['Open', 'High', 'Low', 'Close', 'Volume']].style.format("{:,.0f}"), use_container_width=True, height=500)

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")