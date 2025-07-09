import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="설문지 관리", layout="wide")

db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_name = os.getenv("DB_NAME")

db_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

conn = st.connection("postgres", type="sql", url=db_uri)

st.markdown("""
<style>
    div[data-testid="column"] { display: flex; align-items: center; height: 55px; }
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; }
    [data-testid="stSidebarNav"] ul li a[href*="Form"] { display: none; }
    [data-testid="stSidebarNav"] ul li a[href*="Survey"] { display: none; }
</style>
""", unsafe_allow_html=True)

def get_surveys():
    try:
        query = """
            SELECT DISTINCT ON (s.survey_group_id)
                s.survey_id, s.survey_group_id, s.survey_title, s.survey_content, s.version, s.page, s.created_at
            FROM surveys s
            ORDER BY s.survey_group_id, s.version DESC;
        """
        df = conn.query(sql=query, ttl=0)
        return df
    except Exception as e:
        st.error(f"설문 목록을 불러오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

@st.dialog("설문 미리보기", width="large")
def show_preview_dialog(sid, is_paginated):
    if 'preview_page' not in st.session_state:
        st.session_state.preview_page = 0
        
    def next_page():
        st.session_state.preview_page += 1
    def prev_page():
        st.session_state.preview_page -= 1

    try:
        s_info_q = text("SELECT * FROM surveys WHERE survey_id = :id")
        i_info_q = text("SELECT * FROM survey_items WHERE survey_id = :id ORDER BY item_id ASC")
        
        with conn.session as s:
            s_info = s.execute(s_info_q, {"id": sid}).mappings().fetchone()
            i_info = s.execute(i_info_q, {"id": sid}).mappings().fetchall()

        st.markdown(f"<h3 style='text-align: center;'>{s_info['survey_title']}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center; color: grey;'>{s_info['survey_content']}</p>", unsafe_allow_html=True)
        st.markdown("---")

        questions_to_show = [i_info[st.session_state.preview_page]] if is_paginated else i_info
        
        for idx, item_row in enumerate(questions_to_show):
            q_idx = st.session_state.preview_page if is_paginated else idx
            item_id = item_row['item_id']
            st.markdown(f"**Q{q_idx + 1}. {item_row['item_title']}**")
            
            item_type = item_row['item_type']

            if item_type in ["라디오버튼", "체크박스"]:
                options_q = text("SELECT option_content FROM item_options WHERE item_id = :iid ORDER BY option_id ASC")
                with conn.session as s:
                    options_df = pd.DataFrame(s.execute(options_q, {"iid": item_id}).fetchall(), columns=['option_content'])
                
                options_list = [] if options_df.empty else options_df['option_content'].tolist()

                if not options_list: st.warning("옵션이 없습니다.")
                
                if item_type == "라디오버튼": st.radio("응답", options=options_list, key=f"preview_radio_{item_id}", disabled=True, label_visibility="collapsed")
                elif item_type == "체크박스":
                    for k, opt in enumerate(options_list): st.checkbox(opt, key=f"preview_check_{item_id}_{k}", disabled=True)
            
            elif item_type == "인풋박스":
                st.text_input("응답", key=f"preview_input_{item_id}", disabled=True, label_visibility="collapsed")
            
            st.markdown("<br>", unsafe_allow_html=True)

        if is_paginated and i_info:
            st.markdown("---")
            c1, c2 = st.columns(2)
            c1.button("이전", on_click=prev_page, use_container_width=True, disabled=(st.session_state.preview_page == 0))
            c2.button("다음", on_click=next_page, use_container_width=True, disabled=(st.session_state.preview_page >= len(i_info) - 1))

    except Exception as e:
        st.error(f"미리보기를 불러오는 중 오류가 발생했습니다: {e}")
    
    st.markdown("---")
    if st.button("닫기", use_container_width=True):
        if 'preview_page' in st.session_state:
            del st.session_state.preview_page
        st.rerun()


st.markdown("""
<div style='background:linear-gradient(90deg,#5359ff 0,#6a82fb 100%);padding:24px 0 12px 0;text-align:center;color:white;border-radius:8px;'>
    <h1 style='margin-bottom:0;'>설문지 관리</h1>
    <div style='font-size:1.2em;'>생성된 설문지를 확인, 수정, 삭제하고 결과를 확인하세요.</div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

survey_df = get_surveys()

if not survey_df.empty:
    with st.container(border=True):
        col1, col2, col3, col4, col5, col6 = st.columns([1, 4, 5, 2, 2, 2])
        col1.markdown("**버전**")
        col2.markdown("**📝 제목**")
        col3.markdown("**📄 내용**")
        col4.write("")
        col5.write("")
        col6.write("")

    for index, row in survey_df.iterrows():
        survey_id = row['survey_id']
        is_paginated = row.get('page', False)
        
        with st.container(border=True):
            col1, col2, col3, col4, col5, col6 = st.columns([1, 4, 5, 2, 2, 2])
            with col1:
                st.markdown(f"**v{row['version']}**")
            with col2:
                st.markdown(f'<div class="truncate">{row["survey_title"]}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="truncate">{row["survey_content"]}</div>', unsafe_allow_html=True)

            with col4:
                if st.button("보기", key=f"preview_{survey_id}", use_container_width=True):
                    show_preview_dialog(survey_id, is_paginated)
            with col5:
                if st.button("수정", key=f"edit_{survey_id}", use_container_width=True):
                    st.session_state['edit_survey_id'] = survey_id
                    st.switch_page("pages/_1_Form.py")
            with col6:
                if st.button("삭제", key=f"delete_{survey_id}", use_container_width=True, type="primary"):
                    st.warning(f"v{row['version']}과 관련된 모든 발송 및 응답 기록이 삭제됩니다. 정말 삭제하시겠습니까?")
                    if st.button("예, 삭제합니다", key=f"confirm_delete_{survey_id}"):
                        try:
                            with conn.session as s:
                                s.execute(text('DELETE FROM surveys WHERE survey_id = :id;'), params=dict(id=survey_id))
                                s.commit()
                            st.success(f"설문 (ID: {survey_id})이(가) 성공적으로 삭제되었습니다.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"삭제 중 오류가 발생했습니다: {e}")
else:
    st.info("현재 등록된 설문지가 없습니다. 새 설문지를 만들어주세요.")