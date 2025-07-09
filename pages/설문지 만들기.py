import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from openai import AzureOpenAI
import json
import openai
import os
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="설문 생성 AI", layout="wide")

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
        당신은 주어진 키워드나 주제에 대해, 사람들이 응답하기 좋은 전문적인 설문지를 설계하는 AI 전문가입니다.
        당신의 임무는 설문의 목적을 명확히 하고, 논리적인 흐름에 따라 다양한 유형의 질문과 선택지를 구성하는 것입니다.
        출력은 반드시 지정된 JSON 형식이어야 합니다.
        """
    }

def create_user_prompt(keyword):
    return {
        "role": "user",
        "content": f"""
            '키워드': "{keyword}"

            위 키워드를 바탕으로 전문적인 설문지를 생성해 주세요. 다음 규칙을 반드시 따라야 합니다.

            ### 규칙
            1.  **출력 형식**: 반드시 아래에 명시된 구조를 따르는 JSON 객체로만 응답해야 합니다. 코드 블록(```json ... ```)으로 감싸지 않은 순수 JSON 텍스트여야 합니다.
            2.  **JSON 구조**:
                - 최상위 객체는 `survey_title`, `survey_desc`, `questions` 키를 가집니다.
                - `questions`는 각 문항 객체들을 담는 배열(리스트)입니다.
                - 각 문항 객체는 `title`(질문), `type`(유형), `options`(선택지) 키를 가집니다.
            3.  **질문 유형 (`type`)**: 반드시 "라디오버튼", "체크박스", "인풋박스" 세 가지 중 하나만 사용해야 합니다.
            4.  **선택지 (`options`)**:
                - "라디오버튼"과 "체크박스"는 4~5개의 선택지를 포함해야 합니다.
                - "인풋박스"는 항상 빈 배열 `[]` 이어야 합니다.
            5.  **문항 구성**: 전체 문항은 5개에서 7개 사이로 구성해주세요. 주관식(인풋박스) 문항을 1~2개 포함해주세요.
            6.  **언어**: 모든 키와 값은 반드시 한국어로 작성해야 합니다.

            ### JSON 출력 형식 및 예시
            ```json
            {{
                "survey_title": "회사 구내식당 만족도 설문",
                "survey_desc": "더 나은 식사 환경과 메뉴 품질 개선을 위해 구내식당 이용에 대한 임직원 여러분의 소중한 의견을 듣고자 합니다.",
                "questions": [
                    {{
                        "title": "구내식당을 얼마나 자주 이용하시나요?",
                        "type": "라디오버튼",
                        "options": [
                            "주 4~5회",
                            "주 2~3회",
                            "주 1회",
                            "거의 이용하지 않음"
                        ]
                    }},
                    {{
                        "title": "현재 구내식당 메뉴의 가장 만족스러운 점은 무엇인가요? (모두 선택)",
                        "type": "체크박스",
                        "options": [
                            "맛",
                            "가격",
                            "다양성",
                            "영양",
                            "위생"
                        ]
                    }},
                    {{
                        "title": "앞으로 추가되었으면 하는 메뉴나 서비스가 있다면 자유롭게 작성해주세요.",
                        "type": "인풋박스",
                        "options": []
                    }}
                ]
            }}
            """
    }

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
    if "generating" not in st.session_state:
        st.session_state.generating = False
    if "saving" not in st.session_state:
        st.session_state.saving = False

initialize_state()

is_busy = st.session_state.generating or st.session_state.saving

def reset_page_on_toggle():
    st.session_state.current_page = 0

def go_to_next_page():
    if st.session_state.current_page < len(st.session_state.questions) - 1:
        st.session_state.current_page += 1

def go_to_prev_page():
    if st.session_state.current_page > 0:
        st.session_state.current_page -= 1

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

    with st.container(height=1500, border=True):
        survey_topic = st.text_input("설문 주제를 입력하세요:", disabled=is_busy)
        if st.button("AI로 설문 초안 생성", use_container_width=True, disabled=is_busy):
            if not survey_topic.strip():
                st.warning("설문 주제를 입력해 주세요.")
            else:
                st.session_state.generating = True
                st.rerun()

        if st.session_state.generating:
            with st.spinner("AI가 설문 초안을 생성 중입니다... 잠시만 기다려주세요."):
                try:
                    prompt_messages = [system_message, create_user_prompt(survey_topic)]
                    response = client.chat.completions.create(
                        model=openai_deployment,
                        temperature=0.9, max_tokens=500, messages=prompt_messages
                    )
                    if response.choices:
                        choice = response.choices[0]
                        if choice.finish_reason == "content_filter":
                            st.error("🚨 AI가 생성한 답변이 콘텐츠 정책에 위배되어 차단되었습니다.")
                        elif choice.message.content is None:
                            st.error("AI가 답변을 생성하지 못했습니다.")
                        else:
                            survey_data = json.loads(choice.message.content)
                            st.session_state.survey_title = survey_data['survey_title']
                            st.session_state.survey_desc = survey_data['survey_desc']
                            st.session_state.questions = survey_data['questions']
                            st.session_state.current_page = 0
                    else: st.error("AI로부터 유효한 응답을 받지 못했습니다.")
                except Exception as e: st.error(f"알 수 없는 오류가 발생했습니다: {e}")
                finally:
                    st.session_state.generating = False
                    st.rerun()

        if st.session_state.questions:
            st.text_input("설문 제목", key="survey_title", disabled=is_busy)
            st.text_area("설문 설명", key="survey_desc", disabled=is_busy)
            st.markdown("---")
            st.subheader("생성된 설문 문항")
            
            for i in range(len(st.session_state.questions)):
                with st.container(border=True):
                    current_question = st.session_state.questions[i]
                    
                    header_cols = st.columns([0.8, 0.2])
                    with header_cols[0]: st.markdown(f"**문항 {i+1}**")
                    with header_cols[1]:
                        if st.button("문항 삭제", key=f"del_q_{i}", use_container_width=True, type="primary"):
                            st.session_state.questions.pop(i)
                            st.rerun()

                    current_question['title'] = st.text_input("문항 제목", current_question['title'], key=f"q_title_{i}", disabled=is_busy, label_visibility="collapsed")
                    
                    old_type = current_question['type']
                    selected_type = st.selectbox(
                        "입력 방식", ["라디오버튼", "체크박스", "인풋박스"],
                        index=["라디오버튼", "체크박스", "인풋박스"].index(old_type),
                        key=f"q_type_{i}", disabled=is_busy
                    )
                    
                    if selected_type != old_type:
                        st.session_state.questions[i]['type'] = selected_type
                        st.rerun()

                    if current_question['type'] in ["라디오버튼", "체크박스"]:
                        st.markdown("###### 🔹 옵션 편집")
                        for j in range(len(current_question['options'])):
                            opt_cols = st.columns([10, 1])
                            current_question['options'][j] = opt_cols[0].text_input(
                                f"옵션 {j+1}", value=current_question['options'][j], 
                                key=f"opt_{i}_{j}", label_visibility="collapsed", disabled=is_busy
                            )
                            if opt_cols[1].button("✖️", key=f"del_opt_{i}_{j}", use_container_width=True, disabled=is_busy):
                                current_question['options'].pop(j)
                                st.rerun()

                        if st.button("➕ 옵션 추가", key=f"add_opt_{i}", disabled=is_busy):
                            current_question['options'].append(f"새 옵션 {len(current_question['options'])+1}")
                            st.rerun()
                    st.markdown("")

            if st.button("➕ 문항 추가", use_container_width=True, disabled=is_busy):
                st.session_state.questions.append({"title": "새로운 질문", "type": "라디오버튼", "options": ["옵션 1", "옵션 2"]})
                st.rerun()

with preview_col:
    st.header("👁️ 설문지 미리보기")
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
                c1.button("이전", on_click=go_to_prev_page, use_container_width=True, disabled=(st.session_state.current_page == 0 or is_busy))
                c2.button("다음", on_click=go_to_next_page, use_container_width=True, disabled=(st.session_state.current_page >= len(st.session_state.questions) - 1 or is_busy))

if st.session_state.questions:
    _, center_col, _ = st.columns([1, 1.5, 1])
    with center_col:
        if st.button("💾 설문지 저장", use_container_width=True, type="primary", disabled=is_busy):
            if not st.session_state.survey_title: st.error("설문 제목을 입력해주세요.")
            else: st.session_state.saving = True; st.rerun()

if st.session_state.saving:
    with st.spinner("설문지를 저장 중입니다..."):
        try:
            with conn.session as s:
                next_id_q = text("SELECT nextval('surveys_survey_id_seq')")
                new_survey_id = s.execute(next_id_q).scalar_one()
                insert_survey_q = text("""
                    INSERT INTO surveys (survey_id, survey_group_id, survey_title, survey_content, page, version)
                    VALUES (:id, :gid, :title, :content, :page, 1);
                """)
                s.execute(insert_survey_q, params=dict(id=new_survey_id, gid=new_survey_id, title=st.session_state.survey_title, content=st.session_state.survey_desc, page=st.session_state.is_paginated))
                for q_item in st.session_state.questions:
                    item_result = s.execute(
                        text('INSERT INTO survey_items (survey_id, item_title, item_type) VALUES (:sid, :title, :type) RETURNING item_id;'),
                        params=dict(sid=new_survey_id, title=q_item['title'], type=q_item['type'])
                    )
                    item_id = item_result.scalar_one()
                    if q_item['type'] in ["라디오버튼", "체크박스"]:
                        for option_content in q_item['options']:
                            s.execute(text('INSERT INTO item_options (item_id, option_content) VALUES (:iid, :content);'), params=dict(iid=item_id, content=option_content))
                s.commit()
            for key in ['survey_title', 'survey_desc', 'questions', 'is_paginated', 'current_page', 'saving']:
                if key in st.session_state: del st.session_state[key]
            st.switch_page("pages/설문지 관리.py")
        except SQLAlchemyError as e: st.error(f"DB 저장 오류: {e}"); st.session_state.saving = False; st.rerun()
        except Exception as e: st.error(f"알 수 없는 오류: {e}"); st.session_state.saving = False; st.rerun()