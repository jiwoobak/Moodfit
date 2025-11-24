# recommend.py
# -*- coding: utf-8 -*-
import os
import re
import json
import requests
import pandas as pd
import numpy as np
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from datetime import date, datetime

# Spotify
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


# =========================
# 0) 기본 설정
# =========================
st.set_page_config(
    page_title="운동 추천",
    layout="centered",
    page_icon="🏋️"
)

st.markdown("""
    <h1 style='text-align:center; font-weight:700;'>
        🏋️ 맞춤 운동 추천
    </h1>
    <p style="text-align:center; color:gray; margin-top:-10px;">
        오늘의 컨디션 + 날씨를 바탕으로 가장 잘 맞는 운동을 추천해드려요!
    </p>
""", unsafe_allow_html=True)

USER_CSV = "users.csv"
DAILY_CSV = "daily_info.csv"
WORKOUT_CSV = "workout.csv"


# =========================
# 1) CSV 인코딩 안전 읽기
# =========================
def read_csv_robust(path: str) -> pd.DataFrame:
    encodings_to_try = ["utf-8-sig", "utf-8", "cp949"]
    last_err = None
    for enc in encodings_to_try:
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception as e:
            last_err = e
    raise last_err


# =========================
# 1-1) JSON 직렬화 안전 변환
# =========================
def to_json_safe(obj):
    """
    json.dumps에서 깨지는 타입(date, datetime, Timestamp, numpy 등)을
    전부 안전하게 str/float/int/list/dict로 바꿔주는 함수
    """
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    if pd.isna(obj):
        return None
    return obj


# =========================
# 2) 운동 데이터 전처리
# =========================
def split_tags(s):
    if pd.isna(s):
        return []
    return [x.strip() for x in str(s).split(",") if x.strip()]

def normalize_intensity(x):
    x = str(x).strip()
    x = x.replace(" ", "").replace(",,", ",").strip(",")
    return x

def load_workouts():
    if not os.path.exists(WORKOUT_CSV):
        st.error("workout.csv 파일이 없습니다. recommend.py와 같은 폴더에 넣어주세요.")
        st.stop()

    wdf = read_csv_robust(WORKOUT_CSV)

    required_cols = ["운동명", "운동강도", "운동목적", "감정매핑", "단위체중당에너지소비량"]
    missing = [c for c in required_cols if c not in wdf.columns]
    if missing:
        st.error(f"workout.csv에 컬럼이 부족합니다: {missing}")
        st.stop()

    wdf["운동강도"] = wdf["운동강도"].apply(normalize_intensity)
    wdf["운동목적_list"] = wdf["운동목적"].apply(split_tags)
    wdf["감정매핑_list"] = wdf["감정매핑"].apply(split_tags)

    wdf["단위체중당에너지소비량"] = pd.to_numeric(
        wdf["단위체중당에너지소비량"], errors="coerce"
    ).fillna(0)

    return wdf


# =========================
# 3) 날씨 조회
# =========================
def get_weather(city: str):
    load_dotenv()
    key = os.getenv("WEATHER_API_KEY")
    if not key:
        return "unknown", 0.0

    url = (
        "http://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={key}&lang=kr&units=metric"
    )
    try:
        res = requests.get(url, timeout=5)
        data = res.json()
        weather = data.get("weather", [{}])[0].get("main", "unknown").lower()
        temp = float(data.get("main", {}).get("temp", 0))
        return weather, temp
    except Exception:
        return "unknown", 0.0


def infer_place_preference(daily_row, weather):
    place_pref = str(daily_row.get("운동장소", "")).strip()
    if place_pref == "nan":
        place_pref = ""

    bad_weather = any(w in weather for w in ["rain", "drizzle", "thunderstorm", "snow"])

    if bad_weather:
        final_place = "실내"
        msg = "☔/❄ 날씨 영향으로 실내 운동을 우선 추천합니다."
    else:
        if place_pref in ["실내", "실외"]:
            final_place = place_pref
            msg = f"🌤 사용자 선호 장소({place_pref})를 반영해 추천합니다."
        else:
            final_place = "상관없음"
            msg = "🌤 날씨가 무난해 실내/실외 모두 고려해 추천합니다."

    return final_place, msg


# =========================
# 4) 목표 강도 추정
# =========================
INTENSITY_ORDER = ["저강도", "중강도", "고강도"]

POSITIVE_EMOTIONS = {"행복", "기쁨", "설렘", "자신감", "활력", "만족"}
NEGATIVE_EMOTIONS = {"슬픔", "분노", "불안", "초조", "우울", "긴장", "스트레스"}

def get_arousal_from_daily(daily_row):
    candidates = ["감정_평균각성점수", "각성도", "감정각성도", "감정각성도점수",
                  "arousal", "emotion_arousal"]
    for col in candidates:
        if col in daily_row.index:
            try:
                return float(daily_row[col])
            except:
                pass
    return 3.0

def get_emotion_from_daily(daily_row):
    candidates = ["감정_리스트", "감정", "오늘감정", "emotion", "감정상태"]
    for col in candidates:
        if col in daily_row.index:
            v = str(daily_row[col]).strip()
            if v and v != "nan":
                return v.split(",")[0].strip()
    return ""

def infer_target_intensity(daily_row, user_row):
    arousal = get_arousal_from_daily(daily_row)
    emotion = get_emotion_from_daily(daily_row)

    if arousal >= 4.0:
        base = "고강도"
    elif arousal >= 2.5:
        base = "중강도"
    else:
        base = "저강도"

    sleep_hours = float(daily_row.get("수면시간", 7) or 7)
    stress_level = str(daily_row.get("스트레스", "보통") or "보통")
    exercise_time = float(daily_row.get("운동가능시간(분)", 30) or 30)
    activity = str(user_row.get("활동량", "보통") or "보통")
    injury_status = str(user_row.get("부상 이력", "없음") or "없음")
    purpose = str(daily_row.get("운동목적", "") or "")

    target = base

    if emotion in NEGATIVE_EMOTIONS or stress_level == "높음":
        if target == "고강도":
            target = "중강도"

    if sleep_hours < 5 or injury_status == "있음":
        if target == "고강도":
            target = "중강도"
        elif target == "중강도":
            target = "저강도"

    if activity == "높음" and exercise_time >= 60 and injury_status != "있음":
        if target == "저강도":
            target = "중강도"
        elif target == "중강도" and emotion in POSITIVE_EMOTIONS:
            target = "고강도"

    if "스트레스 해소" in purpose and target == "고강도" and stress_level == "높음":
        target = "중강도"

    return target, arousal


# =========================
# 5) 1차 룰 기반 후보군 생성
# =========================
def filter_candidates(workouts_df, purpose, target_intensity):
    cand = workouts_df[workouts_df["운동목적_list"].apply(lambda lst: purpose in lst)]
    cand2 = cand[cand["운동강도"] == target_intensity]

    if len(cand2) < 5:
        idx = INTENSITY_ORDER.index(target_intensity)
        near = {target_intensity}
        if idx - 1 >= 0:
            near.add(INTENSITY_ORDER[idx - 1])
        if idx + 1 < len(INTENSITY_ORDER):
            near.add(INTENSITY_ORDER[idx + 1])
        cand2 = cand[cand["운동강도"].isin(list(near))]

    return cand2.reset_index(drop=True)


# =========================
# 6) LLM Top3 + 이유 생성
# =========================
def robust_json_parse(text):
    text = text.strip()
    text = re.sub(r"```(json)?", "", text).strip("` \n")
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        text = m.group(0)
    return json.loads(text)

def llm_rank_top3(candidates_df, user_row, daily_row,
                  weather, temp, city, place_pref, equip_list,
                  merged_user_info):
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("OPENAI_API_KEY 환경변수가 없습니다. .env 또는 환경변수에 넣어주세요.")
        st.stop()

    client = OpenAI(api_key=api_key)

    cand_list = []
    for i in range(len(candidates_df)):
        r = candidates_df.iloc[i]
        cand_list.append({
            "운동명": r["운동명"],
            "운동강도": r["운동강도"],
            "운동목적": r["운동목적"],
            "감정매핑": r["감정매핑"],
            "단위체중당에너지소비량": r["단위체중당에너지소비량"]
        })

    system = f"""
당신은 운동 처방 코치입니다.
후보 운동 목록 중 사용자에게 가장 잘 맞는 운동 Top3를 고르고,
각 추천에 대해 구체적인 이유를 쓰세요.

[중요 규칙]
1) Top3는 서로 다른 유형/계열로 다양해야 합니다.
2) 사용자 정적정보(users.csv)를 반드시 고려하세요.
3) 오늘의 동적 상태(daily_info)를 종합해 현실적으로 수행 가능한 운동을 우선하세요.
4) 운동 장소/날씨:
   - 비/눈이거나 실내 선호면 실내/홈트 중심으로 추천하세요.
   - 사용자 장소 권장: {place_pref}
5) 보유 장비:
   - 사용자가 가진 장비로 가능한 운동을 우선하세요.
   - 보유장비: {", ".join(equip_list) if equip_list else "없음/미기재"}
6) JSON 형식 외 텍스트는 절대 출력하지 마세요.

반드시 JSON만 출력:
{{
  "top3": [
    {{"rank": 1, "운동명": "...", "이유": "..."}} ,
    {{"rank": 2, "운동명": "...", "이유": "..."}} ,
    {{"rank": 3, "운동명": "...", "이유": "..."}}
  ]
}}
"""

    user_prompt = {
        "현재날씨": {"도시": city, "상태": weather, "온도": temp},
        "사용자정적정보(users.csv+보완)": merged_user_info,
        "오늘동적정보(daily_info)": daily_row.to_dict(),
        "운동장소선호/권장": place_pref,
        "보유장비": equip_list,
        "후보운동목록": cand_list
    }

    if isinstance(user_prompt.get("오늘동적정보(daily_info)"), dict):
        user_prompt["오늘동적정보(daily_info)"].pop("_date", None)

    safe_prompt = to_json_safe(user_prompt)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(safe_prompt, ensure_ascii=False)}
        ],
        temperature=0.7
    )

    content = resp.choices[0].message.content
    try:
        parsed = robust_json_parse(content)
        return parsed["top3"]
    except:
        fallback = []
        take_n = min(3, len(candidates_df))
        for j in range(take_n):
            fallback.append({
                "rank": j+1,
                "운동명": candidates_df.iloc[j]["운동명"],
                "이유": "LLM 파싱 실패로 룰 기반 상위 후보를 임시 추천했습니다."
            })
        return fallback


# =========================
# 6-1) Spotify 하이브리드 추천
#   - LLM이 운동별 검색어 생성
#   - 실패 시 강도/목적 기반 카테고리 fallback
# =========================
def get_spotify_client():
    load_dotenv()
    cid = os.getenv("SPOTIFY_CLIENT_ID")
    csec = os.getenv("SPOTIFY_CLIENT_SECRET")
    if (not cid) or (not csec):
        return None
    auth_manager = SpotifyClientCredentials(client_id=cid, client_secret=csec)
    return spotipy.Spotify(auth_manager=auth_manager)


# 강도/목적 기반 fallback 맵 (작고 유지 쉬움)
INTENSITY_MUSIC = {
    "고강도": ["high energy workout playlist", "HIIT gym music", "cardio beast mode"],
    "중강도": ["motivating workout playlist", "cardio running music", "upbeat fitness"],
    "저강도": ["stretching yoga chill playlist", "lofi workout", "calm fitness music"]
}

PURPOSE_MUSIC = {
    "근력": ["strength training playlist", "gym motivation music"],
    "체력": ["endurance workout playlist", "running cardio music"],
    "유연": ["yoga stretching relaxing", "pilates calm playlist"],
    "다이어트": ["fat burn cardio playlist", "dance workout music"],
    "스트레스": ["stress relief chill playlist", "relaxing workout music"]
}

def make_queries_from_category(target_intensity, purpose="", emotion=""):
    queries = []

    base_list = INTENSITY_MUSIC.get(target_intensity, INTENSITY_MUSIC["중강도"])
    for b in base_list:
        queries.append(b)

    p = str(purpose or "")
    for key in PURPOSE_MUSIC:
        if key in p:
            for q in PURPOSE_MUSIC[key]:
                queries.append(q)

    if emotion:
        queries.append(f"{emotion} mood playlist")
        queries.append(f"{emotion} 음악 플레이리스트")

    dedup = []
    for q in queries:
        if q not in dedup:
            dedup.append(q)
    return dedup


def llm_make_music_queries(top3, daily_row, target_intensity, purpose):
    """
    Top3 운동 각각에 대해 스포티파이 검색어(한+영)를 2~3개 생성.
    실패 시 빈 dict 반환.
    """
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}

    client = OpenAI(api_key=api_key)

    prompt = {
        "top3_운동": [top3[i]["운동명"] for i in range(len(top3))],
        "강도": target_intensity,
        "목적": purpose,
        "감정": str(daily_row.get("감정_리스트","") or daily_row.get("감정","")),
        "운동가능시간": daily_row.get("운동가능시간(분)", "")
    }

    system = """
당신은 운동별 음악/플레이리스트 추천 전문가입니다.
입력된 Top3 운동 각각에 대해 스포티파이에서 잘 검색될 '플레이리스트 검색어'를
한국어+영어 혼합으로 2~3개씩 만들어주세요.

규칙:
- 운동 성격에 맞는 음악 분위기(템포/무드)를 반영
- 실제 스포티파이에서 검색될 법한 짧은 키워드
- 반드시 JSON만 출력

출력:
{
  "queries": {
    "운동명1": ["검색어1", "검색어2", "검색어3"],
    "운동명2": ["..."],
    "운동명3": ["..."]
  }
}
"""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":json.dumps(to_json_safe(prompt), ensure_ascii=False)}
        ],
        temperature=0.5
    )

    try:
        data = robust_json_parse(resp.choices[0].message.content)
        return data.get("queries", {})
    except:
        return {}


def spotify_search_playlists(sp, queries, per_query_limit=3, total_limit=1, market="KR"):
    """
    여러 쿼리를 순차 검색 → URL 중복 제거 → total_limit개 반환
    """
    if sp is None:
        return []

    results = []
    seen = set()

    for qi in range(len(queries)):
        q = queries[qi]
        try:
            res = sp.search(q=q, type="playlist", limit=per_query_limit, market=market)
            items = (res.get("playlists") or {}).get("items") or []

            for i in range(len(items)):  # enumerate 금지
                pl = items[i]
                if pl is None:
                    continue

                title = pl.get("name") or ""
                owner_obj = pl.get("owner") or {}
                owner = owner_obj.get("display_name") or owner_obj.get("id") or "unknown"
                ext = pl.get("external_urls") or {}
                url = ext.get("spotify") or ""

                if not url or url in seen:
                    continue

                seen.add(url)
                results.append({
                    "title": title,
                    "url": url,
                    "owner": owner,
                    "query_used": q
                })

                if len(results) >= total_limit:
                    return results

        except:
            continue

    return results


def get_playlists_for_top3_with_llm(sp, top3, daily_row, target_intensity, purpose, market="KR"):
    """
    Top3 운동 각각에 대해:
    1) LLM이 만든 운동별 음악 검색어로 검색
    2) 실패하면 강도/목적 기반 fallback 쿼리로 검색
    """
    emotion = get_emotion_from_daily(daily_row)
    llm_queries = llm_make_music_queries(top3, daily_row, target_intensity, purpose)

    out = []
    for t in top3:
        wname = t.get("운동명", "")
        queries = llm_queries.get(wname, [])

        if not queries:
            queries = make_queries_from_category(target_intensity, purpose, emotion)

        pls = spotify_search_playlists(
            sp, queries,
            per_query_limit=3,
            total_limit=1,
            market=market
        )
        out.append({"운동명": wname, "playlists": pls})

    return out


# =========================
# 7) 추천 결과 저장 (날짜 robust)
# =========================
def save_recommendations(daily_df, user_name, pick_date, top3):
    df = daily_df.copy()

    df["_date"] = pd.to_datetime(df["날짜"], errors="coerce").dt.date
    pick_date_dt = pd.to_datetime(pick_date, errors="coerce").date()

    idx = df[
        (df["이름"].astype(str) == str(user_name)) &
        (df["_date"] == pick_date_dt)
    ].index

    if len(idx) == 0:
        df.drop(columns=["_date"], inplace=True, errors="ignore")
        return daily_df

    idx = idx[0]

    for k in range(1, 4):
        wcol = f"추천운동{k}"
        rcol = f"추천이유{k}"
        if wcol not in df.columns:
            df[wcol] = ""
        if rcol not in df.columns:
            df[rcol] = ""

    for item in top3:
        rk = int(item["rank"])
        if 1 <= rk <= 3:
            df.loc[idx, f"추천운동{rk}"] = item["운동명"]
            df.loc[idx, f"추천이유{rk}"] = item["이유"]

    df.drop(columns=["_date"], inplace=True, errors="ignore")
    df.to_csv(DAILY_CSV, index=False, encoding="utf-8-sig")
    return df


# =========================
# 8) UI
# =========================
if not os.path.exists(USER_CSV) or not os.path.exists(DAILY_CSV):
    st.warning("users.csv / daily_info.csv가 없습니다. 먼저 정적/동적 정보를 입력해주세요.")
    st.stop()

users_df = read_csv_robust(USER_CSV)
daily_df = read_csv_robust(DAILY_CSV)
workouts_df = load_workouts()

# 도시 입력
st.markdown("## 🌍 도시 입력")
city = st.text_input("날씨를 반영할 도시명", value="Seoul")
weather, temp = get_weather(city)
st.info(f"🌤 현재 날씨: **{weather}**, 온도 **{temp:.1f}°C** (도시: {city})")

st.markdown("---")

# 사용자 선택
st.markdown("## 👤 사용자 선택")
user_name = st.selectbox("추천 받을 사용자", users_df["이름"].astype(str).tolist())

# 날짜 선택
st.markdown("## 📅 날짜 선택")
daily_df["_date"] = pd.to_datetime(daily_df["날짜"], errors="coerce").dt.date
user_daily = daily_df[daily_df["이름"].astype(str) == str(user_name)].copy()
available_dates = sorted([d for d in user_daily["_date"].dropna().unique()])

if not available_dates:
    st.error("해당 사용자의 동적 정보 기록이 없습니다. '오늘의 컨디션 입력'에서 저장해주세요.")
    st.stop()

pick_mode = st.radio("추천 기준 날짜 선택 방식", ["기록에서 선택", "직접 날짜 입력"], horizontal=True)
if pick_mode == "기록에서 선택":
    pick_date = st.selectbox("추천 기준 날짜", available_dates)
else:
    pick_date = st.date_input("추천 기준 날짜를 선택하세요", value=available_dates[-1])

pick_date_dt = pd.to_datetime(pick_date, errors="coerce").date()

# 선택 날짜가 없으면 최근 기록으로 대체
exact_rows = user_daily[user_daily["_date"] == pick_date_dt]
if len(exact_rows) > 0:
    daily_row = exact_rows.iloc[0]
    used_date = pick_date_dt
else:
    before_rows = user_daily[user_daily["_date"] <= pick_date_dt].sort_values("_date")
    if len(before_rows) > 0:
        daily_row = before_rows.iloc[-1]
        used_date = daily_row["_date"]
    else:
        daily_row = user_daily.sort_values("_date").iloc[-1]
        used_date = daily_row["_date"]
    st.caption(f"선택한 날짜 기록이 없어 **{used_date}** 기록을 기준으로 추천합니다.")

# users.csv 정적 정보
user_row = users_df[users_df["이름"].astype(str) == str(user_name)].iloc[0]

# users.csv(정적) + daily_info(보완) 합치기
merged_user_info = user_row.to_dict()
for k, v in daily_row.to_dict().items():
    if k not in merged_user_info or pd.isna(merged_user_info.get(k)):
        merged_user_info[k] = v

# daily_info 기반 변수
purpose = str(daily_row.get("운동목적", "체력 향상") or "체력 향상")
target_intensity, arousal = infer_target_intensity(daily_row, user_row)

place_pref, place_msg = infer_place_preference(daily_row, weather)
equip_list = split_tags(daily_row.get("보유장비", ""))

st.caption(place_msg)

# 후보군 생성
candidates_df = filter_candidates(workouts_df, purpose, target_intensity)

st.markdown("---")

if st.button("🤖 Top3 운동 추천 받기", use_container_width=True):
    if len(candidates_df) == 0:
        st.error("추천할 후보 운동이 없습니다. 운동목적/강도 조건을 확인해주세요.")
        st.stop()

    with st.spinner("운동 추천을 생성 중입니다..."):
        top3 = llm_rank_top3(
            candidates_df, user_row, daily_row,
            weather, temp, city,
            place_pref, equip_list,
            merged_user_info
        )

    daily_df = save_recommendations(daily_df, user_name, used_date, top3)

    st.markdown("## 🏅 추천 Top3")
    for item in top3:
        st.markdown(f"""
        <div style="
            background:#f7f9fc;
            border-radius:16px;
            padding:18px;
            margin-bottom:10px;
            border:1px solid #e5e7eb;">
            <h3 style="margin:0;">#{item['rank']}  {item['운동명']}</h3>
            <p style="margin-top:6px; color:#374151;">
                {item['이유']}
            </p>
        </div>
        """, unsafe_allow_html=True)

    # =========================
    # Spotify: 운동별 어울리는 플리 추천 (LLM + fallback)
    # =========================
    emotion = get_emotion_from_daily(daily_row)

    top3_names = [top3[i]["운동명"] for i in range(len(top3))]
    cache_key = f"{target_intensity}|{purpose}|{emotion}|{'/'.join(top3_names)}"

    if "playlist_cache" not in st.session_state:
        st.session_state["playlist_cache"] = {}

    if cache_key in st.session_state["playlist_cache"]:
        workout_playlist_pairs = st.session_state["playlist_cache"][cache_key]
    else:
        sp = get_spotify_client()
        workout_playlist_pairs = get_playlists_for_top3_with_llm(
            sp, top3, daily_row,
            target_intensity=target_intensity,
            purpose=purpose,
            market="KR"
        )
        st.session_state["playlist_cache"][cache_key] = workout_playlist_pairs

    st.markdown("## 🎧 추천 운동별 어울리는 Spotify 플레이리스트")

    for i in range(len(workout_playlist_pairs)):
        pair = workout_playlist_pairs[i]
        wname = pair["운동명"]
        pls = pair["playlists"]

        st.markdown(f"### 🏷️ {wname}")

        if len(pls) == 0:
            st.info("이 운동에 어울리는 플레이리스트를 찾지 못했어요 😢")
        else:
            p = pls[0]
            st.markdown(f"""
            <div style="
                background:#ffffff;
                border-radius:16px;
                padding:14px;
                margin-bottom:8px;
                border:1px solid #e5e7eb;">
                <h4 style="margin:0;">🎵 {p['title']}</h4>
                <p style="margin:4px 0 0 0; color:#6b7280;">
                    by {p['owner']}
                </p>
                <a href="{p['url']}" target="_blank">
                    🔗 Spotify에서 열기
                </a>
            </div>
            """, unsafe_allow_html=True)

    daily_df.drop(columns=["_date"], inplace=True, errors="ignore")
