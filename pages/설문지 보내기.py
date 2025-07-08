import streamlit as st
import pandas as pd
import urllib.parse
from datetime import datetime, timedelta, time
import time
import uuid
import json
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

st.set_page_config(page_title="설문지 보내기", layout="wide")
conn = st.connection("postgres", type="sql")

st.markdown("""
<style>
    div[data-testid="column"] { display: flex; align-items: center; height: 55px; }
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; }
    
    [data-testid="stSidebarNav"] ul li a[href*="Form"] { display: none; }
    [data-testid="stSidebarNav"] ul li a[href*="Survey"] { display: none; }
</style>
""", unsafe_allow_html=True)

if "show_status_survey_id" not in st.session_state:
    st.session_state.show_status_survey_id = None
if "active_dialog" not in st.session_state:
    st.session_state.active_dialog = None

def get_surveys_from_db():
    return conn.query("SELECT survey_id, survey_title, survey_content FROM surveys ORDER BY created_at DESC;", ttl=0)

def get_sends_from_db(survey_id):
    df = conn.query(
        f"SELECT send_id, scheduled_at, status, recipients FROM survey_sends WHERE survey_id = {survey_id} ORDER BY scheduled_at DESC;", ttl=0
    )
    return df

def get_completed_users(_conn, survey_id):
    """DB에서 특정 설문의 응답을 완료한 사용자의 이메일과 응답 시간을 가져옵니다."""
    query = f"""
        SELECT email, completed_at
        FROM survey_results
        WHERE survey_id = :survey_id AND status = 'completed' AND email IS NOT NULL;
    """
    df = _conn.query(sql=query,params={"survey_id": survey_id})
    if not df.empty:
        df = df.rename(columns={"email": "이메일"})
    return df

@st.dialog("설문 보내기/수정", width="large")
def show_send_edit_dialog():
    dialog_info = st.session_state.active_dialog
    if not dialog_info: return
    survey_id = dialog_info["survey_id"]
    is_edit_mode = dialog_info.get("mode") == "edit"
    dialog_state_key = f"dialog_state_{dialog_info['key']}"
    if dialog_state_key not in st.session_state:
        initial_state = {"df": None, "scheduled_dt": datetime.now() + timedelta(minutes=10)}
        if is_edit_mode:
            send_item = dialog_info["send_item"]
            recipients_df = pd.DataFrame(send_item.get('recipients', []))
            initial_state["df"] = recipients_df[['이메일']].copy() if '이메일' in recipients_df.columns else pd.DataFrame(columns=['이메일'])
            initial_state["scheduled_dt"] = pd.to_datetime(send_item['scheduled_at'])
        st.session_state[dialog_state_key] = initial_state
    dialog_state = st.session_state[dialog_state_key]
    if not is_edit_mode and dialog_state["df"] is None:
        exl_file = st.file_uploader("발송 대상 엑셀 파일 업로드", type=["xlsx"], key=f"upload_{dialog_state_key}")
        if exl_file:
            try:
                df = pd.read_excel(exl_file)
                email_col = next((col for col in df.columns if "email" in col.lower() or "이메일" in col), None)
                if email_col:
                    dialog_state["df"] = df[[email_col]].rename(columns={email_col: "이메일"})
                    st.rerun()
                else: st.error("엑셀 파일에 '이메일' 또는 'email' 컬럼이 없습니다.")
            except Exception as e: st.error(f"파일 처리 중 오류 발생: {e}")
    else:
        st.info("발송 대상을 확인하고 수정할 수 있습니다.")
        dialog_state["df"] = st.data_editor(dialog_state["df"], use_container_width=True, num_rows="dynamic")
        st.markdown("---"); st.subheader("발송 시간 예약")
        d = st.date_input("발송 날짜", value=dialog_state["scheduled_dt"].date())
        t = st.time_input("발송 시간", value=dialog_state["scheduled_dt"].time())
        scheduled_dt = datetime.combine(d, t)
        st.markdown("---")
        button_label = "수정 완료" if is_edit_mode else "보내기 (예약)"
        if st.button(button_label, use_container_width=True, type="primary"):
            if scheduled_dt < datetime.now():
                st.error("발송 시간은 현재 시간보다 미래여야 합니다.")
            else:
                base_url = f"http://localhost:8501/Survey_Response?survey_id={survey_id}"
                dialog_state["df"]["설문 URL"] = dialog_state["df"]["이메일"].apply(lambda x: f"{base_url}&email={urllib.parse.quote(str(x))}")
                recipients_json = dialog_state["df"].to_json(orient='records', force_ascii=False)

                try:
                    with conn.session as s:
                        if is_edit_mode:
                            send_id = dialog_info['send_item']['send_id']
                            s.execute(text("UPDATE survey_sends SET scheduled_at = :dt, status = '발송 예약', recipients = :recip WHERE send_id = :id;"), params=dict(dt=scheduled_dt, recip=recipients_json, id=send_id))
                            st.success("예약 정보가 성공적으로 수정되었습니다.")
                        else:
                            new_send_id = uuid.uuid4()
                            s.execute(
                                text("INSERT INTO survey_sends (send_id, survey_id, scheduled_at, status, recipients) VALUES (:send_id, :sid, :dt, '발송 예약', :recip);"),
                                params=dict(send_id=new_send_id, sid=survey_id, dt=scheduled_dt, recip=recipients_json)
                            )
                            st.success("새로운 설문 발송이 예약되었습니다.")
                        s.commit()
                    st.session_state.active_dialog = None
                    st.session_state.show_status_survey_id = survey_id
                    del st.session_state[dialog_state_key]
                    time.sleep(1); st.rerun()
                except SQLAlchemyError as e: st.error(f"DB 작업 중 오류 발생: {e}")
                except Exception as e: st.error(f"오류 발생: {e}")
    if st.button("닫기"):
        st.session_state.active_dialog = None
        if dialog_state_key in st.session_state: del st.session_state[dialog_state_key]
        st.rerun()

def handle_button_click(action, **kwargs):
    st.session_state.active_dialog = None
    if action == "show_status":
        survey_id = kwargs.get("survey_id")
        st.session_state.show_status_survey_id = None if st.session_state.show_status_survey_id == survey_id else survey_id
    elif action in ["new_send", "edit_send"]:
        st.session_state.active_dialog = {"mode": "edit" if action == "edit_send" else "new", **kwargs}
    elif action == "cancel_send":
        try:
            with conn.session as s:
                s.execute(text("UPDATE survey_sends SET status = '예약 취소' WHERE send_id = :id;"), params=kwargs)
                s.commit()
            st.success("발송 예약을 취소했습니다.")
        except Exception as e: st.error(f"예약 취소 중 오류 발생: {e}")

st.markdown("""
<div style='background:linear-gradient(90deg,#5359ff 0,#6a82fb 100%);padding:24px 0 12px 0;text-align:center;color:white;border-radius:8px;'>
    <h1 style='margin-bottom:0;'>설문지 보내기</h1>
    <div style='font-size:1.2em;'>생성한 설문지를 확인하고 발송 현황을 추적합니다.</div>
</div>
""", unsafe_allow_html=True)
st.markdown("")
if st.session_state.active_dialog:
    show_send_edit_dialog()
survey_df = get_surveys_from_db()

if not survey_df.empty:
    for _, survey in survey_df.iterrows():
        survey_id = survey["survey_id"]
        send_history_df = get_sends_from_db(survey_id)
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([4, 2, 1.5, 1.5])
            with col1: st.markdown(f"**{survey['survey_title']}**"); st.caption(survey.get("survey_content", ""))
            with col2: st.metric(label="총 발송 횟수", value=f"{len(send_history_df)} 회")
            with col3:
                st.button("새로 보내기", key=f"send_{survey_id}", use_container_width=True, on_click=handle_button_click, args=("new_send",), kwargs={"survey_id": survey_id, "key": f"new_{survey_id}"})
            with col4:
                st.button("발송 현황 보기", key=f"status_{survey_id}", use_container_width=True, disabled=send_history_df.empty, on_click=handle_button_click, args=("show_status",), kwargs={"survey_id": survey_id})
        if st.session_state.show_status_survey_id == survey_id:
            st.write("---"); st.subheader(f"'{survey['survey_title']}' 발송 기록")
            for _, send_item in send_history_df.iterrows():
                with st.container(border=True):
                    scheduled_time = pd.to_datetime(send_item['scheduled_at'])
                    recipients_df = pd.DataFrame(send_item.get('recipients', []))
                    total = len(recipients_df)
                    completed_users_df = get_completed_users(conn, survey_id)
                    completed_emails = completed_users_df['이메일'].tolist() if not completed_users_df.empty else []
                    responded = recipients_df['이메일'].isin(completed_emails).sum() if not recipients_df.empty else 0
                    current_status = send_item.get("status", "N/A")
                    if current_status == "발송 예약" and scheduled_time < datetime.now(): current_status = "발송 완료"
                    if current_status == "발송 완료" and total > 0 and responded == total: current_status = "응답 완료"
                    is_editable = current_status in ["발송 예약", "예약 취소"]
                    is_cancelable = current_status == "발송 예약"
                    status_cols = st.columns([3, 1, 1])
                    with status_cols[0]:
                        percent = (responded / total * 100) if total > 0 else 0
                        st.write(f"**상태:** {current_status} | **예약:** {scheduled_time.strftime('%Y-%m-%d %H:%M')} | **응답률:** {responded}/{total} 명 ({percent:.1f}%)")
                    with status_cols[1]:
                        st.button("수정", key=f"edit_{send_item['send_id']}", use_container_width=True, disabled=not is_editable, on_click=handle_button_click, args=("edit_send",), kwargs={"survey_id": survey_id, "send_item": send_item.to_dict(), "key": f"edit_{send_item['send_id']}"})
                    with status_cols[2]:
                        st.button("예약 취소", key=f"cancel_{send_item['send_id']}", use_container_width=True, disabled=not is_cancelable, on_click=handle_button_click, args=("cancel_send",), kwargs={"id": send_item['send_id']})
                    with st.expander("상세 대상자 목록 보기"):
                        if not recipients_df.empty:
                            if not completed_users_df.empty:
                                display_df = pd.merge(recipients_df, completed_users_df, on="이메일", how="left")
                            else:
                                display_df = recipients_df.copy()
                                display_df['completed_at'] = pd.NaT
                            
                            display_df['응답 여부'] = display_df['completed_at'].apply(lambda x: '완료' if pd.notna(x) else '미완료')
                            display_df['응답 시간'] = pd.to_datetime(display_df['completed_at']).dt.strftime('%Y-%m-%d %H:%M').fillna('')
                            st.dataframe(display_df[['이메일', '설문 URL', '응답 여부', '응답 시간']], hide_index=True, use_container_width=True)
                            
            st.write("")
else:
    st.info("먼저 '설문지 만들기'에서 설문을 생성해주세요.")