import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 1. 페이지 설정
st.set_page_config(page_title="내 손안의 주식 앱", layout="wide")

# 2. 사이드바: 종목 및 기간 입력
st.sidebar.header("🔍 종목 검색")
ticker = st.sidebar.text_input("티커 입력 (예: 005930.KS, TSLA)", value="005930.KS")
days = st.sidebar.slider("차트 조회 기간 (일)", min_value=90, max_value=730, value=365)

# 3. 데이터 가져오기 함수 (★여기가 수정되었습니다★)
def get_data(ticker, days):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    
    # 데이터 다운로드
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)
    
    # [핵심 수정] 컬럼이 2단(MultiIndex)으로 되어있으면 1단으로 평탄화
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
        
    return data

# 메인 화면 구성
st.title(f"📈 {ticker} 주가 분석")

try:
    # 데이터 로딩 표시
    with st.spinner('데이터를 불러오는 중...'):
        df = get_data(ticker, days)

    if df.empty:
        st.error("❌ 데이터를 찾을 수 없습니다. 티커를 확인해주세요. (한국 주식은 .KS 또는 .KQ 필수)")
    else:
        # --- 지표 계산 섹션 ---
        
        # 1. 이동평균선 (MA5, MA20)
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        # 2. 볼린저 밴드 (20일, 승수 2)
        # 이제 컬럼이 평탄화되어서 에러가 나지 않습니다.
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)

        # 3. RSI 계산 (14일)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 탭 생성
        tab1, tab2 = st.tabs(["📊 차트 분석", "📋 최근 데이터 (3개월)"])

        with tab1:
            # --- 차트 그리기 ---
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, row_heights=[0.7, 0.3])

            # 볼린저 밴드 영역 (채우기)
            fig.add_trace(go.Scatter(
                x=list(df.index) + list(df.index[::-1]),
                y=list(df['BB_Upper']) + list(df['BB_Lower'][::-1]),
                fill='toself',
                fillcolor='rgba(128, 128, 128, 0.1)',  # 투명도 조절
                line=dict(color='rgba(255,255,255,0)'),
                name='볼린저 밴드',
                showlegend=False,
                hoverinfo='skip'
            ), row=1, col=1)
            
            # 볼린저 밴드 선
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB 상단'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), name='BB 하단'), row=1, col=1)

            # 캔들스틱
            fig.add_trace(go.Candlestick(x=df.index,
                                         open=df['Open'], high=df['High'],
                                         low=df['Low'], close=df['Close'], 
                                         name='주가'), row=1, col=1)
            
            # 이동평균선
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='blue', width=2), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=2), name='MA20'), row=1, col=1)

            # RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1), name='RSI'), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="blue", row=2, col=1)

            fig.update_layout(xaxis_rangeslider_visible=False, height=600, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True) 

            # --- 매매 타점 로직 ---
            last_close = float(df['Close'].iloc[-1])
            last_ma5 = float(df['MA5'].iloc[-1])
            last_ma20 = float(df['MA20'].iloc[-1])
            last_rsi = float(df['RSI'].iloc[-1])
            last_bb_upper = float(df['BB_Upper'].iloc[-1])
            last_bb_lower = float(df['BB_Lower'].iloc[-1])
            
            # 신호 판단
            buy_signal = (last_close > last_ma5) and (last_ma5 > last_ma20) and (last_rsi < 70)
            sell_signal = (last_ma5 < last_ma20) or (last_rsi >= 70)
            
            # 타점 계산
            buy_price_1 = last_close
            buy_price_2 = last_ma20
            buy_price_3 = last_bb_lower
            
            sell_price_1 = last_bb_upper
            sell_price_2 = last_bb_upper * 1.03
            sell_price_3 = last_bb_upper * 1.05

            st.write("---")
            st.subheader("📢 AI 매매 신호 분석")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("현재 주가", f"{last_close:,.0f}원")
                st.metric("RSI(14)", f"{last_rsi:.1f}")
            with col2:
                if buy_signal:
                    st.success("✅ **매수 신호**")
                    st.caption("추세 상승 + 모멘텀 양호")
                elif sell_signal:
                    st.error("❌ **매도 신호**")
                    st.caption("데드크로스 or 과매수")
                else:
                    st.info("⏸️ **관망**")
                    st.caption("뚜렷한 신호 없음")
            with col3:
                if last_ma5 > last_ma20:
                    st.success("📈 정배열 (골든크로스)")
                else:
                    st.warning("📉 역배열 (데드크로스)")

            st.write("---")
            
            # 타점 UI
            st.markdown("""
            <div style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        padding: 25px; border-radius: 15px; margin: 20px 0; color: white; text-align: center;'>
                <h2 style='margin:0; color:white;'>🎯 AI 추천 매매 타점</h2>
            </div>
            """, unsafe_allow_html=True)
            
            c_buy, c_sell = st.columns(2)
            
            with c_buy:
                st.markdown(f"""
                <div style='background-color:#e8f5e9; padding:20px; border-radius:10px; border:2px solid #4caf50;'>
                    <h3 style='color:#2e7d32; text-align:center; margin-top:0;'>💰 매수 타점</h3>
                    <div style='background:white; padding:10px; margin:10px 0; border-radius:5px;'>
                        <strong>1차 (시장가):</strong> <span style='float:right; color:#d32f2f; font-weight:bold;'>{buy_price_1:,.0f}원</span>
                    </div>
                    <div style='background:white; padding:10px; margin:10px 0; border-radius:5px;'>
                        <strong>2차 (눌림목):</strong> <span style='float:right; color:#d32f2f; font-weight:bold;'>{buy_price_2:,.0f}원</span>
                    </div>
                    <div style='background:white; padding:10px; margin:10px 0; border-radius:5px;'>
                        <strong>3차 (지지선):</strong> <span style='float:right; color:#d32f2f; font-weight:bold;'>{buy_price_3:,.0f}원</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            with c_sell:
                st.markdown(f"""
                <div style='background-color:#ffebee; padding:20px; border-radius:10px; border:2px solid #ef5350;'>
                    <h3 style='color:#c62828; text-align:center; margin-top:0;'>💸 매도 타점</h3>
                    <div style='background:white; padding:10px; margin:10px 0; border-radius:5px;'>
                        <strong>1차 (저항선):</strong> <span style='float:right; color:#1976d2; font-weight:bold;'>{sell_price_1:,.0f}원</span>
                    </div>
                    <div style='background:white; padding:10px; margin:10px 0; border-radius:5px;'>
                        <strong>2차 (돌파):</strong> <span style='float:right; color:#1976d2; font-weight:bold;'>{sell_price_2:,.0f}원</span>
                    </div>
                    <div style='background:white; padding:10px; margin:10px 0; border-radius:5px;'>
                        <strong>3차 (슈팅):</strong> <span style='float:right; color:#1976d2; font-weight:bold;'>{sell_price_3:,.0f}원</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with tab2:
            st.subheader("🗓️ 최근 3개월 데이터")
            three_months_ago = datetime.now() - timedelta(days=90)
            recent_df = df[df.index >= three_months_ago].copy().sort_index(ascending=False)
            st.dataframe(recent_df[['Open', 'High', 'Low', 'Close', 'Volume']].style.format("{:,.0f}"), 
                         use_container_width=True, height=500)

except Exception as e:
    st.error(f"오류가 발생했습니다: {e}")