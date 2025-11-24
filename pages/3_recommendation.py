import streamlit as st
import pandas as pd
from sheets_auth import connect_gsheet
from datetime import datetime
import os, json, re, requests
import numpy as np
from openai import OpenAI

st.set_page_config(page_title="운동 추천", layout="centered", page_icon="🏋️")

st.markdown("""
    <h1 style='text-align:center; font-weight:700;'>🏋️ 맞춤 운동 추천</h1>
    <p style="text-align:center; color:gray; margin-top:-10px;">
        오늘의 컨디션 + 날씨 기반 Top3 운동 추천
    </p>
""", unsafe_allow_html=True)

# ===============================
# Google Sheet 연결
# ===============================
sh = connect_gsheet("MoodFit_users")
ws_daily = sh.worksheet("daily")   # daily 시트
ws_users = sh.sheet1               # 회원정보 시트

# ===============================
# 날씨 입력
# ===============================
city = st.text_input("🌍 날씨 도시명", value="Seoul")
key = os.getenv("WEATHER_API_KEY")

def get_weather(city):
    if not key:
        return "unknown", 0.0
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={key}&lang=kr&units=metric"
    try:
        res = requests.get(url, timeout=5).json()
        return res["weather"][0]["main"], res["main"]["temp"]
    except:
        return "unknown", 0.0

weather, temp = get_weather(city)
st.info(f"현재: {weather}, {temp:.1f}°C")

# ===============================
# 사용자 선택
# ===============================
users = ws_users.col_values(1)[1:]  # header 제외
user_name = st.selectbox("추천 받을 사용자", users)

# 날짜
dates = ws_daily.col_values(1)[1:]
pick_date = st.selectbox("추천 기준 날짜", sorted(set(dates), reverse=True))

# ===============================
# 추천 버튼 클릭 로직
# ===============================
if st.button("🤖 Top3 운동 추천 받기", use_container_width=True):

    # LLM 추천 결과 예시로 가짜 top3
    top3 = [
        {"rank":1, "운동명":"런닝", "이유":"심박수 상승 & 스트레스 해소"},
        {"rank":2, "운동명":"요가", "이유":"근육 이완 & 회복"},
        {"rank":3, "운동명":"플랭크", "이유":"코어 강화 효과"}
    ]

    st.session_state["recommended_workouts"] = [t["운동명"] for t in top3]

    # Google Sheets에서 해당 row 찾기
    daily_rows = ws_daily.get_all_values()
    target_row = None
    for i, row in enumerate(daily_rows):
        if row[0] == pick_date and row[1] == user_name:
            target_row = i + 1  # index 보정

    if not target_row:
        st.error("해당 날짜의 컨디션 데이터가 없습니다.")
        st.stop()

    # 추천 운동 3개 업데이트
    ws_daily.update_cell(target_row, 11, top3[0]["운동명"])  # 추천1
    ws_daily.update_cell(target_row, 12, top3[1]["운동명"])  # 추천2
    ws_daily.update_cell(target_row, 13, top3[2]["운동명"])  # 추천3

    st.success("🎉 추천 운동이 저장되었습니다!")

    # 화면 출력
    st.markdown("## 🏅 추천 Top3")
    for item in top3:
        st.write(f"### #{item['rank']} {item['운동명']}")
        st.write(item["이유"])

    st.markdown("---")
    st.write("추천 운동 평가를 진행해주세요")

    if st.button("📊 평가 페이지로 이동", use_container_width=True):
        st.switch_page("pages/4_evaluation_dashboard.py")
