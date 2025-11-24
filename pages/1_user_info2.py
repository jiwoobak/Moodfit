import streamlit as st
import pandas as pd
from sheets_auth import connect_gsheet

# 페이지 기본 설정
st.set_page_config(
    page_title="회원 등록",
    layout="centered",
    page_icon="🧍"
)

st.markdown("""
    <h1 style='text-align:center; font-weight:700;'>
        🧍 회원 등록
    </h1>
    <p style="text-align:center; color:gray; margin-top:-10px;">
        회원 정보를 등록하면 개인 맞춤 운동 추천이 더 정확해져요!
    </p>
""", unsafe_allow_html=True)

# Google Sheet 연결
sh = connect_gsheet("MoodFit_users")
ws = sh.sheet1   # 첫 시트

# 입력 UI
st.markdown("## 📝 기본 정보")

col1, col2 = st.columns(2)
with col1:
    name = st.text_input("이름", placeholder="홍길동")
with col2:
    gender = st.selectbox("성별", ["남성", "여성"])

col3, col4 = st.columns(2)
with col3:
    age = st.number_input("나이 (만나이)", min_value=10, max_value=100, value=25)
with col4:
    activity = st.selectbox("평소 활동량", ["낮음", "보통", "높음"])

col5, col6 = st.columns(2)
with col5:
    height = st.text_input("키 (cm)")
with col6:
    weight = st.text_input("몸무게 (kg)")

st.markdown("---")

st.markdown("## 🩹 부상 이력")

injury_status = st.radio("부상 여부", ["없음", "있음"], horizontal=True)
injury_detail = ""

if injury_status == "있음":
    common_injuries = ["무릎", "허리", "어깨", "발목", "손목", "기타"]
    selected_parts = st.multiselect("부상 부위를 선택하세요", common_injuries)
    if "기타" in selected_parts:
        other = st.text_input("기타 부상 입력", placeholder="예: 햄스트링 등")
        if other.strip():
            selected_parts.append(other)
    injury_detail = ", ".join(selected_parts) if selected_parts else "있음"

st.markdown("<br>", unsafe_allow_html=True)

if st.button("💾 회원 등록 완료", use_container_width=True):
    if not name.strip():
        st.warning("⚠️ 이름을 입력해주세요.")
        st.stop()

    new_row = [
        name, age, gender, height, weight, activity,
        injury_status, injury_detail
    ]

    existing_names = ws.col_values(1)
    if name in existing_names:
        st.warning("⚠ 이미 등록된 회원입니다.")
    else:
        ws.append_row(new_row)
        st.success("🎉 회원 등록이 완료되었습니다!")
        st.balloons()
        st.switch_page("pages/2_daily_info2.py")
