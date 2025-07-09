# 설문지 관리.py

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
                s.survey_id, s.survey_title, s.survey_content, s.created_at, s.version
            FROM surveys s
            ORDER BY s.survey_group_id, s.version DESC;
        """
        df = conn.query(sql=query, ttl=0)
        return df
    except Exception as e:
        st.error(f"설문 목록을 불러오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

def create_new_survey_version(survey_id_to_copy_from):
    try:
        with conn.session as s:
            old_survey_q = text("SELECT * FROM surveys WHERE survey_id = :sid")
            old_survey = s.execute(old_survey_q, {"sid": survey_id_to_copy_from}).fetchone()
            if not old_survey:
                st.error("원본 설문을 찾을 수 없습니다.")
                return None

            group_id = old_survey.survey_group_id
            latest_version_q = text("SELECT MAX(version) FROM surveys WHERE survey_group_id = :gid")
            latest_version = s.execute(latest_version_q, {"gid": group_id}).scalar_one()
            new_version = latest_version + 1
            
            new_survey_q = text("""
                INSERT INTO surveys (survey_group_id, version, survey_title, survey_content, page)
                VALUES (:gid, :ver, :title, :content, :page) RETURNING survey_id;
            """)
            new_survey_id = s.execute(new_survey_q, {
                "gid": group_id, "ver": new_version, "title": old_survey.survey_title,
                "content": old_survey.survey_content, "page": old_survey.page
            }).scalar_one()

            old_items_q = text("SELECT item_id, item_title, item_type FROM survey_items WHERE survey_id = :sid ORDER BY item_id")
            old_items = s.execute(old_items_q, {"sid": survey_id_to_copy_from}).mappings().fetchall()

            for item in old_items:
                new_item_q = text("INSERT INTO survey_items (survey_id, item_title, item_type) VALUES (:sid, :title, :type) RETURNING item_id;")
                new_item_id = s.execute(new_item_q, {"sid": new_survey_id, "title": item['item_title'], "type": item['item_type']}).scalar_one()

                old_options_q = text("SELECT option_content FROM item_options WHERE item_id = :iid ORDER BY option_id")
                old_options = s.execute(old_options_q, {"iid": item['item_id']}).mappings().fetchall()
                for option in old_options:
                    s.execute(text("INSERT INTO item_options (item_id, option_content) VALUES (:iid, :content);"), {"iid": new_item_id, "content": option['option_content']})
            
            s.commit()
            st.toast(f"'{old_survey.survey_title}'의 새 버전(v{new_version})이 생성되었습니다.")
            return new_survey_id
    except Exception as e:
        st.error(f"새로운 버전을 생성하는 중 오류 발생: {e}")
        return None


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
        col1, col2, col3, col4, col5 = st.columns([1, 4, 6, 2, 2])
        col1.markdown("**버전**")
        col2.markdown("**📝 제목**")
        col3.markdown("**📄 내용**")
        col4.write("")
        col5.write("")

    for index, row in survey_df.iterrows():
        survey_id = row['survey_id']
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([1, 4, 6, 2, 2])
            with col1:
                st.markdown(f"**v{row['version']}**")
            with col2:
                st.markdown(f'<div class="truncate">{row["survey_title"]}</div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="truncate">{row["survey_content"]}</div>', unsafe_allow_html=True)

            with col4:
                if st.button("수정", key=f"edit_{survey_id}", use_container_width=True):
                    new_survey_id = create_new_survey_version(survey_id)
                    if new_survey_id:
                        st.session_state['edit_survey_id'] = new_survey_id
                        st.switch_page("pages/_1_Form.py")
            with col5:
                if st.button("삭제", key=f"delete_{survey_id}", use_container_width=True, type="primary"):
                    st.warning("이 버전과 관련된 모든 발송 및 응답 기록이 삭제됩니다. 정말 삭제하시겠습니까?")
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