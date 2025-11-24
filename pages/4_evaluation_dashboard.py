import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="추천 운동 평가 Dashboard", page_icon="📊", layout="wide")

st.title("📊 MoodFit 추천운동 평가 Dashboard")

# 평가 데이터 불러오기
uploaded_file = st.file_uploader("평가 결과 CSV 파일 업로드", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # 측정 항목 목록
    score_columns = [
        "목적 적합성",
        "감정 적합성",
        "난이도 적합성",
        "부상위험 고려",
        "추천 타당성",
        "추천 다양성"
    ]

    st.subheader("📌 전체 평균 점수")
    avg_scores = df[score_columns].mean()

    col1, col2 = st.columns(2)

    with col1:
        st.metric("총 평균 점수", round(avg_scores.mean(), 2))

        for col in score_columns:
            st.write(f"**{col}:** {round(avg_scores[col], 2)} 점")

    with col2:
        # Radar chart using Plotly
        radar_df = pd.DataFrame(dict(
            r=list(avg_scores.values),
            theta=score_columns
        ))

        fig = px.line_polar(radar_df, r='r', theta='theta', line_close=True)
        fig.update_traces(fill="toself")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("📍 페르소나별 필터")
    persona_list = sorted(df["페르소나"].unique())
    selected_persona = st.selectbox("페르소나 선택", persona_list)

    persona_data = df[df["페르소나"] == selected_persona]
    st.write(persona_data)

    st.subheader("📝 평가 코멘트 모음")
    for i, row in persona_data.iterrows():
        st.write(f"**- 평가자 {row['평가자']}** : {row['코멘트']}")
else:
    st.info("📥 CSV 파일을 업로드해주세요.")
