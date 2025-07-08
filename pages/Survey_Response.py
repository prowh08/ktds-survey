import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import time

st.set_page_config(page_title="설문 응답", layout="centered", initial_sidebar_state="collapsed")
conn = st.connection("postgres", type="sql")

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

def save_responses(survey_id, user_email, responses):
    try:
        with conn.session as s:
            result = s.execute(
                text("INSERT INTO survey_results (survey_id, user_id, email, status, completed_at) VALUES (:sid, NULL, :email, 'completed', CURRENT_TIMESTAMP) RETURNING result_id;"),
                params={"sid": survey_id, "email": user_email}
            )
            result_id = result.scalar_one()

            for item_id, answer in responses.items():
                if not answer: continue
                
                if isinstance(answer, list):
                    for option_id in answer:
                        s.execute(
                            text("INSERT INTO user_responses (result_id, user_id, item_id, option_id) VALUES (:rid, NULL, :iid, :oid);"),
                            params={"rid": result_id, "iid": item_id, "oid": option_id}
                        )
                elif "option_id" in answer:
                     s.execute(
                        text("INSERT INTO user_responses (result_id, user_id, item_id, option_id) VALUES (:rid, NULL, :iid, :oid);"),
                        params={"rid": result_id, "iid": item_id, "oid": answer["option_id"]}
                    )
                elif "text" in answer and answer['text']:
                    s.execute(
                        text("INSERT INTO user_responses (result_id, user_id, item_id, response_text) VALUES (:rid, NULL, :iid, :text);"),
                        params={"rid": result_id, "iid": item_id, "text": answer["text"]}
                    )
            s.commit()
        return True
    except Exception as e:
        st.error(f"저장 중 오류가 발생했습니다: {e}")
        return False

params = st.query_params
survey_id = params.get("survey_id")
email = params.get("email")

if not survey_id or not survey_id.isdigit():
    st.error("잘못된 설문 링크입니다. URL을 확인해주세요.")
    st.stop()

survey_id = int(survey_id)
survey_info, items_df = get_survey_data(conn, survey_id)

if survey_info is None:
    st.error("존재하지 않거나 삭제된 설문입니다.")
    st.stop()
    
if f"submitted_{survey_id}_{email}" in st.session_state:
    st.success("설문에 참여해주셔서 감사합니다! 🙏")
    st.balloons()
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
            success = save_responses(survey_id, email, st.session_state.user_answers)
            if success:
                st.session_state[f"submitted_{survey_id}_{email}"] = True
                if "user_answers" in st.session_state:
                    del st.session_state.user_answers
                st.rerun()
        else:
            st.error("응답자를 식별할 수 없습니다. 전달받은 링크를 통해 다시 접속해주세요.")