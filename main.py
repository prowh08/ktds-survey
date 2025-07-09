import streamlit as st
import pandas as pd
import plotly.express as px
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from sqlalchemy import text
from openai import AzureOpenAI
import json
import os
from dotenv import load_dotenv

load_dotenv()

db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

openai_endpoint = os.getenv("AZURE_ENDPOINT")
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_api_version = os.getenv("OPENAI_API_VERSION")
openai_deployment = os.getenv("GPT_DEPLOYMENT_NAME")

db_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
conn = st.connection("postgres", type="sql", url=db_uri)

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
        SELECT DISTINCT ON (survey_group_id) survey_group_id, survey_title
        FROM surveys ORDER BY survey_group_id, version DESC;
    """
    return conn.query(query, ttl=600)

@st.cache_data(ttl=600)
def get_versions_for_group(_conn, survey_group_id):
    query = text("SELECT version FROM surveys WHERE survey_group_id = :group_id ORDER BY version DESC;")
    df = pd.DataFrame(_conn.execute(query, {"group_id": survey_group_id}).fetchall(), columns=['version'])
    return df['version'].tolist()

@st.cache_data(ttl=600)
def get_target_count(_conn, survey_id):
    query = text("SELECT SUM(jsonb_array_length(recipients)) FROM survey_sends WHERE survey_id = :sid;")
    result = _conn.execute(query, {"sid": survey_id}).scalar_one_or_none()
    return result or 0

@st.cache_data(ttl=600)
def get_survey_structure(_conn, survey_id):
    query = text("""
        SELECT si.item_title, array_agg(io.option_content ORDER BY io.option_id) as options
        FROM survey_items si JOIN item_options io ON si.item_id = io.item_id
        WHERE si.survey_id = :sid AND si.item_type != '인풋박스'
        GROUP BY si.item_id, si.item_title ORDER BY si.item_id;
    """)
    df = pd.DataFrame(_conn.execute(query, {"sid": survey_id}).fetchall(), columns=['item_title', 'options'])
    return df

@st.cache_data(ttl=600)
def get_responses_for_survey(_conn, survey_id):
    query = text("""
        SELECT sr.result_id, sr.completed_at, si.item_title, si.item_type,
               COALESCE(io.option_content, ur.response_text) AS response_content,
               sa.sentiment_label
        FROM survey_results sr
        JOIN user_responses ur ON sr.result_id = ur.result_id
        JOIN survey_items si ON ur.item_id = si.item_id
        LEFT JOIN item_options io ON ur.option_id = io.option_id
        LEFT JOIN sentiment_analysis sa ON ur.response_id = sa.response_id
        WHERE sr.survey_id = :sid AND sr.status = 'completed';
    """)
    long_df = pd.DataFrame(_conn.execute(query, {"sid": survey_id}).fetchall(), columns=['result_id', 'created_at', 'item_title', 'item_type', 'response_content', 'sentiment'])
    if long_df.empty: return pd.DataFrame(), pd.DataFrame()
    pivot_df = long_df.pivot_table(index=['result_id', 'created_at'], columns='item_title', values='response_content', aggfunc='first').reset_index()
    pivot_df = pivot_df.rename(columns=lambda c: '만족도' if '만족도' in c else '개선점' if '개선점' in c or '의견' in c else c)
    return pivot_df, long_df

@st.cache_data(ttl=3600)
def get_ai_evaluation(_client, text_responses_df):
    if not _client: return {"summary": "AI 클라이언트가 초기화되지 않았습니다.", "insights": []}
    if text_responses_df.empty: return {"summary": "분석할 텍스트 응답이 없습니다.", "insights": []}

    def format_row(row):
        return f"질문: {row['item_title']}\n답변: {row['response_content']}\n사전 분석된 감성: {row['sentiment']}"
    
    full_text_input = "\n\n".join(text_responses_df.apply(format_row, axis=1))
    
    system_prompt = """
        당신은 전문 시장 조사 분석가입니다. '질문', '답변', 그리고 사전 분석된 '감성'('Positive', 'Negative', 'Neutral')으로 구성된 일련의 사용자 설문조사 응답이 주어집니다.
        당신의 임무는 주어진 세 가지 정보를 모두 활용하여 포괄적인 분석을 수행하는 것입니다.

        1.  먼저, 주어진 모든 피드백을 종합하여, 간결하고 전문적인 한 문단의 종합 평가를 한국어로 생성해 주세요.
        2.  다음으로, 피드백에서 핵심 주제 또는 토픽을 3~5개 찾아내세요. 각 주제에 대해, 주어진 데이터를 바탕으로 전반적인 감성을 'Positive', 'Negative', 'Neutral' 중 하나로 판단해야 합니다.

        출력은 반드시 "summary"와 "insights"라는 두 개의 키를 가진 유효한 JSON 형식이어야 합니다.
        "insights"의 값은 각 객체가 "theme"과 "sentiment" 키를 갖는 객체들의 리스트여야 합니다.

        예시:
        {
        "summary": "사용자들은 전반적으로 새로운 기능에 긍정적인 반응을 보였으나, 일부는 가격 정책에 대해 우려를 표했습니다. 특히 UI/UX의 직관성에 대한 높은 평가가 두드러졌습니다.",
        "insights": [
            {"theme": "새로운 기능에 대한 관심", "sentiment": "Positive"},
            {"theme": "가격 정책", "sentiment": "Negative"},
            {"theme": "UI/UX 편의성", "sentiment": "Positive"}
        ]
        }
    """
    response = _client.chat.completions.create(
        model=openai_deployment,
        response_format={"type": "json_object"},
        temperature=0.9,
        max_tokens=500,
        messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_text_input}
        ]
    )
    return json.loads(response.choices[0].message.content)

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
    selected_title = st.selectbox("분석할 설문을 선택하세요:", survey_list_df['survey_title'].tolist(), key="selected_survey")
    selected_group_id = int(survey_list_df[survey_list_df['survey_title'] == selected_title]['survey_group_id'].iloc[0])
with filter_cols[1]:
    with conn.session as s: available_versions = get_versions_for_group(s, selected_group_id)
    selected_version = st.selectbox("버전 선택:", available_versions, format_func=lambda v: f"v{v}", index=0)
start_date_default, end_date_default = datetime.now().date() - timedelta(days=30), datetime.now().date()
with filter_cols[2]: start_date = st.date_input("시작일", value=start_date_default)
with filter_cols[3]: end_date = st.date_input("종료일", value=end_date_default)
with filter_cols[4]: st.write("⠀"); search_button = st.button("조회", use_container_width=True, type="primary")

st.markdown("---")

if search_button:
    with conn.session as s:
        query = text("SELECT survey_id FROM surveys WHERE survey_group_id = :gid AND version = :ver;")
        result = s.execute(query, {"gid": selected_group_id, "ver": selected_version}).scalar_one_or_none()
    if result is None: st.error("선택된 설문과 버전에 해당하는 데이터를 찾을 수 없습니다."); st.stop()
    
    final_survey_id = result
    
    with conn.session as s:
        df_full_responses, df_long_full = get_responses_for_survey(s, final_survey_id)
        survey_structure_df = get_survey_structure(s, final_survey_id)

    if df_full_responses.empty: st.warning("선택된 설문과 버전에 대한 응답 데이터가 없습니다.")
    else:
        df_full_responses['created_at'] = pd.to_datetime(df_full_responses['created_at'])
        df_responses = df_full_responses[(df_full_responses['created_at'].dt.date >= start_date) & (df_full_responses['created_at'].dt.date <= end_date)]
        
        df_long_full['created_at'] = pd.to_datetime(df_long_full['created_at'])
        df_long_responses = df_long_full[(df_long_full['created_at'].dt.date >= start_date) & (df_long_full['created_at'].dt.date <= end_date)]
        
        if df_responses.empty: st.info(f"선택하신 기간({start_date} ~ {end_date})에 해당하는 응답이 없습니다.")
        else:
            tab_graph, tab_table = st.tabs(["📊 그래프로 보기", "📄 전체 응답 보기"])
            with tab_graph:
                st.subheader(f"'{selected_title}' (v{selected_version}) 통계 결과")
                st.caption(f"분석 기간: {start_date} ~ {end_date}")

                with conn.session as s: target_count = get_target_count(s, final_survey_id)
                df_text_analysis = df_long_responses[df_long_responses['item_type'] == '인풋박스'].copy()
                df_text_analysis.dropna(subset=['response_content'], inplace=True)
                meaningless_responses = ['.', '없음', '없습니다']
                df_text_analysis = df_text_analysis[~df_text_analysis['response_content'].isin(meaningless_responses)]
                df_text_analysis = df_text_analysis[df_text_analysis['response_content'].str.strip() != '']

                kpi_cols = st.columns(4)
                total_responses = len(df_responses)
                response_rate = f"{total_responses / target_count:.1%}" if target_count > 0 else "N/A"
                text_responses_with_sentiment = df_text_analysis[df_text_analysis['sentiment'].notna()]
                positive_responses = (text_responses_with_sentiment['sentiment'] == 'positive').sum()
                positive_rate = f"{positive_responses / len(text_responses_with_sentiment):.1%}" if not text_responses_with_sentiment.empty else "N/A"

                kpi_cols[0].metric(label="총 응답 수", value=f"{total_responses} 건")
                kpi_cols[1].metric(label="응답률 (목표 대비)", value=response_rate)
                kpi_cols[2].metric(label="긍정 답변 비율", value=positive_rate)
                kpi_cols[3].metric(label="분석 기간", value=f"{(end_date - start_date).days + 1} 일")
                
                st.markdown("---")
                
                with st.spinner("AI가 텍스트 응답을 분석 및 요약하고 있습니다..."):
                    ai_evaluation = get_ai_evaluation(client, df_text_analysis)

                st.subheader("🤖 AI 종합 평가")
                st.info(ai_evaluation.get("summary", "AI 평가를 생성하지 못했습니다."))
                st.subheader("💡 AI 핵심 인사이트")
                insights = ai_evaluation.get("insights", [])
                if insights:
                    insight_cols = st.columns(len(insights))
                    for i, insight in enumerate(insights):
                        with insight_cols[i]:
                            sentiment_emoji = "😃" if insight.get("sentiment") == "Positive" else "😞" if insight.get("sentiment") == "Negative" else "😐"
                            st.metric(label=f"{sentiment_emoji} {insight.get('theme')}", value=insight.get('sentiment'))
                else: st.info("분석된 핵심 인사이트가 없습니다.")
                
                st.markdown("---")
                
                with st.container(border=True):
                    st.write("#### 🗓️ 일자별 응답 수")
                    daily_counts = df_responses['created_at'].dt.date.value_counts().sort_index()
                    fig_daily_bar = px.bar(x=daily_counts.index, y=daily_counts.values, labels={'x': '날짜', 'y': '응답 건수'})
                    fig_daily_bar.update_yaxes(rangemode='tozero'); st.plotly_chart(fig_daily_bar, use_container_width=True)

                st.markdown("---")

                st.subheader("💬 주관식 답변 분석")
                left_col, right_col = st.columns(2)
                with left_col:
                    subjective_questions = df_text_analysis['item_title'].unique()
                    if not subjective_questions.any():
                        st.info("분석할 주관식 답변이 없습니다.")
                    else:
                        for question_title in subjective_questions:
                            with st.container(border=True):
                                st.write(f"**Q. {question_title}**")
                                question_responses = df_text_analysis[df_text_analysis['item_title'] == question_title]
                                positive = question_responses[question_responses['sentiment'] == 'positive']['response_content'].tolist()
                                negative = question_responses[question_responses['sentiment'] == 'negative']['response_content'].tolist()
                                neutral = question_responses[question_responses['sentiment'] == 'neutral']['response_content'].tolist()

                                if positive:
                                    with st.expander(f"😃 긍정적인 답변 ({len(positive)}개)"):
                                        for resp in positive: st.markdown(f"- {resp}")
                                if negative:
                                    with st.expander(f"😞 부정적인 답변 ({len(negative)}개)"):
                                        for resp in negative: st.markdown(f"- {resp}")
                                if neutral:
                                    with st.expander(f"😐 중립적인 답변 ({len(neutral)}개)"):
                                        for resp in neutral: st.markdown(f"- {resp}")
                with right_col:
                    text_data_for_wc = " ".join(df_text_analysis["response_content"].dropna())
                    if text_data_for_wc:
                        with st.container(border=True):
                            st.write("#### ☁️ 주요 키워드 (워드클라우드)")
                            try:
                                font_path = "c:/Windows/Fonts/malgun.ttf"
                                wordcloud = WordCloud(width=800, height=400, background_color='white', font_path=font_path).generate(text_data_for_wc)
                                fig_wc, ax = plt.subplots(figsize=(10, 5)); ax.imshow(wordcloud, interpolation='bilinear'); ax.axis('off')
                                st.pyplot(fig_wc)
                            except Exception: st.warning("워드클라우트 생성에 실패했습니다. 한글 폰트 경로를 확인해주세요.")
                    else:
                        with st.container(border=True):
                            st.write("#### ☁️ 주요 키워드 (워드클라우드)")
                            st.info("분석할 키워드가 없습니다.")

            with tab_table:                
                st.subheader(f"📄 '{selected_title}' (v{selected_version}) 전체 응답 데이터")
                cols = df_responses.columns.tolist()
                if 'created_at' in cols: cols.insert(0, cols.pop(cols.index('created_at')))
                if 'result_id' in cols: cols.pop(cols.index('result_id'))
                st.dataframe(df_responses[cols], hide_index=True, use_container_width=True)
                
                st.markdown("---")
                
                st.subheader("📊 문항별 응답 분포")
                if survey_structure_df.empty: st.info("분석할 객관식 문항이 없습니다.")
                else:
                    chart_cols = st.columns(2)
                    for i, row in survey_structure_df.iterrows():
                        q_title = row['item_title']
                        all_options = row['options']
                        with chart_cols[i % 2]:
                            with st.container(border=True):
                                st.write(f"**Q. {q_title}**")
                                q_data = df_long_responses[df_long_responses['item_title'] == q_title]
                                response_counts = q_data['response_content'].value_counts()
                                full_counts = pd.Series(0, index=all_options).add(response_counts, fill_value=0)
                                fig = px.bar(y=full_counts.index, x=full_counts.values, labels={'y': '응답', 'x': '응답 수'}, orientation='h')
                                fig.update_layout(showlegend=False, height=300, yaxis={'categoryorder':'total ascending'}); fig.update_xaxes(dtick=1)
                                st.plotly_chart(fig, use_container_width=True)
else:
    st.info("조회할 설문과 기간을 선택하고 '조회' 버튼을 눌러주세요.")