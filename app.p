import streamlit as st

st.set_page_config(
    page_title="MoodFit",
    page_icon="🏋️",
    layout="centered"
)

# ----------------------------
# 이미지 (위, 작게)
# ----------------------------
st.image("assets/home_fitness.jpg", width=300)   # ← 이미지 크기 조절

# ----------------------------
# 제목 + 설명
# ----------------------------
st.markdown("""
<h1 style="text-align:center; font-size:42px; font-weight:900; margin-top:15px;">
🏋️ MoodFit
</h1>

<p style="text-align:center; font-size:20px; color:#444; margin-top:-10px;">
감정 기반 개인 맞춤 운동 추천 서비스
</p>
""", unsafe_allow_html=True)

# ----------------------------
# 설명 문장
# ----------------------------
st.markdown("""
<p style='text-align:center; font-size:18px; color:#333; margin-top:25px;'>
오늘의 감정을 선택하면<br>
당신에게 딱 맞는 운동 루틴을 추천해드릴게요!
</p>
""", unsafe_allow_html=True)

