import streamlit as st
from sqlalchemy import text
import time
from sqlalchemy.exc import SQLAlchemyError
from openai import AzureOpenAI
import os
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="설문 수정", layout="wide", initial_sidebar_state="collapsed")

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

system_message = {
    "role": "system",
    "content": """
        "당신은 설문조사 문항 작성에 특화된 전문 카피라이터입니다.
        사용자가 입력한 질문을 응답자가 더 이해하기 쉽고, 명확하며, 중립적인 표현으로 다듬어주세요.
        다른 설명 없이, 다듬어진 최종 질문 문구만 출력해야 합니다."
        """
    }

st.markdown("""
<style>
    .stTextArea, .stTextInput { width: 100%; }
    [data-testid="stSidebarNav"] ul li a[href*="Form"] { display: none; }
    [data-testid="stSidebarNav"] ul li a[href*="Survey"] { display: none; }
    
</style>
""", unsafe_allow_html=True)

def initialize_edit_state():
    if not st.session_state.get('data_loaded', False):
        survey_id_to_edit = st.session_state.get('edit_survey_id')
        if survey_id_to_edit is None:
            return

        try:
            with conn.session as s:
                survey_info = s.execute(text("SELECT survey_title, survey_content, page FROM surveys WHERE survey_id = :id"), {"id": survey_id_to_edit}).mappings().fetchone()
                
                items_q = text("""
                    SELECT si.item_id, si.item_title, si.item_type, array_agg(io.option_content ORDER BY io.option_id) as options
                    FROM survey_items si
                    LEFT JOIN item_options io ON si.item_id = io.item_id
                    WHERE si.survey_id = :sid
                    GROUP BY si.item_id ORDER BY si.item_id;
                """)
                items_data = s.execute(items_q, {"sid": survey_id_to_edit}).mappings().fetchall()
            
            st.session_state.edit_title = survey_info['survey_title']
            st.session_state.edit_desc = survey_info['survey_content']
            st.session_state.is_paginated = survey_info['page']
            
            questions = []
            for item in items_data:
                questions.append({
                    "title": item['item_title'],
                    "type": item['item_type'],
                    "options": [opt for opt in item['options'] if opt is not None]
                })
            st.session_state.edit_questions = questions
            st.session_state.current_page = 0
            st.session_state.data_loaded = True

        except Exception as e:
            st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
            st.stop()

def refine_question_text(client, original_text):
    if not client:
        st.error("AI 클라이언트가 초기화되지 않았습니다.")
        return original_text
    
    response = client.chat.completions.create(
            model=openai_deployment,
            temperature=0.9,
            max_tokens=500,
            messages=[
                system_message,
                {"role": "user", "content": original_text}
            ]
        )
    return response.choices[0].message.content.strip()


if 'edit_survey_id' not in st.session_state:
    st.warning("잘못된 접근입니다. 설문 관리 페이지에서 수정할 항목을 선택해주세요.")
    if st.button("관리 페이지로 돌아가기"): st.switch_page("pages/설문지 관리.py")
    st.stop()

initialize_edit_state()

def reset_page_on_toggle(): st.session_state.current_page = 0
def go_to_next_page():
    if st.session_state.current_page < len(st.session_state.edit_questions) - 1: st.session_state.current_page += 1
def go_to_prev_page():
    if st.session_state.current_page > 0: st.session_state.current_page -= 1

def on_type_change(index):
    widget_key = f"edit_q_type_{index}"
    new_type = st.session_state[widget_key]
    st.session_state.edit_questions[index]['type'] = new_type


st.markdown(f"""
<div style='background:linear-gradient(90deg,#5359ff 0,#6a82fb 100%);padding:24px 0 12px 0;text-align:center;color:white;border-radius:8px;'>
    <h1 style='margin-bottom:0;'>설문 수정 (ID: {st.session_state.edit_survey_id})</h1>
</div>
""", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

edit_col, preview_col = st.columns([6, 4])

with edit_col:
    st.header("✍️ 설문 수정")

    with st.container(height=1500, border=True):
        st.text_input("설문 제목", key="edit_title")
        st.text_area("설문 설명", key="edit_desc")
        st.checkbox("미리보기 한 장씩 보기", key="is_paginated", on_change=reset_page_on_toggle)
        st.markdown("---")
        st.subheader("설문 문항 편집")

        for i in range(len(st.session_state.edit_questions)):
            with st.container(border=True):
                current_question = st.session_state.edit_questions[i]
                
                st.markdown(f"**문항 {i+1}**")
                title_cols = st.columns([4, 1])
                with title_cols[0]:
                    current_question['title'] = st.text_input(
                        "문항 제목", 
                        current_question['title'], 
                        key=f"edit_q_title_{i}", 
                        label_visibility="collapsed"
                    )
                with title_cols[1]:
                    if st.button("AI 추천", key=f"refine_{i}", use_container_width=True):
                        with st.spinner("AI가 문구를 다듬고 있습니다..."):
                           refined_text = refine_question_text(client, current_question['title'])
                           st.session_state.edit_questions[i]['title'] = refined_text
                           st.rerun()

                st.selectbox(
                    "입력 방식", 
                    ["라디오버튼", "체크박스", "인풋박스"],
                    index=["라디오버튼", "체크박스", "인풋박스"].index(current_question['type']),
                    key=f"edit_q_type_{i}",
                    on_change=on_type_change,
                    args=(i,)
                )

                if current_question['type'] in ["라디오버튼", "체크박스"]:
                    st.markdown("###### 🔹 옵션 편집")
                    for j in range(len(current_question['options'])):
                        opt_cols = st.columns([10, 1])
                        current_question['options'][j] = opt_cols[0].text_input(
                            f"옵션 {j+1}", 
                            value=current_question['options'][j], 
                            key=f"edit_opt_{i}_{j}", 
                            label_visibility="collapsed"
                        )
                        if opt_cols[1].button("✖️", key=f"edit_del_opt_{i}_{j}", use_container_width=True):
                            current_question['options'].pop(j)
                            st.rerun()

                    if st.button("➕ 옵션 추가", key=f"edit_add_opt_{i}"):
                        current_question['options'].append(f"새 옵션 {len(current_question['options'])+1}")
                        st.rerun()
                st.markdown("")

        if st.button("➕ 문항 추가", use_container_width=True):
            st.session_state.edit_questions.append({"title": "새로운 질문", "type": "라디오버튼", "options": ["옵션 1", "옵션 2"]})
            st.rerun()

with preview_col:
    st.header("👁️ 설문지 미리보기")
    with st.container(border=True):
        st.markdown(f"<h3 style='text-align: center;'>{st.session_state.edit_title}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center;'>{st.session_state.edit_desc}</p>", unsafe_allow_html=True)
        st.markdown("---")
                
        questions_to_show = [st.session_state.edit_questions[st.session_state.current_page]] if st.session_state.is_paginated else st.session_state.edit_questions
        
        for i, q in enumerate(questions_to_show):
            q_idx = st.session_state.current_page if st.session_state.is_paginated else i
            st.markdown(f"**Q{q_idx + 1}. {q['title']}**")
            
            if q['type'] in ["라디오버튼", "체크박스"] and not q['options']:
                st.warning("옵션을 추가해주세요.")
            
            if q['type'] == "라디오버튼": st.radio("응답", q['options'], key=f"p_r_{q_idx}", disabled=True, label_visibility="collapsed")
            elif q['type'] == "체크박스":
                for k, opt in enumerate(q['options']):
                    st.checkbox(opt, key=f"p_c_{q_idx}_{k}", disabled=True)
            elif q['type'] == "인풋박스": st.text_input("응답", key=f"p_i_{q_idx}", disabled=True, label_visibility="collapsed")
            st.markdown("---")

        if st.session_state.is_paginated:
            c1, c2 = st.columns(2)
            c1.button("이전", on_click=go_to_prev_page, use_container_width=True, disabled=(st.session_state.current_page == 0))
            c2.button("다음", on_click=go_to_next_page, use_container_width=True, disabled=(st.session_state.current_page >= len(st.session_state.edit_questions) - 1))

st.markdown("---")
_, left_col, center_col, _ = st.columns([1, 1.5, 1.5, 1])

def cleanup_state():
    keys = ['edit_survey_id', 'data_loaded', 'edit_title', 'edit_desc', 'edit_questions', 'is_paginated', 'current_page']
    for key in keys:
        if key in st.session_state: del st.session_state[key]

with left_col:
    if st.button("🔙 취소하고 돌아가기", use_container_width=True):
        cleanup_state()
        st.switch_page("pages/설문지 관리.py")

with center_col:
    if st.button("💾 수정 완료", use_container_width=True, type="primary"):
        try:
            with conn.session as s:
                survey_id = st.session_state.edit_survey_id
                
                update_survey_q = text('UPDATE surveys SET survey_title = :title, survey_content = :content, page = :page, updated_at = CURRENT_TIMESTAMP WHERE survey_id = :id;')
                s.execute(update_survey_q, params=dict(title=st.session_state.edit_title, content=st.session_state.edit_desc, page=st.session_state.is_paginated, id=survey_id))
                
                s.execute(text('DELETE FROM survey_items WHERE survey_id = :id;'), params=dict(id=survey_id))

                for q_item in st.session_state.edit_questions:
                    item_result = s.execute(
                        text('INSERT INTO survey_items (survey_id, item_title, item_type) VALUES (:sid, :title, :type) RETURNING item_id;'),
                        params=dict(sid=survey_id, title=q_item['title'], type=q_item['type'])
                    )
                    item_id = item_result.scalar_one()
                    if q_item['type'] in ["라디오버튼", "체크박스"]:
                        for option_content in q_item['options']:
                            s.execute(
                                text('INSERT INTO item_options (item_id, option_content) VALUES (:iid, :content);'),
                                params=dict(iid=item_id, content=option_content)
                            )
                s.commit()
            
            st.success("설문이 성공적으로 수정되었습니다!")
            cleanup_state()
            time.sleep(1)
            st.switch_page("pages/설문지 관리.py")

        except SQLAlchemyError as e: st.error(f"수정 중 데이터베이스 오류가 발생했습니다: {e}")
        except Exception as e: st.error(f"수정 중 알 수 없는 오류가 발생했습니다: {e}")