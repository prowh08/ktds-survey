import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

st.set_page_config(page_title="설문지 관리", layout="wide")
conn = st.connection("postgres", type="sql")

st.markdown("""
<style>
    div[data-testid="column"] {
        display: flex;
        align-items: center;
        height: 55px;
    }
    .truncate {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        width: 100%;
    }
    [data-testid="stSidebarNav"] ul li a[href*="Form"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

def get_surveys():
    try:
        query = "SELECT survey_id, survey_title, survey_content, created_at FROM surveys ORDER BY created_at DESC;"
        df = conn.query(sql=query, ttl=0)
        return df
    except Exception as e:
        st.error(f"설문 목록을 불러오는 중 오류가 발생했습니다: {e}")
        return pd.DataFrame()

st.markdown("""
<div style='background:linear-gradient(90deg,#5359ff 0,#6a82fb 100%);padding:24px 0 12px 0;text-align:center;color:white;border-radius:8px;'>
    <h1 style='margin-bottom:0;'>설문지 관리</h1>
    <div style='font-size:1.2em;'>생성된 설문지를 확인, 수정, 삭제하고 결과를 확인하세요.</div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

if st.button("🔄 목록 새로고침"):
    st.rerun()

survey_df = get_surveys()

if not survey_df.empty:
    with st.container(border=True):
        col1, col2, col3, col4, col5 = st.columns([2, 3, 1, 1, 1])
        col1.markdown("**📝 제목**")
        col2.markdown("**📄 내용**")
        col3.write("")
        col4.write("")
        col5.write("")

    for index, row in survey_df.iterrows():
        survey_id = row['survey_id']
        with st.container(border=True):
            col1, col2, col3, col4, col5 = st.columns([2, 3, 1, 1, 1])
            with col1:
                st.markdown(f'<div class="truncate">{row["survey_title"]}</div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="truncate">{row["survey_content"]}</div>', unsafe_allow_html=True)

            with col3:
                @st.dialog("설문 미리보기", width="large")
                def show_preview_dialog(sid):
                    try:
                        s_info = conn.query(f"SELECT * FROM surveys WHERE survey_id={sid}", ttl=0).iloc[0]
                        i_info = conn.query(f"SELECT * FROM survey_items WHERE survey_id={sid}", ttl=0)

                        st.markdown(f"### {s_info['survey_title']}")
                        st.markdown(f"{s_info['survey_content']}")
                        st.markdown("---")
                        for _, item_row in i_info.iterrows():
                            st.markdown(f"**Q. {item_row['item_title']}** ({item_row['item_type']})")

                    except Exception as e:
                        st.error(f"미리보기를 불러오는 중 오류 발생: {e}")

                if st.button("보기", key=f"preview_{survey_id}", use_container_width=True):
                    show_preview_dialog(survey_id)

            with col4:
                if st.button("수정", key=f"edit_{survey_id}", use_container_width=True):
                    st.session_state['edit_survey_id'] = survey_id
                    st.switch_page("pages/_1_Form.py")

            with col5:
                if st.button("삭제", key=f"delete_{survey_id}", use_container_width=True, type="primary"):
                    try:
                        with conn.session as s:
                            s.execute(text('DELETE FROM surveys WHERE survey_id = :id;'), params=dict(id=survey_id))
                            s.commit()
                        st.success(f"설문 (ID: {survey_id})이(가) 성공적으로 삭제되었습니다.")
                        st.rerun()
                    except SQLAlchemyError as e:
                        st.error(f"삭제 중 데이터베이스 오류가 발생했습니다: {e}")
                    except Exception as e:
                        st.error(f"삭제 중 알 수 없는 오류가 발생했습니다: {e}")
else:
    st.info("현재 등록된 설문지가 없습니다. 새 설문지를 만들어주세요.")