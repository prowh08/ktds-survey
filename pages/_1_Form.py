import streamlit as st
import time
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()  # 환경변수 불러오기
st.set_page_config(page_title="설문 수정", layout="wide", initial_sidebar_state="collapsed")

# db connection setup
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

db_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

conn = st.connection("postgres", type="sql", url=db_uri)

st.markdown("""
<style>
    .stTextArea, .stTextInput { width: 100%; }
    [data-testid="stSidebarNav"] ul li a[href*="Form"] { display: none; }
    [data-testid="stSidebarNav"] ul li a[href*="Survey"] { display: none; }
    
</style>
""", unsafe_allow_html=True)

def initialize_edit_state():
    for key in ['edit_title', 'edit_desc', 'edit_questions', 'is_paginated', 'current_page']:
        if key not in st.session_state:
            st.session_state[key] = "" if "title" in key or "desc" in key else [] if "questions" in key else False if "paginated" in key else 0

def load_data_for_edit(survey_id):
    try:
        survey_info = conn.query(f"SELECT survey_title, survey_content, page FROM surveys WHERE survey_id={survey_id}", ttl=0).iloc[0]
        st.session_state.edit_title = survey_info['survey_title']
        st.session_state.edit_desc = survey_info['survey_content']
        st.session_state.is_paginated = survey_info['page']

        items_df = conn.query(f"SELECT item_id, item_title, item_type FROM survey_items WHERE survey_id={survey_id}", ttl=0)
        
        questions_list = []
        for _, item_row in items_df.iterrows():
            q_item = {"title": item_row['item_title'], "type": item_row['item_type'], "options": []}
            
            if q_item['type'] in ["라디오버튼", "체크박스"]:
                options_df = conn.query(f"SELECT option_content FROM item_options WHERE item_id={item_row['item_id']}", ttl=0)
                q_item['options'] = options_df['option_content'].tolist()
            
            questions_list.append(q_item)

        st.session_state.edit_questions = questions_list
        st.session_state.current_page = 0
        st.session_state.data_loaded = True

    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}"); st.stop()

if 'edit_survey_id' not in st.session_state:
    st.warning("잘못된 접근입니다. 설문 관리 페이지에서 수정할 항목을 선택해주세요.")
    if st.button("관리 페이지로 돌아가기"): st.switch_page("pages/설문지 관리.py")
    st.stop()

if not st.session_state.get('data_loaded', False):
    initialize_edit_state()
    load_data_for_edit(st.session_state.edit_survey_id)

def reset_page_on_toggle(): st.session_state.current_page = 0
def go_to_next_page():
    if st.session_state.current_page < len(st.session_state.edit_questions) - 1: st.session_state.current_page += 1
def go_to_prev_page():
    if st.session_state.current_page > 0: st.session_state.current_page -= 1

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

        for i, q_item in enumerate(st.session_state.edit_questions):
            with st.container(border=True):
                cols = st.columns([5, 2])
                q_item['title'] = cols[0].text_input("문항 제목", q_item['title'], key=f"edit_q_title_{i}")
                q_item['type'] = cols[1].selectbox("입력 방식", ["라디오버튼", "체크박스", "인풋박스"],
                                                   index=["라디오버튼", "체크박스", "인풋박스"].index(q_item['type']),
                                                   key=f"edit_q_type_{i}")

                if q_item['type'] in ["라디오버튼", "체크박스"]:
                    st.markdown("###### 🔹 옵션 편집")
                    for j in range(len(q_item['options'])):
                        opt_cols = st.columns([10, 1])
                        q_item['options'][j] = opt_cols[0].text_input(f"옵션 {j+1}", value=q_item['options'][j], key=f"edit_opt_{i}_{j}", label_visibility="collapsed")
                        if opt_cols[1].button("✖️", key=f"edit_del_opt_{i}_{j}", use_container_width=True):
                            q_item['options'].pop(j)
                            st.rerun()

                    if st.button("➕ 옵션 추가", key=f"edit_add_opt_{i}"):
                        q_item['options'].append(f"새 옵션 {len(q_item['options'])+1}")
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
        cleanup_state(); st.switch_page("pages/설문지 관리.py")

with center_col:
    if st.button("💾 수정 완료", use_container_width=True, type="primary"):
        try:
            with conn.session as s:
                survey_id = st.session_state.edit_survey_id
                s.execute(
                    text('UPDATE surveys SET survey_title = :title, survey_content = :content, page = :page, edit_at = CURRENT_TIMESTAMP WHERE survey_id = :id;'),
                    params=dict(title=st.session_state.edit_title, content=st.session_state.edit_desc, page=st.session_state.is_paginated, id=survey_id)
                )
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
            cleanup_state(); time.sleep(1); st.switch_page("pages/설문지 관리.py")

        except SQLAlchemyError as e: st.error(f"수정 중 데이터베이스 오류가 발생했습니다: {e}")
        except Exception as e: st.error(f"수정 중 알 수 없는 오류가 발생했습니다: {e}")