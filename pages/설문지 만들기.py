import streamlit as st
import time
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

st.set_page_config(page_title="설문 생성 AI", layout="wide")
conn = st.connection("postgres", type="sql")

st.markdown("""
<style>
    .stTextArea, .stTextInput { width: 100%; }
    [data-testid="stSidebarNav"] ul li a[href*="Form"] { display: none; }
    [data-testid="stSidebarNav"] ul li a[href*="Survey"] { display: none; }
</style>
""", unsafe_allow_html=True)

def initialize_state():
    if "questions" not in st.session_state:
        st.session_state.questions = []
    if "survey_title" not in st.session_state:
        st.session_state.survey_title = ""
    if "survey_desc" not in st.session_state:
        st.session_state.survey_desc = ""
    if "is_paginated" not in st.session_state:
        st.session_state.is_paginated = False
    if "current_page" not in st.session_state:
        st.session_state.current_page = 0

initialize_state()

def reset_page_on_toggle(): st.session_state.current_page = 0
def go_to_next_page():
    if st.session_state.current_page < len(st.session_state.questions) - 1: st.session_state.current_page += 1
def go_to_prev_page():
    if st.session_state.current_page > 0: st.session_state.current_page -= 1

st.markdown("""
<div style='background:linear-gradient(90deg,#5359ff 0,#6a82fb 100%);padding:24px 0 12px 0;text-align:center;color:white;border-radius:8px;'>
    <h1 style='margin-bottom:0;'>설문 생성 AI</h1>
    <div style='font-size:1.2em;'>당신은 주제만 결정하세요.<br>나머지는 AI가 도와 드립니다.</div>
</div>
""", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

edit_col, preview_col = st.columns([6, 4])

with edit_col:
    st.header("✍️ 설문 편집")
    st.markdown("---")
    
    with st.container(height=700, border=True):
        survey_topic = st.text_input("설문 주제를 입력하세요:")
        if st.button("AI로 설문 초안 생성", use_container_width=True):
            if not survey_topic.strip():
                st.warning("설문 주제를 입력해 주세요.")
            else:
                st.session_state.survey_title = f"{survey_topic}에 대한 설문"
                st.session_state.survey_desc = f"{survey_topic}에 대한 여러분의 소중한 의견을 듣고자 합니다."
                st.session_state.questions = [
                    {"title": f"{survey_topic}에 대해 얼마나 관심이 있으신가요?", "type": "라디오버튼", "options": ["매우 많음", "많음", "보통", "적음", "매우 적음"]},
                    {"title": f"{survey_topic}을(를) 알게 된 경로는 무엇인가요?", "type": "체크박스", "options": ["인터넷 검색", "지인 추천", "SNS", "광고"]},
                    {"title": f"{survey_topic}과(와) 관련해 개선되었으면 하는 점이 있나요?", "type": "인풋박스", "options": []},
                ]
                st.session_state.current_page = 0
                st.rerun()

        if st.session_state.questions:
            st.text_input("설문 제목", key="survey_title")
            st.text_area("설문 설명", key="survey_desc")
            st.checkbox("미리보기 한 장씩 보기", key="is_paginated", on_change=reset_page_on_toggle)
            st.markdown("---")
            st.subheader("생성된 설문 문항")

            for i, q_item in enumerate(st.session_state.questions):
                with st.container(border=True):
                    cols = st.columns([5, 2])
                    q_item['title'] = cols[0].text_input("문항 제목", q_item['title'], key=f"q_title_{i}")
                    q_item['type'] = cols[1].selectbox("입력 방식", ["라디오버튼", "체크박스", "인풋박스"],
                                                       index=["라디오버튼", "체크박스", "인풋박스"].index(q_item['type']),
                                                       key=f"q_type_{i}")

                    if q_item['type'] in ["라디오버튼", "체크박스"]:
                        st.markdown("###### 🔹 옵션 편집")
                        for j in range(len(q_item['options'])):
                            opt_cols = st.columns([10, 1])
                            q_item['options'][j] = opt_cols[0].text_input(f"옵션 {j+1}", value=q_item['options'][j], key=f"opt_{i}_{j}", label_visibility="collapsed")
                            if opt_cols[1].button("✖️", key=f"del_opt_{i}_{j}", use_container_width=True):
                                q_item['options'].pop(j)
                                st.rerun()

                        if st.button("➕ 옵션 추가", key=f"add_opt_{i}"):
                            q_item['options'].append(f"새 옵션 {len(q_item['options'])+1}")
                            st.rerun()
                    st.markdown("")

            if st.button("➕ 문항 추가", use_container_width=True):
                st.session_state.questions.append({"title": "새로운 질문", "type": "라디오버튼", "options": ["옵션 1", "옵션 2"]})
                st.rerun()

with preview_col:
    st.header("👁️ 실시간 미리보기")
    st.markdown("---")
    if not st.session_state.questions:
        st.info("왼쪽에서 설문 주제를 입력하고 'AI로 설문 초안 생성' 버튼을 눌러주세요.")
    else:
        with st.container(border=True):
            st.markdown(f"<h3 style='text-align: center;'>{st.session_state.survey_title}</h3>", unsafe_allow_html=True)
            st.markdown(f"<p style='text-align: center;'>{st.session_state.survey_desc}</p>", unsafe_allow_html=True)
            st.markdown("---")

            questions_to_show = [st.session_state.questions[st.session_state.current_page]] if st.session_state.is_paginated else st.session_state.questions
            
            for i, q in enumerate(questions_to_show):
                q_idx = st.session_state.current_page if st.session_state.is_paginated else i
                st.markdown(f"**Q{q_idx + 1}. {q['title']}**")
                
                if q['type'] in ["라디오버튼", "체크박스"] and not q['options']: st.warning("옵션을 추가해주세요.")
                
                if q['type'] == "라디오버튼": st.radio("응답", q['options'], key=f"p_r_{q_idx}", disabled=True, label_visibility="collapsed")
                elif q['type'] == "체크박스":
                    for k, opt in enumerate(q['options']): st.checkbox(opt, key=f"p_c_{q_idx}_{k}", disabled=True)
                elif q['type'] == "인풋박스": st.text_input("응답", key=f"p_i_{q_idx}", disabled=True, label_visibility="collapsed")
                st.markdown("---")

            if st.session_state.is_paginated:
                c1, c2 = st.columns(2)
                c1.button("이전", on_click=go_to_prev_page, use_container_width=True, disabled=(st.session_state.current_page == 0))
                c2.button("다음", on_click=go_to_next_page, use_container_width=True, disabled=(st.session_state.current_page >= len(st.session_state.questions) - 1))

if st.session_state.questions:
    _, center_col, _ = st.columns([1, 1.5, 1])
    with center_col:
        if st.button("💾 설문지 저장", use_container_width=True, type="primary"):
            if not st.session_state.survey_title:
                st.error("설문 제목을 입력해주세요.")
            else:
                try:
                    with conn.session as s:
                        survey_result = s.execute(
                            text('INSERT INTO surveys (survey_title, survey_content, page) VALUES (:title, :content, :page) RETURNING survey_id;'),
                            params=dict(title=st.session_state.survey_title, content=st.session_state.survey_desc, page=st.session_state.is_paginated)
                        )
                        survey_id = survey_result.scalar_one()

                        for q_item in st.session_state.questions:
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
                    
                    for key in ['survey_title', 'survey_desc', 'questions', 'is_paginated', 'current_page']:
                        if key in st.session_state: del st.session_state[key]
                    
                    st.success("설문지가 성공적으로 데이터베이스에 저장되었습니다!")
                    time.sleep(1); st.rerun()

                except SQLAlchemyError as e: st.error(f"데이터베이스 저장 중 오류 발생: {e}")
                except Exception as e: st.error(f"알 수 없는 오류 발생: {e}")