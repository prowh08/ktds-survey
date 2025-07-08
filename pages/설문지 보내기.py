import streamlit as st
import pandas as pd
import urllib.parse
from datetime import datetime, timedelta, time
import time
import uuid
import random

st.markdown("""
<style>
    div[data-testid="column"] { display: flex; align-items: center; height: 55px; }
    .truncate { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%; }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="설문지 보내기", layout="wide")

if "survey_list" not in st.session_state:
    st.session_state.survey_list = [
        {"title": "1분기 고객 만족도 설문", "desc": "서비스 개선을 위한 의견"},
        {"title": "신제품 아이디어 공모", "desc": "채택된 아이디어에는 특별한 혜택"}
    ]
if "send_history" not in st.session_state:
    st.session_state.send_history = []
if "show_status_title" not in st.session_state:
    st.session_state.show_status_title = None
if "active_dialog" not in st.session_state:
    st.session_state.active_dialog = None


@st.dialog("설문 보내기/수정", width="large")
def show_send_edit_dialog():
    dialog_info = st.session_state.active_dialog
    if not dialog_info: return

    survey_data = dialog_info["survey"]
    is_edit_mode = dialog_info.get("mode") == "edit"
    dialog_state_key = f"dialog_state_{dialog_info['key']}"

    if dialog_state_key not in st.session_state:
        if is_edit_mode:
            send_item = dialog_info["send_item"]
            st.session_state[dialog_state_key] = {
                "df": send_item['data'][['이메일']].copy(),
                "scheduled_dt": datetime.strptime(send_item['scheduled_time'], "%Y-%m-%d %H:%M:%S")
            }
        else:
            st.session_state[dialog_state_key] = {"df": None, "scheduled_dt": datetime.now() + timedelta(minutes=10)}

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
                else: st.error("엑셀 파일에 이메일 컬럼이 없습니다.")
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
            if scheduled_dt < datetime.now() and not is_edit_mode:
                st.error("발송 시간은 현재 시간보다 미래여야 합니다.")
            else:
                base_url = "https://your-survey-url.com/form"
                dialog_state["df"]["설문 URL"] = dialog_state["df"]["이메일"].apply(lambda x: f"{base_url}?email={urllib.parse.quote(str(x))}")

                if is_edit_mode:
                    for i, item in enumerate(st.session_state.send_history):
                        if item['send_id'] == dialog_info['send_item']['send_id']:
                            st.session_state.send_history[i].update({
                                "data": dialog_state["df"], "scheduled_time": scheduled_dt.strftime("%Y-%m-%d %H:%M:%S"),
                                "total": len(dialog_state["df"]), "status": "발송 예약"
                            })
                            break
                    st.success("예약 정보가 성공적으로 수정되었습니다.")
                else:
                    st.session_state.send_history.append({
                        "send_id": str(uuid.uuid4()), "survey_title": survey_data["title"], "data": dialog_state["df"],
                        "scheduled_time": scheduled_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "total": len(dialog_state["df"]), "responded": 0,
                        "status": "발송 예약"
                    })
                    st.success("새로운 설문 발송이 예약되었습니다.")

                st.session_state.active_dialog = None
                st.session_state.show_status_title = survey_data["title"]
                del st.session_state[dialog_state_key]
                time.sleep(1); st.rerun()

    if st.button("닫기"):
        st.session_state.active_dialog = None
        if dialog_state_key in st.session_state: del st.session_state[dialog_state_key]
        st.rerun()

def handle_button_click(action, **kwargs):
    """모든 버튼 클릭 이벤트를 중앙에서 관리하는 함수"""
    st.session_state.active_dialog = None

    if action == "show_status":
        survey_title = kwargs.get("survey_title")
        if st.session_state.show_status_title == survey_title:
            st.session_state.show_status_title = None
        else:
            st.session_state.show_status_title = survey_title

    elif action == "new_send":
        st.session_state.show_status_title = None
        st.session_state.active_dialog = {"mode": "new", "survey": kwargs.get("survey"), "key": kwargs.get("key")}

    elif action == "edit_send":
        st.session_state.show_status_title = None
        st.session_state.active_dialog = {"mode": "edit", "survey": kwargs.get("survey"), "send_item": kwargs.get("send_item"), "key": kwargs.get("key")}

    elif action == "cancel_send":
        send_id = kwargs.get("send_id")
        for i, item in enumerate(st.session_state.send_history):
            if item['send_id'] == send_id:
                st.session_state.send_history[i]['status'] = "예약 취소"
                break
        st.success("발송 예약을 취소했습니다.")
        time.sleep(1)

st.markdown("""
<div style='background:linear-gradient(90deg,#5359ff 0,#6a82fb 100%);padding:24px 0 12px 0;text-align:center;color:white;border-radius:8px;'>
    <h1 style='margin-bottom:0;'>설문지 보내기</h1>
    <div style='font-size:1.2em;'>생성한 설문지를 확인하고 발송 현황을 추적합니다.</div>
</div>
""", unsafe_allow_html=True)
st.markdown("")

if st.session_state.active_dialog:
    show_send_edit_dialog()

if st.session_state.survey_list:
    for idx, survey in enumerate(st.session_state.survey_list):
        survey_title = survey["title"]
        related_sends = [s for s in st.session_state.send_history if s["survey_title"] == survey_title]

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([4, 2, 1.5, 1.5])
            with col1: st.markdown(f"**{survey_title}**"); st.caption(survey.get("desc", ""))
            with col2: st.metric(label="총 발송 횟수", value=f"{len(related_sends)} 회")

            with col3:
                st.button("새로 보내기", key=f"send_{idx}", use_container_width=True,
                          on_click=handle_button_click, args=("new_send",), kwargs={"survey": survey, "key": f"new_{idx}"})
            with col4:
                st.button("발송 현황 보기", key=f"status_{idx}", use_container_width=True, disabled=not related_sends,
                          on_click=handle_button_click, args=("show_status",), kwargs={"survey_title": survey_title})

        if st.session_state.show_status_title == survey_title:
            st.write("---"); st.subheader(f"'{survey_title}' 발송 기록")
            for send_item in sorted(related_sends, key=lambda x: x['scheduled_time'], reverse=True):
                with st.container(border=True):
                    scheduled_time = datetime.strptime(send_item['scheduled_time'], "%Y-%m-%d %H:%M:%S")
                    total, responded = send_item["total"], send_item.get("responded", 0)
                    
                    current_status = send_item.get("status", "N/A")
                    if current_status == "발송 예약" and scheduled_time < datetime.now():
                        current_status = "발송 완료"
                    if current_status == "발송 완료" and total > 0 and responded == total:
                         current_status = "응답 완료"
                    
                    is_editable = current_status in ["발송 예약", "예약 취소"]
                    is_cancelable = current_status == "발송 예약" and (responded < total if total > 0 else True)

                    status_cols = st.columns([3, 1, 1])
                    with status_cols[0]:
                        percent = (responded / total * 100) if total > 0 else 0
                        st.write(f"**상태:** {current_status} | **예약:** {send_item['scheduled_time']} | **대상:** {total}명 | **응답률:** {percent:.1f}%")
                    
                    with status_cols[1]:
                        st.button("수정", key=f"edit_send_{send_item['send_id']}", use_container_width=True, disabled=not is_editable,
                                  on_click=handle_button_click, args=("edit_send",), kwargs={"survey": survey, "send_item": send_item, "key": f"edit_{send_item['send_id']}"})
                    
                    with status_cols[2]:
                        st.button("예약 취소", key=f"cancel_send_{send_item['send_id']}", use_container_width=True, disabled=not is_cancelable, type="secondary",
                                  on_click=handle_button_click, args=("cancel_send",), kwargs={"send_id": send_item['send_id']})

                    with st.expander("상세 대상자 및 응답 현황 보기"):
                        df_status = send_item["data"].copy()
                        total_sent = len(df_status)
                        responded_count = send_item.get("responded", 0)
                        
                        indices = list(range(total_sent))
                        random.shuffle(indices)
                        responded_indices = set(indices[:responded_count])

                        response_status_list, response_time_list = [], []
                        for i in range(total_sent):
                            if i in responded_indices:
                                response_status_list.append("완료")
                                response_time_list.append((scheduled_time + timedelta(days=random.randint(0, 3))).strftime("%Y-%m-%d %H:%M:%S"))
                            else:
                                response_status_list.append("미완료")
                                response_time_list.append(None)
                        
                        df_status["응답 여부"] = response_status_list
                        df_status["응답 시간"] = pd.to_datetime(response_time_list, errors='coerce').strftime('%Y-%m-%d %H:%M:%S').fillna('')
                        
                        st.dataframe(df_status[['이메일', '설문 URL', '응답 여부', '응답 시간']], hide_index=True, use_container_width=True)
            st.write("")
else:
    st.info("등록된 설문이 없습니다.")