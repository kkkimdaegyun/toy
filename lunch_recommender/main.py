import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from schemas import (
    User, Restaurant, RestaurantAttributes, MABStats,
    RecommendationRequest, RecommendationResponse,
    FeedbackRequest, NearbyRestaurant
)
from recommender import LunchRecommender, CATEGORY_ATTRIBUTE_DEFAULTS, infer_ingredients
from nlp_parser import parse_lunch_prompt
from naver_api import NaverLocalSearch

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("LunchRecommenderAPI")

app = FastAPI(
    title="Lunch Recommendation AI Service",
    description="사내 점심 메뉴 추천 AI (CBF + Category Preference + Least Misery + MAB UCB + 네이버 지도 연동)",
    version="3.0.0"
)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# 추천 엔진 및 네이버 API 클라이언트
recommender_engine = LunchRecommender()
naver_client = NaverLocalSearch()

# ═══════════════════════════════════════════════════════════════
# 데이터 파일 관리
# ═══════════════════════════════════════════════════════════════
SURVEY_FILE = "surveys_data.json"
MAB_STATS_FILE = "mab_stats.json"
FEEDBACK_FILE = "feedback_log.json"

employee_surveys: Dict[str, User] = {}
mab_stats_store: Dict[str, Dict] = {}
feedback_log: List[Dict] = []

# ── 기본 사내 직원 프로필 ─────────────────────────────────────
DEFAULT_EMPLOYEES = {}

# ── 폴백 식당 (네이버 API 미설정 시 사용) ────────────────────
DEFAULT_RESTAURANTS = [
    Restaurant(rest_id="r1", name="얼큰 한돈 생고기 김치찌개 맛집",
               attributes={"category": "한식", "spicy_level": 4.5, "soup": True, "meat": True, "ingredients": ["돼지고기", "김치", "두부"]},
               mab_stats={"clicks": 20, "avg_reward": 4.7}),
    Restaurant(rest_id="r2", name="불향 매콤 숯불 쭈꾸미 & 철판 제육볶음",
               attributes={"category": "한식", "spicy_level": 4.5, "soup": False, "meat": True, "ingredients": ["쭈꾸미", "돼지고기", "양파"]},
               mab_stats={"clicks": 15, "avg_reward": 4.6}),
    Restaurant(rest_id="r3", name="칼칼한 뚝배기 묵은지 닭볶음탕 전문점",
               attributes={"category": "한식", "spicy_level": 4.5, "soup": True, "meat": True, "ingredients": ["닭고기", "감자", "김치"]},
               mab_stats={"clicks": 18, "avg_reward": 4.8}),
    Restaurant(rest_id="r4", name="화끈한 성수 정통 마라탕",
               attributes={"category": "중식", "spicy_level": 5.0, "soup": True, "meat": True, "ingredients": ["소고기", "청경채", "마라", "숙주"]},
               mab_stats={"clicks": 12, "avg_reward": 4.4}),
    Restaurant(rest_id="r5", name="얼큰 차돌 불짬뽕 & 찹쌀 탕수육",
               attributes={"category": "중식", "spicy_level": 4.0, "soup": True, "meat": True, "ingredients": ["돼지고기", "오징어", "양파"]},
               mab_stats={"clicks": 14, "avg_reward": 4.3}),
    Restaurant(rest_id="r6", name="정통 오사카 매콤 카라미소 라멘",
               attributes={"category": "일식", "spicy_level": 4.0, "soup": True, "meat": True, "ingredients": ["돼지고기", "숙주", "된장"]},
               mab_stats={"clicks": 10, "avg_reward": 4.2}),
    Restaurant(rest_id="r7", name="신선 사케동 & 겉바속촉 로스 돈카츠",
               attributes={"category": "일식", "spicy_level": 1.0, "soup": False, "meat": True, "ingredients": ["연어", "돼지고기"]},
               mab_stats={"clicks": 11, "avg_reward": 4.5}),
    Restaurant(rest_id="r8", name="담백한 맑은 한우 나주곰탕",
               attributes={"category": "한식", "spicy_level": 1.0, "soup": True, "meat": True, "ingredients": ["소고기", "파", "무"]},
               mab_stats={"clicks": 25, "avg_reward": 4.7}),
    Restaurant(rest_id="r9", name="상암동 대림복국 직영점",
               attributes={"category": "한식", "spicy_level": 1.0, "soup": True, "meat": False, "ingredients": ["복어", "미나리", "콩나물"]},
               mab_stats={"clicks": 20, "avg_reward": 4.8}),
    Restaurant(rest_id="r10", name="누리꿈스퀘어 시원한 대구지리탕 전문점",
               attributes={"category": "한식", "spicy_level": 1.0, "soup": True, "meat": False, "ingredients": ["대구", "미나리", "무"]},
               mab_stats={"clicks": 18, "avg_reward": 4.6}),
]


# ═══════════════════════════════════════════════════════════════
# 데이터 로드/저장 함수
# ═══════════════════════════════════════════════════════════════
def load_surveys():
    global employee_surveys
    employee_surveys.clear()
    if os.path.exists(SURVEY_FILE):
        try:
            with open(SURVEY_FILE, "r", encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    employee_surveys[k] = User(**v)
            logger.info(f"직원 설문 {len(employee_surveys)}건 로드 완료")
        except Exception as e:
            logger.warning(f"설문 파일 로드 실패: {e}")


def save_surveys():
    try:
        with open(SURVEY_FILE, "w", encoding="utf-8") as f:
            json.dump({k: v.model_dump() for k, v in employee_surveys.items()}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        logger.error(f"설문 저장 실패: {e}")


def load_mab_stats():
    global mab_stats_store
    if os.path.exists(MAB_STATS_FILE):
        try:
            with open(MAB_STATS_FILE, "r", encoding="utf-8") as f:
                mab_stats_store = json.load(f)
            logger.info(f"MAB 통계 {len(mab_stats_store)}개 식당 로드 완료")
        except Exception as e:
            logger.warning(f"MAB 통계 로드 실패: {e}")


def save_mab_stats():
    try:
        with open(MAB_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(mab_stats_store, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"MAB 통계 저장 실패: {e}")


def load_feedback():
    global feedback_log
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                feedback_log = json.load(f)
            logger.info(f"피드백 이력 {len(feedback_log)}건 로드 완료")
        except Exception as e:
            logger.warning(f"피드백 로드 실패: {e}")


def save_feedback():
    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(feedback_log, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"피드백 저장 실패: {e}")


def get_mab_stats_for(restaurant_name: str) -> MABStats:
    """식당별 MAB 통계 조회 (없으면 초기값)"""
    stats = mab_stats_store.get(restaurant_name, {"clicks": 0, "avg_reward": 0.0})
    return MABStats(clicks=stats.get("clicks", 0), avg_reward=stats.get("avg_reward", 0.0))


def update_mab_stats_for(restaurant_name: str, rating: float):
    """피드백 별점으로 MAB 통계 실시간 업데이트"""
    if restaurant_name not in mab_stats_store:
        mab_stats_store[restaurant_name] = {"clicks": 0, "total_reward": 0.0, "avg_reward": 0.0}
    s = mab_stats_store[restaurant_name]
    s["clicks"] += 1
    s["total_reward"] = s.get("total_reward", 0.0) + rating
    s["avg_reward"] = round(s["total_reward"] / s["clicks"], 2)
    save_mab_stats()


# ═══════════════════════════════════════════════════════════════
# 네이버 식당 → Restaurant 변환
# ═══════════════════════════════════════════════════════════════
def convert_naver_to_restaurants(naver_results: List[Dict]) -> List[Restaurant]:
    """네이버 API 결과를 추천 엔진용 Restaurant 객체로 변환"""
    restaurants = []
    for i, nr in enumerate(naver_results):
        cat = nr.get("category", "기타")
        defaults = CATEGORY_ATTRIBUTE_DEFAULTS.get(cat, CATEGORY_ATTRIBUTE_DEFAULTS["기타"])
        mab = get_mab_stats_for(nr["title"])

        restaurants.append(Restaurant(
            rest_id=f"naver_{i}",
            name=nr["title"],
            attributes=RestaurantAttributes(
                category=cat,
                spicy_level=defaults["spicy_level"],
                soup=defaults["soup"],
                meat=defaults["meat"],
                # [Fix 5-b] 네이버는 재료를 안 주므로 카테고리+이름으로 추정 재료를 채워
                #           Least Misery 알러지/기피 필터가 실데이터에서도 작동하도록 함.
                ingredients=infer_ingredients(nr["title"], cat)
            ),
            mab_stats=mab
        ))
    return restaurants


# 초기 데이터 로드
load_surveys()
load_mab_stats()
load_feedback()


class SearchPromptRequest(BaseModel):
    query: str


# ═══════════════════════════════════════════════════════════════
# API 엔드포인트
# ═══════════════════════════════════════════════════════════════

@app.get("/health", summary="헬스체크", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "naver_api_configured": naver_client.is_configured,
        "registered_surveys": len(employee_surveys),
        "total_feedback": len(feedback_log)
    }


@app.get("/api/restaurants/nearby", summary="누리꿈스퀘어 근처 식당 조회", tags=["Restaurant"])
async def get_nearby_restaurants():
    """네이버 지도 API로 상암동 누리꿈스퀘어 1km 이내 식당 목록 반환"""
    if not naver_client.is_configured:
        raise HTTPException(status_code=503, detail="네이버 API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")

    results = naver_client.search_nearby_restaurants()
    return {
        "location": "상암동 누리꿈스퀘어",
        "count": len(results),
        "restaurants": [NearbyRestaurant(**r).model_dump() for r in results]
    }


@app.get("/api/restaurants/search", summary="키워드로 근처 식당 검색 (RLHF 대안 선택용)", tags=["Restaurant"])
async def search_local_restaurants(query: str):
    """
    사용자가 AI 추천 식당 대신 실제 간 식당을 검색하여 선택할 수 있도록 지원합니다.
    """
    query_clean = query.strip()
    if not query_clean:
        return {"count": 0, "restaurants": []}

    if naver_client.is_configured:
        results = naver_client.search_keyword(query_clean)
        return {"count": len(results), "restaurants": results}
    else:
        matched = [
            {
                "title": r.name,
                "category": r.attributes.category,
                "address": "상암동 누리꿈스퀘어 인근",
                "naver_map_url": f"https://map.naver.com/v5/search/{quote(r.name)}"
            }
            for r in DEFAULT_RESTAURANTS if query_clean in r.name or query_clean in r.attributes.category
        ]
        if not matched:
            matched = [{
                "title": query_clean,
                "category": "기타",
                "address": "상암동 누리꿈스퀘어 인근",
                "naver_map_url": f"https://map.naver.com/v5/search/{quote(query_clean)}"
            }]
        return {"count": len(matched), "restaurants": matched}


@app.post("/api/search", summary="자연어 점심 메뉴 추천 검색", tags=["Search"])
async def search_lunch(payload: SearchPromptRequest):
    """
    자연어 요청을 분석하여 참여자·맛 선호도를 반영한 Top 3 추천.
    네이버 API 설정 시 실제 주변 식당 대상, 미설정 시 샘플 식당 대상.
    """
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")

    # 1. NLP 파싱
    matched_users, modifier, excluded_categories, notes = parse_lunch_prompt(query, employee_surveys)
    if not matched_users:
        if employee_surveys:
            matched_users = list(employee_surveys.values())[:3]
            notes.append("💡 참여자 미지정 — 사내 등록 구성원 평균 취향 반영")
        else:
            matched_users = [User(user_id="기본 참여자")]
            notes.append("💡 등록된 설문 없음 — 기본 취향으로 추천")

    # 2. 식당 풀 결정
    naver_lookup: Dict[str, Dict] = {}

    if naver_client.is_configured:
        naver_results = naver_client.search_nearby_restaurants(
            exclude_categories=excluded_categories
        )
        # 사용자가 입력한 구체적 음식 키워드(예: 맑은탕, 라멘 등)가 있으면 추가 검색하여 우선 풀에 반영
        if modifier.get("query_keyword"):
            kw_results = naver_client.search_keyword(modifier["query_keyword"])
            for kr in kw_results:
                if not any(nr.get("title") == kr.get("title") for nr in naver_results):
                    naver_results.insert(0, kr)
        restaurants = convert_naver_to_restaurants(naver_results)
        for i, nr in enumerate(naver_results):
            naver_lookup[f"naver_{i}"] = nr
        # [Fix 5-a] 제외 의도 카테고리를 네이버 후보 풀에도 실제 적용.
        #  기존엔 검색 키워드만 줄이고 반환 결과는 안 걸러 중식/일식이 그대로 유입됐다.
        if excluded_categories:
            filtered = [r for r in restaurants if r.attributes.category not in excluded_categories]
            if filtered:  # 전부 걸러지면 원복(Fallback)
                restaurants = filtered
        notes.append(f"📍 네이버 지도: 누리꿈스퀘어 1km 이내 {len(restaurants)}개 식당 맞춤 검색")
    else:
        restaurants = [r for r in DEFAULT_RESTAURANTS if r.attributes.category not in excluded_categories]
        notes.append("⚠️ 네이버 API 미설정 — 샘플 식당 데이터 사용")

    # 3. 당일 맛 보정
    temp_users = []
    for u in matched_users:
        u_dict = u.model_dump()
        u_dict["preferences"].update(modifier)
        temp_users.append(User(**u_dict))

    # 4. 추천 알고리즘 실행 (질문 키워드 기반 맞춤 스코어 및 추천 메뉴 생성)
    recs = recommender_engine.recommend(users=temp_users, restaurants=restaurants, top_k=3, query_text=query)

    # 5. 응답 구성
    participant_names = [u.user_id for u in temp_users]
    results = []
    for r in recs:
        item: Dict[str, Any] = {
            "rest_id": r.rest_id,
            "name": r.name,
            "category": r.category,
            "final_score": r.final_score,
            "recommended_menu": r.recommended_menu,
            "reason": r.reason,
        }
        if r.rest_id in naver_lookup:
            nr = naver_lookup[r.rest_id]
            item["naver_map_url"] = nr.get("naver_map_url", "")
            item["address"] = nr.get("road_address") or nr.get("address", "")
            item["telephone"] = nr.get("telephone", "")
        else:
            item["naver_map_url"] = f"https://map.naver.com/v5/search/{quote(r.name)}"
            item["address"] = ""
            item["telephone"] = ""
        results.append(item)

    return {
        "participants": participant_names,
        "context_notes": notes,
        "recommendations": results
    }


@app.post("/api/survey", summary="직원 취향 설문 저장", tags=["Survey"])
async def submit_survey(user: User):
    if user.taste_preferences:
        spicy_val = float(user.taste_preferences.get("매운 음식", 3))
        soup_val = user.taste_preferences.get("국물 있는 음식", 3) >= 3
        meat_val = user.taste_preferences.get("고기 위주", 3) >= 3
        user.preferences = {"spicy_level": spicy_val, "soup": soup_val, "meat": meat_val}
    employee_surveys[user.user_id] = user
    save_surveys()
    return {"message": "설문이 성공적으로 저장되었습니다.", "user": user}


@app.get("/api/surveys", response_model=List[User], summary="전체 설문 조회", tags=["Survey"])
async def get_all_surveys():
    return list(employee_surveys.values())
@app.api_route("/api/surveys/reset", methods=["DELETE", "POST"], summary="전체 설문 DB 초기화 (테스트용)", tags=["Survey"])
async def reset_all_surveys():
    employee_surveys.clear()
    save_surveys()
    return {"message": "테스트용: 모든 설문 데이터가 초기화되었습니다."}



@app.get("/api/surveys/stats", summary="설문 참여자 목록 및 취합 통계 조회", tags=["Survey"])
async def get_surveys_stats():
    users = list(employee_surveys.values())
    total = len(users)
    names = [u.user_id for u in users]

    if total == 0:
        return {
            "total_count": 0,
            "names": [],
            "names_str": "아직 설문 완료자 없음",
            "stats": {},
            "storage_info": {
                "file": SURVEY_FILE,
                "abs_path": os.path.abspath(SURVEY_FILE),
                "status": f"DB({SURVEY_FILE}) 파일에 실시간 적재 준비 완료 (현재 0명)"
            }
        }

    dept_counts = {}
    cat_counts = {}
    total_spicy = 0.0
    soup_count = 0
    meat_count = 0
    all_allergies = []
    all_dislikes = []

    for u in users:
        dept = u.department or "미지정"
        dept_counts[dept] = dept_counts.get(dept, 0) + 1

        for cat in u.preferred_categories:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        total_spicy += float(u.preferences.get("spicy_level", 3.0))
        if u.preferences.get("soup", False):
            soup_count += 1
        if u.preferences.get("meat", False):
            meat_count += 1

        all_allergies.extend(u.allergies)
        all_dislikes.extend(u.dislikes)

    avg_spicy = round(total_spicy / total, 1)
    soup_ratio = round((soup_count / total) * 100, 1)
    meat_ratio = round((meat_count / total) * 100, 1)

    return {
        "total_count": total,
        "names": names,
        "names_str": ", ".join(names),
        "stats": {
            "dept_counts": dept_counts,
            "category_preference": cat_counts,
            "avg_spicy_level": avg_spicy,
            "soup_preference_ratio": soup_ratio,
            "meat_preference_ratio": meat_ratio,
            "allergies": list(set(all_allergies)),
            "dislikes": list(set(all_dislikes))
        },
        "storage_info": {
            "file": SURVEY_FILE,
            "abs_path": os.path.abspath(SURVEY_FILE),
            "status": f"현재 {total}명의 설문 데이터가 서버 영구 DB({SURVEY_FILE})에 정상 적재됨"
        }
    }


@app.get("/api/surveys/{user_id}", response_model=User, summary="특정 직원 설문 조회", tags=["Survey"])
async def get_user_survey(user_id: str):
    if user_id not in employee_surveys:
        raise HTTPException(status_code=404, detail="해당 직원의 설문 내역을 찾을 수 없습니다.")
    return employee_surveys[user_id]


# ═══════════════════════════════════════════════════════════════
# 피드백 시스템 (Reward Score → MAB 실시간 학습)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/feedback", summary="식사 후 피드백 제출 (RLHF 대안 학습 포함)", tags=["Feedback"])
async def submit_feedback(fb: FeedbackRequest):
    """
    - visited=True (👍): 추천 식당 방문 완료 -> 해당 식당 만족도 학습
    - visited=False (👎): 추천 식당 미방문 -> 실제 방문한 대안 식당(actual_restaurant_name) 학습 및 사내 풀 자가 확장
    """
    record = {
        "user_id": fb.user_id,
        "restaurant_name": fb.restaurant_name,
        "rating": fb.rating,
        "visited": fb.visited,
        "actual_restaurant_name": fb.actual_restaurant_name,
        "actual_category": fb.actual_category,
        "timestamp": datetime.now().isoformat()
    }
    feedback_log.append(record)
    save_feedback()

    if fb.visited:
        update_mab_stats_for(fb.restaurant_name, fb.rating)
    else:
        if fb.actual_restaurant_name:
            update_mab_stats_for(fb.actual_restaurant_name, fb.rating)
            logger.info(f"RLHF 대안 식당 학습 완료: {fb.actual_restaurant_name} (만족도 {fb.rating}점)")

    return {"message": "피드백이 성공적으로 반영되어 AI가 학습되었습니다.", "record": record}


@app.get("/api/feedback/history", summary="전체 피드백 이력 조회", tags=["Feedback"])
async def get_feedback_history():
    return {"count": len(feedback_log), "records": feedback_log}


# ═══════════════════════════════════════════════════════════════
# 온라인 평가 대시보드 (Hit Rate + 평균 만족도)
# ═══════════════════════════════════════════════════════════════

@app.get("/api/dashboard", summary="추천 성과 대시보드 통계", tags=["Dashboard"])
async def get_dashboard():
    """
    Hit Rate: 추천 후 실제 방문 비율
    Avg Satisfaction: 방문 피드백 평균 별점 (AI 추천 방문 + RLHF 대안 방문)
    식당별 누적 피드백 및 평균 점수
    """
    total = len(feedback_log)
    ai_visited = [f for f in feedback_log if f.get("visited")]
    alt_visited = [f for f in feedback_log if not f.get("visited") and f.get("actual_restaurant_name")]
    total_ai_visited = len(ai_visited)
    hit_rate = round((total_ai_visited / total * 100), 1) if total > 0 else 0.0

    all_ratings = [f["rating"] for f in feedback_log if f.get("rating")]
    avg_satisfaction = round(sum(all_ratings) / len(all_ratings), 1) if all_ratings else 0.0

    # 식당별 통계 집계 (AI 추천 방문 및 RLHF 대안 방문 모두 포함)
    rest_stats: Dict[str, Dict] = {}
    for f in feedback_log:
        target_name = f["restaurant_name"] if f.get("visited") else (f.get("actual_restaurant_name") or f["restaurant_name"])
        if target_name not in rest_stats:
            rest_stats[target_name] = {"feedback_count": 0, "visit_count": 0, "total_rating": 0}
        rest_stats[target_name]["feedback_count"] += 1
        rest_stats[target_name]["visit_count"] += 1
        rest_stats[target_name]["total_rating"] += f.get("rating", 0)

    per_restaurant = []
    for name, s in rest_stats.items():
        avg_r = round(s["total_rating"] / s["visit_count"], 1) if s["visit_count"] > 0 else 0
        per_restaurant.append({
            "name": name,
            "feedback_count": s["feedback_count"],
            "visit_count": s["visit_count"],
            "avg_rating": avg_r
        })
    per_restaurant.sort(key=lambda x: x["avg_rating"], reverse=True)

    return {
        "total_feedback": total,
        "total_visited": total_ai_visited,
        "hit_rate": hit_rate,
        "avg_satisfaction": avg_satisfaction,
        "per_restaurant": per_restaurant
    }


@app.post("/recommend", response_model=RecommendationResponse, summary="표준 추천 API", tags=["Recommendation"])
async def get_recommendations(payload: RecommendationRequest):
    recs = recommender_engine.recommend(users=payload.users, restaurants=payload.restaurants, top_k=3)
    return RecommendationResponse(recommendations=recs)


# ═══════════════════════════════════════════════════════════════
# 프론트엔드 페이지 라우트
# ═══════════════════════════════════════════════════════════════

@app.get("/", response_class=FileResponse, summary="점심 추천 홈", tags=["UI"])
async def home_page():
    return FileResponse("static/index.html")


@app.get("/survey", response_class=FileResponse, summary="구성원 취향 설문", tags=["UI"])
async def survey_page():
    return FileResponse("static/survey.html")


@app.get("/dashboard", response_class=FileResponse, summary="추천 성과 대시보드", tags=["UI"])
async def dashboard_page():
    return FileResponse("static/dashboard.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
