import streamlit as st
import pandas as pd
import plotly.express as px
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

st.markdown("""
<style>
    /* 1. 글자와 버튼 세로 중앙 정렬 (이전 코드 유지) */
    div[data-testid="column"] {
        display: flex;
        align-items: center;
        height: 55px;
    }

    /* 3. 글자가 길어지면 ...으로 생략하는 클래스 (이전 코드 유지) */
    .truncate {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        width: 100%;
    }
    
    /* 'Form'이라는 단어가 포함된 링크를 사이드바에서 숨깁니다 */
    [data-testid="stSidebarNav"] ul li a[href*="Form"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

def get_survey_details(survey_title):
    """선택된 설문의 상세 정보 (목표 응답 수 등)를 반환"""
    if survey_title == "1분기 고객 만족도 설문":
        return {"title": survey_title, "target_count": 100}
    return {"title": survey_title, "target_count": 50}

def get_responses_for_survey(survey_title):
    """DB에서 특정 설문에 대한 응답들을 불러오는 함수 (시뮬레이션)"""
    if survey_title == "1분기 고객 만족도 설문":
        base_date = datetime.now()
        return pd.DataFrame([
            {"만족도": "매우 만족", "개선점": "디자인 만족", "sentiment": "positive", "created_at": base_date - timedelta(days=10)},
            {"만족도": "만족", "개선점": "가격 보통", "sentiment": "neutral", "created_at": base_date - timedelta(days=8)},
            {"만족도": "매우 만족", "개선점": "성능 만족", "sentiment": "positive", "created_at": base_date - timedelta(days=5)},
            {"만족도": "보통", "개선점": "기능 부족", "sentiment": "negative", "created_at": base_date - timedelta(days=3)},
            {"만족도": "만족", "개선점": "사용법 쉬움", "sentiment": "positive", "created_at": base_date - timedelta(days=1)},
        ])
    return pd.DataFrame()

st.set_page_config(page_title="설문 통계", layout="wide")
st.title("📊 설문 통계")
st.write("설문별, 기간별 응답 결과를 시각화하여 보여줍니다.")
st.markdown("---")

filter_cols = st.columns([3, 1, 1, 1])
with filter_cols[0]:
    survey_titles = ["1분기 고객 만족도 설문", "신제품 아이디어 공모"]
    selected_title = st.selectbox("분석할 설문을 선택하세요:", survey_titles, key="selected_survey")

df_full_responses = get_responses_for_survey(selected_title)
survey_details = get_survey_details(selected_title)

if not df_full_responses.empty and 'created_at' in df_full_responses.columns:
    df_full_responses['created_at'] = pd.to_datetime(df_full_responses['created_at'])
    start_date_default, end_date_default = df_full_responses['created_at'].min().date(), df_full_responses['created_at'].max().date()
else:
    start_date_default, end_date_default = datetime.now().date() - timedelta(days=30), datetime.now().date()

with filter_cols[1]:
    start_date = st.date_input("시작일", value=start_date_default)
with filter_cols[2]:
    end_date = st.date_input("종료일", value=end_date_default)
with filter_cols[3]:
    st.write("⠀")
    search_button = st.button("조회", use_container_width=True, type="primary")

st.markdown("---")

if search_button:
    if df_full_responses.empty:
        st.warning("선택된 설문에 대한 응답 데이터가 없습니다.")
    else:
        df_responses = df_full_responses[
            (df_full_responses['created_at'].dt.date >= start_date) &
            (df_full_responses['created_at'].dt.date <= end_date)
        ]
        
        if df_responses.empty:
            st.info(f"선택하신 기간({start_date} ~ {end_date})에 해당하는 응답이 없습니다.")
        else:
            st.subheader(f"'{selected_title}' 통계 결과 ({start_date} ~ {end_date})")

            kpi_cols = st.columns(4)
            total_responses = len(df_responses)
            target_count = survey_details.get("target_count", 0)
            response_rate = f"{total_responses / target_count:.1%}" if target_count > 0 else "N/A"
            positive_responses = (df_responses['sentiment'] == 'positive').sum()
            positive_rate = f"{positive_responses / total_responses:.1%}" if total_responses > 0 else "N/A"

            kpi_cols[0].metric(label="총 응답 수", value=f"{total_responses} 건")
            kpi_cols[1].metric(label="응답률 (목표 대비)", value=response_rate)
            kpi_cols[2].metric(label="긍정 답변 비율", value=positive_rate)
            kpi_cols[3].metric(label="분석 기간", value=f"{(end_date - start_date).days + 1} 일")
            
            st.markdown("---")
            
            with st.container(border=True):
                st.write("#### 🗓️ 일자별 응답 추이")
                daily_counts = df_responses['created_at'].dt.date.value_counts().sort_index()
                fig_line = px.line(daily_counts, x=daily_counts.index, y=daily_counts.values, labels={'x': '날짜', 'y': '응답 수'}, markers=True)
                st.plotly_chart(fig_line, use_container_width=True)

            left_chart_col, right_chart_col = st.columns(2)
            with left_chart_col:
                with st.container(border=True):
                    st.write("#### 📈 만족도 분포")
                    satisfaction_counts = df_responses["만족도"].value_counts()
                    fig_bar = px.bar(satisfaction_counts, x=satisfaction_counts.index, y=satisfaction_counts.values, labels={'x': '만족도', 'y': '응답 수'}, color=satisfaction_counts.index)
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                with st.container(border=True):
                    st.write("#### 📝 최신 응답 일부 (표)")
                    display_df = df_responses[['created_at', '만족도', 'sentiment', '개선점']].sort_values(by="created_at", ascending=False).head(10)
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

            with right_chart_col:
                with st.container(border=True):
                    st.write("#### 💬 주관식 답변 감성 분석")
                    sentiment_counts = df_responses["sentiment"].value_counts()
                    fig_donut = px.pie(sentiment_counts, values=sentiment_counts.values, names=sentiment_counts.index, title='주요 개선 의견 감성 분포', hole=.3, color_discrete_map={'positive':'blue', 'negative':'red', 'neutral':'grey'})
                    st.plotly_chart(fig_donut, use_container_width=True)

                with st.container(border=True):
                    st.write("#### ☁️ 개선점에 대한 주요 키워드")
                    text = " ".join(df_responses["개선점"].dropna())
                    try:
                        font_path = "c:/Windows/Fonts/malgun.ttf"
                        wordcloud = WordCloud(width=800, height=400, background_color='white', font_path=font_path).generate(text)
                        fig_wc, ax = plt.subplots(figsize=(10, 5)); ax.imshow(wordcloud, interpolation='bilinear'); ax.axis('off')
                        st.pyplot(fig_wc)
                    except Exception:
                        st.error("워드클라우드 생성 중 오류가 발생했습니다.")
else:
    st.info("조회할 설문과 기간을 선택하고 '조회' 버튼을 눌러주세요.")