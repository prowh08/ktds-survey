import streamlit as st
from sqlalchemy import text
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient
import os
from dotenv import load_dotenv

load_dotenv()  # 환경변수 불러오기
st.set_page_config(page_title="설문 응답", layout="centered", initial_sidebar_state="collapsed")

# db connection setup
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

db_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

conn = st.connection("postgres", type="sql", url=db_uri)

# Get environment variables
language_endpoint = os.getenv("AZURE_LNG_ENDPOINT")
language_api_key = os.getenv("AZURE_LNG_API_KEY")

lang_credential = AzureKeyCredential(language_api_key)

# OpenAI client setting
text_client = TextAnalyticsClient(
        endpoint=language_endpoint,
        credential=lang_credential
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stHeader"] { display: none; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def get_survey_data(_conn, survey_id):
    try:
        survey_info = _conn.query(f"SELECT survey_title, survey_content, page FROM surveys WHERE survey_id={survey_id}", ttl=60)
        if survey_info.empty:
            return None, None
        
        items_query = """
            SELECT si.item_id, si.item_title, si.item_type, array_agg(io.option_content ORDER BY io.option_id) as options, array_agg(io.option_id ORDER BY io.option_id) as option_ids
            FROM survey_items si
            LEFT JOIN item_options io ON si.item_id = io.item_id
            WHERE si.survey_id = :sid
            GROUP BY si.item_id, si.item_title, si.item_type
            ORDER BY si.item_id;
        """
        items_df = _conn.query(sql=items_query, params={"sid": survey_id})
        
        return survey_info.iloc[0], items_df
    except Exception as e:
        st.error(f"데이터 조회 중 오류 발생: {e}")
        return None, None

def save_responses(survey_id, send_id, user_email, responses):
    try:
        with conn.session as s:
            result = s.execute(
                text("INSERT INTO survey_results (survey_id, send_id, email, status, completed_at) VALUES (:sid, :send_id, :email, 'completed', CURRENT_TIMESTAMP) RETURNING result_id;"),
                params={"sid": survey_id, "send_id": send_id, "email": user_email}
            )
            result_id = result.scalar_one()

            for item_id, answer in responses.items():
                if not answer: continue
                
                if isinstance(answer, list):
                    for option_id in answer:
                        s.execute(
                            text("INSERT INTO user_responses (result_id,  item_id, option_id) VALUES (:rid, :iid, :oid);"),
                            params={"rid": result_id, "iid": item_id, "oid": option_id}
                        )
                elif "option_id" in answer:
                     s.execute(
                        text("INSERT INTO user_responses (result_id,  item_id, option_id) VALUES (:rid, :iid, :oid);"),
                        params={"rid": result_id, "iid": item_id, "oid": answer["option_id"]}
                    )
                elif "text" in answer and answer['text'].strip():
                    response_text_to_save = answer['text'].strip()
                    res = s.execute(
                        text("INSERT INTO user_responses (result_id, item_id, response_text) VALUES (:rid, :iid, :text) RETURNING response_id;"),
                        params={"rid": result_id, "iid": item_id, "text": response_text_to_save}
                    )
                    response_id = res.scalar_one()

                    sentiment_label, sentiment_score = analyze_sentiment(text_client, response_text_to_save)
                    if sentiment_label and sentiment_score is not None:
                        s.execute(
                            text("INSERT INTO sentiment_analysis (response_id, sentiment_label, sentiment_score) VALUES (:rid, :label, :score);"),
                            params={"rid": response_id, "label": sentiment_label, "score": sentiment_score}
                        )
            s.commit()
        return True
    except Exception as e:
        st.error(f"저장 중 오류가 발생했습니다: {e}")
        return False

def analyze_sentiment(client, text_document):
    """주어진 텍스트의 감정을 분석하고, 레이블과 점수를 반환합니다."""
    try:
        result = client.analyze_sentiment(documents=[text_document])
        doc_result = [doc for doc in result if not doc.is_error][0]

        sentiment = doc_result.sentiment
        if sentiment == 'positive':
            score = doc_result.confidence_scores.positive
        elif sentiment == 'neutral':
            score = doc_result.confidence_scores.neutral
        else: # negative
            score = doc_result.confidence_scores.negative
            
        return sentiment, score
    except Exception as e:
        st.warning(f"감정 분석 API 호출 중 오류가 발생했습니다: {e}")
        return None, None

params = st.query_params
survey_id = int(st.query_params.get("survey_id"))
email = st.query_params.get("email")
send_id = st.query_params.get("send_id")

survey_info, items_df = get_survey_data(conn, survey_id)

if not all([survey_id, email, send_id]):
    st.error("잘못된 접근입니다. 유효한 설문 URL을 통해 접속해주세요.")
    st.stop()

if survey_info is None:
    st.error("존재하지 않거나 삭제된 설문입니다.")
    st.stop()
    
if f"submitted_{survey_id}_{email}" in st.session_state:
    st.success("설문에 참여해주셔서 감사합니다! 🙏")
    st.balloons()
    st.stop()

try:
    query = """
        SELECT status FROM survey_results
        WHERE send_id = :send_id AND email = :email;
    """
    result_df = conn.query(sql=query, params={"send_id": send_id, "email": email}, ttl=0)
    
    if not result_df.empty and result_df.iloc[0]['status'] == 'completed':
        st.warning("이미 설문에 참여하셨습니다. 감사합니다.")
        st.stop() # 페이지 실행 중지

except Exception as e:
    st.error(f"응답 상태를 확인하는 중 오류가 발생했습니다: {e}")
    st.stop()

    
st.title(survey_info['survey_title'])
st.markdown(survey_info['survey_content'])
st.markdown("---")

if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

all_questions_valid = True
if items_df.empty:
    st.warning("이 설문에는 등록된 문항이 없습니다.")
    all_questions_valid = False

for _, item in items_df.iterrows():
    item_id = item['item_id']
    st.subheader(f"Q. {item['item_title']}")

    if item['item_type'] == '라디오버튼':
        if not isinstance(item['options'], list) or (len(item['options']) > 0 and item['options'][0] is None): 
            st.warning("옵션이 올바르게 설정되지 않았습니다."); all_questions_valid = False; continue
        option_map = {opt: opt_id for opt, opt_id in zip(item['options'], item['option_ids'])}
        selected_option = st.radio("하나를 선택해주세요.", item['options'], key=f"item_{item_id}", index=None, label_visibility="collapsed")
        if selected_option:
            st.session_state.user_answers[item_id] = {"option_id": option_map[selected_option]}
    
    elif item['item_type'] == '체크박스':
        if not isinstance(item['options'], list) or (len(item['options']) > 0 and item['options'][0] is None):
            st.warning("옵션이 올바르게 설정되지 않았습니다."); all_questions_valid = False; continue
        selected_options = []
        option_map = {opt: opt_id for opt, opt_id in zip(item['options'], item['option_ids'])}
        for option in item['options']:
            if st.checkbox(option, key=f"item_{item_id}_{option_map[option]}"):
                selected_options.append(option_map[option])
        st.session_state.user_answers[item_id] = selected_options

    elif item['item_type'] == '인풋박스':
        text_input = st.text_area("답변을 입력해주세요.", key=f"item_{item_id}", height=150, label_visibility="collapsed")
        st.session_state.user_answers[item_id] = {"text": text_input}
        
    st.markdown("---")

if all_questions_valid and st.button("제출하기", use_container_width=True, type="primary"):
    
    is_fully_answered = True
    for _, item in items_df.iterrows():
        item_id = item['item_id']
        answer = st.session_state.user_answers.get(item_id)
        
        if answer is None:
            is_fully_answered = False
            break
        
        if item['item_type'] == '체크박스' and not answer:
            is_fully_answered = False
            break
        if item['item_type'] == '인풋박스' and not answer.get('text', '').strip():
            is_fully_answered = False
            break
            
    if not is_fully_answered:
        st.warning("⚠️ 모든 문항에 응답해주세요!")
    else:
        if email:
            success = save_responses(survey_id, send_id, email, st.session_state.user_answers)
            if success:
                st.session_state[f"submitted_{survey_id}_{email}"] = True
                if "user_answers" in st.session_state:
                    del st.session_state.user_answers
                st.rerun()
        else:
            st.error("응답자를 식별할 수 없습니다. 전달받은 링크를 통해 다시 접속해주세요.")