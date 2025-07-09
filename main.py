import streamlit as st
import pandas as pd
import plotly.express as px
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from sqlalchemy import text
import os
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

db_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

conn = st.connection("postgres", type="sql", url=db_uri)

openai_endpoint = os.getenv("AZURE_ENDPOINT")
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_api_version = os.getenv("OPENAI_API_VERSION")
openai_deployment = os.getenv("GPT_DEPLOYMENT_NAME")

client = AzureOpenAI(
        api_version=openai_api_version,
        azure_endpoint=openai_endpoint,
        api_key=openai_api_key,
)



st.markdown("""
<style>
    div[data-testid="column"] { display: flex; align-items: center; height: 55px; }
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; }
    [data-testid="stSidebarNav"] ul li a[href*="Form"] { display: none; }
    [data-testid="stSidebarNav"] ul li a[href*="Survey"] { display: none; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=600)
def get_survey_list():
    query = """
        SELECT DISTINCT ON (survey_group_id)
            survey_group_id,
            survey_title
        FROM surveys
        ORDER BY survey_group_id, version DESC;
    """
    return conn.query(query, ttl=600)

@st.cache_data(ttl=600)
def get_versions_for_group(_conn, survey_group_id):
    query = text("""
        SELECT version FROM surveys
        WHERE survey_group_id = :group_id
        ORDER BY version DESC;
    """)
    df = pd.DataFrame(_conn.execute(query, {"group_id": survey_group_id}).fetchall(), columns=['version'])
    return df['version'].tolist()

@st.cache_data(ttl=600)
def get_target_count(_conn, survey_id):
    query = text("SELECT SUM(jsonb_array_length(recipients)) FROM survey_sends WHERE survey_id = :sid;")
    result = _conn.execute(query, {"sid": survey_id}).scalar_one_or_none()
    return result or 0

@st.cache_data(ttl=600)
def get_responses_for_survey(_conn, survey_id):
    query = text("""
        SELECT
            sr.result_id,
            sr.completed_at,
            si.item_title,
            COALESCE(io.option_content, ur.response_text) AS response_content,
            sa.sentiment_label
        FROM
            survey_results sr
        JOIN
            user_responses ur ON sr.result_id = ur.result_id
        JOIN
            survey_items si ON ur.item_id = si.item_id
        LEFT JOIN
            item_options io ON ur.option_id = io.option_id
        LEFT JOIN
            sentiment_analysis sa ON ur.response_id = sa.response_id
        WHERE
            sr.survey_id = :sid AND sr.status = 'completed';
    """)
    long_df = pd.DataFrame(_conn.execute(query, {"sid": survey_id}).fetchall(), columns=['result_id', 'created_at', 'item_title', 'response_content', 'sentiment'])
    
    if long_df.empty:
        return pd.DataFrame()

    pivot_df = long_df.pivot_table(
        index=['result_id', 'created_at'], 
        columns='item_title', 
        values='response_content',
        aggfunc='first'
    ).reset_index()

    sentiment_df = long_df[long_df['sentiment'].notna()][['result_id', 'sentiment']].drop_duplicates()
    final_df = pd.merge(pivot_df, sentiment_df, on='result_id', how='left')
    
    final_df = final_df.rename(columns=lambda c: '만족도' if '만족도' in c else '개선점' if '개선점' in c or '의견' in c else c)
    
    return final_df

st.set_page_config(page_title="설문 통계", layout="wide")
st.title("📊 설문 통계 대시보드")
st.write("설문별, 기간별 응답 결과를 시각화하여 보여줍니다.")
st.markdown("---")

survey_list_df = get_survey_list()
if survey_list_df.empty:
    st.warning("분석할 수 있는 설문이 없습니다. 먼저 설문을 생성해주세요.")
    st.stop()

filter_cols = st.columns([2, 1, 1, 1, 1])
with filter_cols[0]:
    selected_title = st.selectbox(
        "분석할 설문을 선택하세요:", 
        survey_list_df['survey_title'].tolist(), 
        key="selected_survey"
    )
    selected_group_id = int(survey_list_df[survey_list_df['survey_title'] == selected_title]['survey_group_id'].iloc[0])

with filter_cols[1]:
    with conn.session as s:
        available_versions = get_versions_for_group(s, selected_group_id)
    
    selected_version = st.selectbox(
        "버전 선택:",
        available_versions,
        format_func=lambda v: f"v{v}",
        index=0
    )

start_date_default, end_date_default = datetime.now().date() - timedelta(days=30), datetime.now().date()

with filter_cols[2]:
    start_date = st.date_input("시작일", value=start_date_default)
with filter_cols[3]:
    end_date = st.date_input("종료일", value=end_date_default)
with filter_cols[4]:
    st.write("⠀")
    search_button = st.button("조회", use_container_width=True, type="primary")

st.markdown("---")

if search_button:
    with conn.session as s:
        query = text("SELECT survey_id FROM surveys WHERE survey_group_id = :gid AND version = :ver;")
        result = s.execute(query, {"gid": selected_group_id, "ver": selected_version}).scalar_one_or_none()
        
    if result is None:
        st.error("선택된 설문과 버전에 해당하는 데이터를 찾을 수 없습니다.")
        st.stop()
    
    final_survey_id = result
    
    with conn.session as s:
        df_full_responses = get_responses_for_survey(s, final_survey_id)

    if df_full_responses.empty:
        st.warning("선택된 설문과 버전에 대한 응답 데이터가 없습니다.")
    else:
        df_full_responses['created_at'] = pd.to_datetime(df_full_responses['created_at'])
        df_responses = df_full_responses[
            (df_full_responses['created_at'].dt.date >= start_date) &
            (df_full_responses['created_at'].dt.date <= end_date)
        ]
        
        if df_responses.empty:
            st.info(f"선택하신 기간({start_date} ~ {end_date})에 해당하는 응답이 없습니다.")
        else:
            tab_graph, tab_table = st.tabs(["📊 그래프로 보기", "📄 전체 응답 보기"])

            with tab_graph:
                st.subheader(f"'{selected_title}' (v{selected_version}) 통계 결과")
                st.caption(f"분석 기간: {start_date} ~ {end_date}")

                with conn.session as s:
                    target_count = get_target_count(s, final_survey_id)

                kpi_cols = st.columns(4)
                total_responses = len(df_responses)
                response_rate = f"{total_responses / target_count:.1%}" if target_count > 0 else "N/A"
                positive_responses = (df_responses['sentiment'] == 'positive').sum() if 'sentiment' in df_responses.columns else 0
                positive_rate = f"{positive_responses / total_responses:.1%}" if total_responses > 0 else "N/A"

                kpi_cols[0].metric(label="총 응답 수", value=f"{total_responses} 건")
                kpi_cols[1].metric(label="응답률 (목표 대비)", value=response_rate)
                kpi_cols[2].metric(label="긍정 답변 비율", value=positive_rate)
                kpi_cols[3].metric(label="분석 기간", value=f"{(end_date - start_date).days + 1} 일")
                
                st.markdown("---")
                
                with st.container(border=True):
                    st.write("#### 🗓️ 일자별 응답 수")
                    daily_counts = df_responses['created_at'].dt.date.value_counts().sort_index()
                    fig_daily_bar = px.bar(
                        x=daily_counts.index,
                        y=daily_counts.values,
                        labels={'x': '날짜', 'y': '응답 건수'}
                    )
                    fig_daily_bar.update_yaxes(rangemode='tozero')
                    st.plotly_chart(fig_daily_bar, use_container_width=True)

                left_chart_col, right_chart_col = st.columns(2)
                with left_chart_col:
                    if '만족도' in df_responses.columns:
                        with st.container(border=True):
                            st.write("#### 📈 만족도 분포")
                            satisfaction_counts = df_responses["만족도"].value_counts()
                            fig_bar = px.bar(satisfaction_counts, x=satisfaction_counts.index, y=satisfaction_counts.values, labels={'x': '만족도', 'y': '응답 수'}, color=satisfaction_counts.index)
                            st.plotly_chart(fig_bar, use_container_width=True)
                    
                    with st.container(border=True):
                        st.write("#### 📝 최신 응답 일부 (표)")
                        cols_to_display = ['created_at'] + [col for col in ['만족도', 'sentiment', '개선점'] if col in df_responses.columns]
                        display_df = df_responses[cols_to_display].sort_values(by="created_at", ascending=False).head(10)
                        st.dataframe(display_df, use_container_width=True, hide_index=True)

                with right_chart_col:
                    if 'sentiment' in df_responses.columns:
                        with st.container(border=True):
                            st.write("#### 💬 주관식 답변 감성 분석")
                            sentiment_counts = df_responses["sentiment"].value_counts()
                            fig_donut = px.pie(sentiment_counts, values=sentiment_counts.values, names=sentiment_counts.index, title='주요 개선 의견 감성 분포', hole=.3, color_discrete_map={'positive':'blue', 'negative':'red', 'neutral':'grey'})
                            st.plotly_chart(fig_donut, use_container_width=True)

                    if '개선점' in df_responses.columns:
                        with st.container(border=True):
                            st.write("#### ☁️ 개선점에 대한 주요 키워드")
                            text = " ".join(df_responses["개선점"].dropna())
                            if text:
                                try:
                                    font_path = "c:/Windows/Fonts/malgun.ttf"
                                    wordcloud = WordCloud(width=800, height=400, background_color='white', font_path=font_path).generate(text)
                                    fig_wc, ax = plt.subplots(figsize=(10, 5)); ax.imshow(wordcloud, interpolation='bilinear'); ax.axis('off')
                                    st.pyplot(fig_wc)
                                except Exception as e:
                                    st.warning("워드클라우트 생성에 실패했습니다. 한글 폰트 경로를 확인해주세요.")
                            else:
                                st.info("분석할 키워드가 없습니다.")
            
            with tab_table:
                st.subheader(f"'{selected_title}' (v{selected_version}) 전체 응답 데이터")
                st.info("각 행은 한 명의 응답자가 제출한 전체 답변입니다. 질문 제목이 표의 헤더가 됩니다.")
                
                cols = df_responses.columns.tolist()
                if 'created_at' in cols:
                    cols.insert(0, cols.pop(cols.index('created_at')))
                if 'result_id' in cols:
                    cols.pop(cols.index('result_id'))
                
                display_full_df = df_responses[cols]
                st.dataframe(display_full_df, use_container_width=True)

else:
    st.info("조회할 설문과 기간을 선택하고 '조회' 버튼을 눌러주세요.")