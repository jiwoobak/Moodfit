import streamlit as st
import time

st.set_page_config(page_title="MoodFit", page_icon="🏋️", layout="centered")

st.markdown("""
    <h1 style='text-align:center; font-size:40px;'>🏋️ MoodFit</h1>
    <p style='text-align:center; font-size:20px; color:gray;'>당신의 감정 기반 운동 추천 서비스</p>
""", unsafe_allow_html=True)

# 3~4초 대기 후 자동 이동
time.sleep(3)  # ← 3초 보여줌
st.switch_page("pages/1_user_info2.py")
