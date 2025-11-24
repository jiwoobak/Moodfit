import streamlit as st

st.set_page_config(
    page_title="MoodFit",
    page_icon="🏋️",
    layout="centered"
)

# 이미지 중앙
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("assets/home_fitness.jpg", width=350)

# 제목 & 설명
st.title("🏋️ MoodFit")
st.write("감정 기반 개인 맞춤 운동 추천 서비스")

st.markdown("---")

# 버튼 클릭하면 다음 페이지 이동
if st.button("👉 시작하기", use_container_width=True):
    st.switch_page("1_user_info2.py")

