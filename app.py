import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import traceback

# ==========================================
# 라이브러리 설정 및 안전 처리
# ==========================================
try:
    from pykrx import stock
    HAS_PYKRX = True
except ImportError:
    HAS_PYKRX = False

try:
    import setuptools
    HAS_SETUPTOOLS = True
except ImportError:
    HAS_SETUPTOOLS = False

# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(page_title="내 손안의 주식 앱", layout="wide")

# ==========================================
# [기능 1] 가격 포맷팅 함수
# ==========================================
def format_price(price, ticker):
    """
    티커에 따라 가격을 적절히 포맷팅하는 함수
    """
    if pd.isna(price) or price is None:
        return "-"
    
    is_korean = ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ')
    
    if is_korean:
        rounded_price = int(round(price / 50) * 50)
        return f"{rounded_price:,}원"
    else:
        return f"${price:,.2f}"

def round_price_if_korean(price, ticker):
    """한국 주식인 경우 50원 단위로 반올림"""
    is_korean = ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ')
    if is_korean:
        return round(price / 50) * 50
    return price

# ==========================================
# [기능 2] 메모장 관리 함수
# ==========================================
MEMO_FILE = "memos.txt"

def load_memos():
    if not os.path.exists(MEMO_FILE):
        try:
            with open(MEMO_FILE, "w", encoding="utf-8") as f:
                pass
        except Exception:
            pass
        return []
    try:
        with open(MEMO_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception:
        return []

def save_memo(memo):
    try:
        with open(MEMO_FILE, "a", encoding="utf-8") as f:
            f.write(memo + "\n")
        return True
    except Exception:
        return False

def delete_memo(index):
    memos = load_memos()
    if 0 <= index < len(memos):
        del memos[index]
        try:
            with open(MEMO_FILE, "w", encoding="utf-8") as f:
                for m in memos:
                    f.write(m + "\n")
            return True
        except Exception:
            return False
    return False

# ==========================================
# [기능 3] 데이터 수집 함수
# ==========================================
@st.cache_data
def get_stock_data(ticker, days):
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        
        return data
    except Exception as e:
        st.error(f"주가 데이터 수집 오류: {str(e)}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def get_investor_data_auto_fix(ticker, days):
    """
    [디버깅 모드] 에러 발생 시 상세 로그를 화면에 출력하는 함수
    """
    if not HAS_PYKRX:
        return "LIBRARY_ERROR: pykrx 라이브러리가 설치되지 않았습니다."

    ticker_code = ticker.split('.')[0].strip()
    
    # 날짜 고정 (테스트용)
    str_start = "20240102"
    str_end = "20240110"

    debug_info = f"""
    [디버깅 정보]
    - 티커: {ticker_code}
    - 요청 시작일: {str_start}
    - 요청 종료일: {str_end}
    - 라이브러리 유무: {HAS_PYKRX}
    """

    try:
        df = stock.get_market_trading_value_by_date(
            fromdate=str_start,
            todate=str_end,
            ticker=ticker_code
        )
        
        if df is None:
            return f"❌ 오류: 데이터가 None입니다.\n{debug_info}"
        
        if df.empty:
            return f"⚠️ 오류: 데이터가 비어있습니다 (Empty DataFrame).\n{debug_info}\n[가능성] IP 차단, 티커 오류, 혹은 네이버 금융 접속 불가"

        col_map = {
            '기관합계': '기관합계', '기관': '기관합계',
            '외국인합계': '외국인', '외국인': '외국인',
            '개인': '개인'
        }
        df = df.rename(columns=col_map)
        
        required = ['개인', '외국인', '기관합계']
        if not all(col in df.columns for col in required):
             return f"❌ 컬럼 오류: {list(df.columns)}\n{debug_info}"
        
        return df[required].cumsum()

    except Exception:
        error_msg = traceback.format_exc()
        return f"🔥 치명적 오류 발생 (Traceback):\n{error_msg}\n\n{debug_info}"

# ==========================================
# 사이드바 UI
# ==========================================
st.sidebar.header("🔍 종목 검색")
ticker = st.sidebar.text_input("티커 입력", value="005930.KS", help="예: 005930.KS (코스피), 035720.KQ (코스닥), TSLA (나스닥)")
days = st.sidebar.slider("차트 조회 기간 (일)", min_value=30, max_value=730, value=90)

st.sidebar.markdown("---")
st.sidebar.subheader("📝 내 메모장")
new_memo = st.sidebar.text_input("메모 입력", placeholder="종목코드 메모", key="memo_input")
if st.sidebar.button("메모 저장", key="save_memo"):
    if new_memo:
        if save_memo(new_memo):
            st.sidebar.success("저장됨!")
            st.rerun()
        else:
            st.sidebar.error("저장 실패")

memos = load_memos()
if memos:
    st.sidebar.markdown("---")
    for i, memo in enumerate(memos):
        col1, col2 = st.sidebar.columns([0.8, 0.2])
        col1.text(f"• {memo}")
        if col2.button("X", key=f"del_{i}"):
            if delete_memo(i):
                st.rerun()

# ==========================================
# 메인 화면
# ==========================================
st.title(f"📈 {ticker} 주가 분석")

try:
    # 주가 데이터 수집
    with st.spinner('주가 데이터를 불러오는 중...'):
        df = get_stock_data(ticker, days)

    if df.empty:
        st.error("❌ 주가 데이터를 찾을 수 없습니다. 티커를 확인해주세요.")
        st.info("💡 한국 주식은 티커 뒤에 .KS(코스피) 또는 .KQ(코스닥)를 붙여주세요.")
    else:
        # 기술적 지표 계산
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA10'] = df['Close'].rolling(window=10).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        # 볼린저 밴드
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        
        # RSI 계산
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 매매 타점 계산 (가격 반올림 포함)
        last_close = float(df['Close'].iloc[-1])
        last_ma5 = float(df['MA5'].iloc[-1])
        last_ma10 = float(df['MA10'].iloc[-1])
        last_ma20 = float(df['MA20'].iloc[-1])
        last_bb_upper = float(df['BB_Upper'].iloc[-1])
        last_bb_lower = float(df['BB_Lower'].iloc[-1])

        # -----------------------------------------------------------
        # [수정됨] 차트에 그릴 가로선 가격들 계산
        # -----------------------------------------------------------
        ma5_rounded = round_price_if_korean(last_ma5, ticker)
        ma10_rounded = round_price_if_korean(last_ma10, ticker) # [NEW] 눌림목용
        bb_upper_rounded = round_price_if_korean(last_bb_upper, ticker)
        ma20_rounded = round_price_if_korean(last_ma20, ticker)
        ma20_95_rounded = round_price_if_korean(last_ma20 * 0.95, ticker)
        
        # [NEW] 2차 목표가 (슈팅)
        sell_price_2 = round_price_if_korean(last_bb_upper * 1.05, ticker)

        # 탭 생성
        tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "📋 최근 데이터", "💰 수급 분석"])

        # ==========================================
        # Tab 1: 차트 분석
        # ==========================================
        with tab1:
            # 3단 차트 구성
            fig = make_subplots(
                rows=3, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.05,
                row_heights=[0.6, 0.2, 0.2],
                subplot_titles=("주가 차트 (전략 가로선 포함)", "거래량", "RSI(14)")
            )

            # Row 1: 주가 차트
            # 볼린저 밴드 영역
            fig.add_trace(
                go.Scatter(
                    x=list(df.index) + list(df.index[::-1]),
                    y=list(df['BB_Upper']) + list(df['BB_Lower'][::-1]),
                    fill='toself',
                    fillcolor='rgba(128, 128, 128, 0.1)',
                    line=dict(width=0),
                    name='볼린저 밴드',
                    showlegend=False,
                    hoverinfo='skip'
                ),
                row=1, col=1
            )
            
            # 볼린저 밴드 상단/하단 선
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1, dash='dot'), name='BB 상단'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1, dash='dot'), name='BB 하단'), row=1, col=1)
            
            # 캔들스틱 차트
            fig.add_trace(
                go.Candlestick(
                    x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='주가'
                ),
                row=1, col=1
            )
            
            # 이동평균선
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='blue', width=2), name='MA5'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA10'], line=dict(color='#FFD700', width=2, dash='dot'), name='MA10'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=2), name='MA20'), row=1, col=1)

            # -------------------------------------------------------
            # [수정완료] 5가지 전략 가로선
            # -------------------------------------------------------
            
            # 1. 일반형 (파란선): [수정] 불타기(MA5) -> 눌림목(MA10)
            fig.add_hline(
                y=ma10_rounded,
                line_dash="solid",
                line_color="blue",
                line_width=3,
                annotation_text=f"🌊 일반형 눌림목 ({format_price(ma10_rounded, ticker)})",
                annotation_position="bottom",
                annotation=dict(x=0.5, xanchor='center'),
                row=1, col=1
            )
            
            # 2. 공격형 (빨간선): 돌파(BB상단) -> 유지
            fig.add_hline(
                y=bb_upper_rounded,
                line_dash="solid",
                line_color="red",
                line_width=3,
                annotation_text=f"🔥 공격형 돌파 ({format_price(bb_upper_rounded, ticker)})",
                annotation_position="bottom",
                annotation=dict(x=0.5, xanchor='center'),
                row=1, col=1
            )
            
            # 3. 보수형 (초록선): 투매(MA20*0.95) -> 유지
            fig.add_hline(
                y=ma20_95_rounded,
                line_dash="solid",
                line_color="green",
                line_width=3,
                annotation_text=f"🛡️ 보수형 투매 ({format_price(ma20_95_rounded, ticker)})",
                annotation_position="bottom",
                annotation=dict(x=0.5, xanchor='center'),
                row=1, col=1
            )
            
            # 4. 목표가 (노란선): [수정] 1차 저항 -> 2차 목표(슈팅)
            fig.add_hline(
                y=sell_price_2,
                line_dash="dash",
                line_color="gold",
                line_width=2,
                annotation_text=f"🚀 2차 목표 (슈팅) ({format_price(sell_price_2, ticker)})",
                annotation_position="bottom",
                annotation=dict(x=0.5, xanchor='center'),
                row=1, col=1
            )
            
            # 5. 손절선 (회색선): [수정] 이름 변경
            fig.add_hline(
                y=ma20_rounded,
                line_dash="dot",
                line_color="gray",
                line_width=2,
                annotation_text=f"🛑 손절선 ({format_price(ma20_rounded, ticker)})",
                annotation_position="bottom",
                annotation=dict(x=0.5, xanchor='center'),
                row=1, col=1
            )

            # Row 2: 거래량
            colors = ['red' if row['Open'] <= row['Close'] else 'blue' for _, row in df.iterrows()]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='거래량'), row=2, col=1)

            # Row 3: RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name='RSI'), row=3, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1, annotation_text="과매수(70)")
            fig.add_hline(y=30, line_dash="dash", line_color="blue", row=3, col=1, annotation_text="과매도(30)")

            # 차트 레이아웃 설정
            fig.update_layout(
                height=800,
                xaxis_rangeslider_visible=False,
                hovermode='x unified'
            )
            
            fig.update_xaxes(title_text="날짜", row=3, col=1)
            fig.update_yaxes(title_text="가격", row=1, col=1)
            fig.update_yaxes(title_text="거래량", row=2, col=1)
            fig.update_yaxes(title_text="RSI", row=3, col=1)

            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")

            # 매수 전략 카드
            is_korean = ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ')
            currency_text = "원화" if is_korean else "달러"
            
            st.markdown(f"### 🎯 3-Scenario AI 매수 전략 ({currency_text})")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("""
                <div style='background-color: #e3f2fd; padding: 10px; border-radius: 10px; border: 1px solid #2196f3;'>
                    <h4 style='color: #0d47a1; text-align: center; margin: 0 0 10px 0;'>🌊 일반형 </h4>
                </div>
                """, unsafe_allow_html=True)
                st.info(f"""
                **1. 정찰:** {format_price(last_close, ticker)}
                
                **2. 불타기:** {format_price(ma5_rounded, ticker)}
                
                **3. 눌림목:** {format_price(ma10_rounded, ticker)}
                """)

            with col2:
                st.markdown("""
                <div style='background-color: #ffebee; padding: 10px; border-radius: 10px; border: 1px solid #f44336;'>
                    <h4 style='color: #b71c1c; text-align: center; margin: 0 0 10px 0;'>🔥 공격형 </h4>
                </div>
                """, unsafe_allow_html=True)
                st.error(f"""
                **1. 즉시 진입:** {format_price(last_close, ticker)}
                
                **2. 돌파 매매:** {format_price(bb_upper_rounded, ticker)}
                
                **3. 슈팅 구간:** {format_price(round_price_if_korean(last_close * 1.03, ticker), ticker)}
                """)

            with col3:
                st.markdown("""
                <div style='background-color: #e8f5e9; padding: 10px; border-radius: 10px; border: 1px solid #4caf50;'>
                    <h4 style='color: #1b5e20; text-align: center; margin: 0 0 10px 0;'>🛡️ 보수형 </h4>
                </div>
                """, unsafe_allow_html=True)
                st.success(f"""
                **1. 생명선 지지:** {format_price(ma20_rounded, ticker)}
                
                **2. 투매 잡기:** {format_price(ma20_95_rounded, ticker)}
                
                **3. 과매도 구간:** {format_price(round_price_if_korean(last_bb_lower, ticker), ticker)}
                """)

            # 매도/청산 가이드
            st.markdown("---")
            st.markdown("### 📉 AI 매도/청산 시나리오")
            
            st.warning(f"""
            **🎯 1차 목표 (저항선):** {format_price(bb_upper_rounded, ticker)} 
            
            **🚀 2차 목표 (슈팅 구간):** {format_price(sell_price_2, ticker)} 
            
            **🛑 손절선:** {format_price(ma20_rounded, ticker)} 
            """)

        # ==========================================
        # Tab 2: 최근 데이터
        # ==========================================
        with tab2:
            st.subheader("🗓️ 최근 데이터 (최근 90일)")
            
            is_korean = ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ')
            if is_korean:
                format_dict = {
                    'Open': '{:,.0f}', 'High': '{:,.0f}', 'Low': '{:,.0f}', 'Close': '{:,.0f}', 'Volume': '{:,.0f}'
                }
            else:
                format_dict = {
                    'Open': '{:,.2f}', 'High': '{:,.2f}', 'Low': '{:,.2f}', 'Close': '{:,.2f}', 'Volume': '{:,.0f}'
                }
            
            display_df = df[['Open', 'High', 'Low', 'Close', 'Volume']].sort_index(ascending=False).head(90)
            st.dataframe(
                display_df.style.format(format_dict),
                use_container_width=True,
                height=500
            )

        # ==========================================
        # Tab 3: 수급 분석
        # ==========================================
        with tab3:
            st.subheader("💰 투자자별 누적 순매수 추이")
            
            is_korean = ticker.upper().endswith('.KS') or ticker.upper().endswith('.KQ')
            
            if not is_korean:
                st.info("💡 수급 분석 기능은 한국 주식(.KS, .KQ)에만 제공됩니다.")
                st.warning("🚫 미국/해외 주식은 수급 데이터를 제공하지 않습니다.")
            elif not HAS_PYKRX:
                st.error("❌ pykrx 라이브러리가 설치되지 않았습니다.")
                st.info("💡 다음 명령어로 설치해주세요: `pip install pykrx`")
            else:
                with st.spinner("수급 데이터를 가져오는 중 (자동 복구 기능 활성화)..."):
                    result = get_investor_data_auto_fix(ticker, days)
                
                if isinstance(result, str):
                    if "LIBRARY_ERROR" in result:
                        st.error("❌ " + result.replace("LIBRARY_ERROR: ", ""))
                    elif "EMPTY_DATA" in result:
                        st.warning("⚠️ " + result.replace("EMPTY_DATA: ", ""))
                        st.info("💡 장 시작 전이거나, 아직 거래 데이터가 집계되지 않았을 수 있습니다.")
                    elif "COLUMN_ERROR" in result:
                        st.error("❌ " + result.replace("COLUMN_ERROR: ", ""))
                        st.code(result)
                    elif "RUNTIME_ERROR" in result:
                        st.error("❌ 데이터 조회 중 오류가 발생했습니다.")
                        st.code(result.replace("RUNTIME_ERROR: ", ""))
                        st.info("💡 티커 코드와 조회 날짜를 확인해주세요.")
                else:
                    # 차트 그리기
                    fig_inv = go.Figure()
                    
                    fig_inv.add_trace(go.Scatter(
                        x=result.index, y=result['개인'], mode='lines', name='개인',
                        line=dict(color='green', width=2),
                        hovertemplate='<b>날짜:</b> %{x}<br><b>개인 누적 순매수:</b> %{y:,.0f}원<extra></extra>'
                    ))
                    
                    fig_inv.add_trace(go.Scatter(
                        x=result.index, y=result['외국인'], mode='lines', name='외국인',
                        line=dict(color='red', width=2),
                        hovertemplate='<b>날짜:</b> %{x}<br><b>외국인 누적 순매수:</b> %{y:,.0f}원<extra></extra>'
                    ))
                    
                    fig_inv.add_trace(go.Scatter(
                        x=result.index, y=result['기관합계'], mode='lines', name='기관합계',
                        line=dict(color='blue', width=2),
                        hovertemplate='<b>날짜:</b> %{x}<br><b>기관합계 누적 순매수:</b> %{y:,.0f}원<extra></extra>'
                    ))
                    
                    fig_inv.update_layout(
                        title=f"{ticker} - 투자자별 누적 순매수 추이 (최근 {days}일)",
                        xaxis_title="날짜", yaxis_title="누적 순매수 (원)",
                        height=600, hovermode='x unified',
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    
                    st.plotly_chart(fig_inv, use_container_width=True)
                    
                    # 최근 수급 요약
                    st.markdown("---")
                    st.subheader("📊 최근 수급 요약")
                    
                    if len(result) > 0:
                        latest = result.iloc[-1]
                        prev = result.iloc[-2] if len(result) > 1 else result.iloc[0]
                        
                        daily_change_personal = latest['개인'] - prev['개인'] if len(result) > 1 else latest['개인']
                        daily_change_foreign = latest['외국인'] - prev['외국인'] if len(result) > 1 else latest['외국인']
                        daily_change_institution = latest['기관합계'] - prev['기관합계'] if len(result) > 1 else latest['기관합계']
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("개인 누적 순매수", f"{latest['개인']:,.0f}원", f"{daily_change_personal:,.0f}원" if len(result) > 1 else None)
                        with col2:
                            st.metric("외국인 누적 순매수", f"{latest['외국인']:,.0f}원", f"{daily_change_foreign:,.0f}원" if len(result) > 1 else None)
                        with col3:
                            st.metric("기관합계 누적 순매수", f"{latest['기관합계']:,.0f}원", f"{daily_change_institution:,.0f}원" if len(result) > 1 else None)
                    
                    with st.expander("📋 상세 데이터 보기"):
                        display_result = result.copy()
                        display_result.columns = ['개인(누적)', '외국인(누적)', '기관합계(누적)']
                        display_result = display_result.sort_index(ascending=False)
                        st.dataframe(display_result.style.format("{:,.0f}"), use_container_width=True, height=400)

except Exception as e:
    st.error(f"❌ 오류가 발생했습니다: {str(e)}")
    st.info("💡 페이지를 새로고침하거나 티커를 확인해주세요.")
    st.code(f"티커: {ticker}\n조회 기간: {days}일\n오류 상세: {type(e).__name__}")