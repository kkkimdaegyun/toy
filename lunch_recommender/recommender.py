import math
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from schemas import User, Restaurant, RecommendationItem


# 카테고리별 기본 속성 추정값 (네이버 API 식당 → Restaurant 변환 시 사용)
CATEGORY_ATTRIBUTE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "한식":   {"spicy_level": 3.0, "soup": True,  "meat": True},
    "중식":   {"spicy_level": 3.5, "soup": True,  "meat": True},
    "일식":   {"spicy_level": 1.5, "soup": True,  "meat": True},
    "양식":   {"spicy_level": 1.0, "soup": False, "meat": True},
    "분식":   {"spicy_level": 2.5, "soup": False, "meat": False},
    "치킨":   {"spicy_level": 2.0, "soup": False, "meat": True},
    "피자":   {"spicy_level": 1.0, "soup": False, "meat": True},
    "햄버거": {"spicy_level": 1.0, "soup": False, "meat": True},
    "카페":   {"spicy_level": 0.0, "soup": False, "meat": False},
    "아시안": {"spicy_level": 3.0, "soup": True,  "meat": True},
    "샐러드": {"spicy_level": 0.0, "soup": False, "meat": False},
    "고기":   {"spicy_level": 2.0, "soup": False, "meat": True},
    "해산물": {"spicy_level": 2.0, "soup": True,  "meat": False},
    "국밥":   {"spicy_level": 2.5, "soup": True,  "meat": True},
    "찌개":   {"spicy_level": 3.5, "soup": True,  "meat": True},
    "면류":   {"spicy_level": 2.5, "soup": True,  "meat": False},
    "기타":   {"spicy_level": 2.0, "soup": False, "meat": True},
}


# [Fix 5-b] 네이버 실데이터는 ingredients가 비어 있어 알러지 필터가 무력화됨.
# 카테고리 대표 재료 + 식당명 토큰으로 '추정 재료'를 채워 Least Misery 안전장치를 복구.
# (안전 방향으로 보수적 추정: 확실치 않으면 과하게라도 제외하는 편이 Zero Tolerance에 부합)
CATEGORY_TYPICAL_INGREDIENTS: Dict[str, List[str]] = {
    "한식":   ["마늘", "고춧가루"],
    "중식":   ["돼지고기", "춘장"],
    "일식":   ["생선", "간장"],
    "양식":   ["밀", "치즈", "우유"],
    "분식":   ["밀", "떡"],
    "치킨":   ["닭고기", "밀"],
    "피자":   ["밀", "치즈", "우유"],
    "햄버거": ["밀", "소고기", "우유"],
    "카페":   [],
    "아시안": ["땅콩", "코코넛"],
    "샐러드": ["채소"],
    "고기":   ["소고기", "돼지고기"],
    "해산물": ["갑각류", "새우", "조개", "생선"],
    "국밥":   ["돼지고기"],
    "찌개":   ["돼지고기", "두부"],
    "면류":   ["밀"],
    "기타":   [],
}

# 식당명 토큰 → 잠재 알러지원 추정 (카테고리로 못 잡는 케이스 보강)
NAME_ALLERGEN_HINTS: Dict[str, List[str]] = {
    "해물": ["갑각류", "새우", "조개", "오징어"],
    "해산물": ["갑각류", "새우", "조개"],
    "새우": ["새우", "갑각류"],
    "게": ["갑각류", "게"],
    "랍스터": ["갑각류"],
    "가재": ["갑각류"],
    "조개": ["조개"],
    "굴": ["조개", "굴"],
    "복": ["생선", "복어"],
    "생선": ["생선"],
    "회": ["생선"],
    "초밥": ["생선", "새우"],
    "스시": ["생선", "새우"],
    "땅콩": ["땅콩"],
    "우유": ["우유"],
    "치즈": ["우유"],
}


def infer_ingredients(name: str, category: str) -> List[str]:
    """카테고리 대표 재료 + 이름 토큰 힌트로 잠재 재료(알러지 검증용)를 추정한다."""
    ings = list(CATEGORY_TYPICAL_INGREDIENTS.get(category, []))
    lname = (name or "").lower()
    for token, allergens in NAME_ALLERGEN_HINTS.items():
        if token in lname:
            ings.extend(allergens)
    # 중복 제거(순서 유지)
    seen = set()
    result = []
    for i in ings:
        if i not in seen:
            seen.add(i)
            result.append(i)
    return result


# [Fix 2] '요리 종류'를 명시한 키워드 → 점수 가산이 아니라 '하드 프리필터' 대상.
# (예: "돈까스 먹자" → 돈까스 파는 곳만 후보로. 매칭이 하나도 없으면 원복=Fallback)
DISH_KEYWORDS: Dict[str, List[str]] = {
    "버거": ["버거", "햄버거", "burger", "맥도날드", "버거킹", "크라이치즈", "프랭크", "쉐이크쉑", "롯데리아", "맘스터치"],
    "피자": ["피자", "pizza"],
    "돈까스": ["돈까스", "돈카츠", "카츠", "katsu"],
    "초밥": ["초밥", "스시", "sushi", "오마카세"],
}


class LunchRecommender:
    """
    사내 점심 메뉴 추천 엔진
    4단계 하이브리드 파이프라인:
      1) Least Misery (알러지·기피 100% 필터링)
      2) Group Average CBF (맵기·국물·고기 코사인 유사도)
      3) Category Preference (설문 Q6 카테고리 선호도 반영)
      4) MAB UCB (피드백 기반 탐색/활용 균형)

    최종 출력: 0~100% 팀원 취향 매칭률
    """

    def __init__(
        self,
        cbf_weight: float = 0.30,
        category_weight: float = 0.25,
        exploit_weight: float = 0.30,
        explore_weight: float = 0.15,
        ucb_c: float = 1.2,
    ):
        self.cbf_weight = cbf_weight
        self.category_weight = category_weight
        self.exploit_weight = exploit_weight
        self.explore_weight = explore_weight
        self.ucb_c = ucb_c

    # ── 1단계: Least Misery 필터링 ───────────────────────────────────

    def _check_least_misery(self, users: List[User], restaurant: Restaurant) -> Tuple[bool, List[str]]:
        """한 명이라도 알러지/기피 음식 충돌 시 후보에서 제외"""
        conflicts = []
        ingredients = [ing.lower().strip() for ing in restaurant.attributes.ingredients]
        rest_name = restaurant.name.lower()

        for user in users:
            for allergy in user.allergies:
                a = allergy.lower().strip()
                if not a:
                    continue
                if any(a in ing or ing in a for ing in ingredients) or a in rest_name:
                    conflicts.append(f"{user.user_id} 알러지({allergy})")

            for dislike in user.dislikes:
                d = dislike.lower().strip()
                if not d:
                    continue
                if any(d in ing or ing in d for ing in ingredients) or d in rest_name:
                    conflicts.append(f"{user.user_id} 기피({dislike})")

        return len(conflicts) == 0, conflicts

    # ── 2단계: Content-Based Filtering ───────────────────────────────

    def _feature_similarity(self, pref: Dict[str, Any], rest_dict: Dict[str, Any]) -> float:
        """
        [Fix 3] 코사인 대신 '거리 기반' 특징 유사도.
        코사인은 (1) 모든 성분이 1사분면이라 값이 [0.5,1] 상단에 압축되고,
        (2) 크기(magnitude)를 무시해 '매콤 선호 vs 순한 식당'의 차이를 못 잡으며,
        (3) 불리언 soup/meat가 연속형 spicy를 압도하는 문제가 있었다.
        → 각 특징을 [0,1]로 맞춘 뒤 '근접도(1-|차이|)'를 가중 평균한다. (반환 0~1)
        """
        su = min(max(float(pref.get("spicy_level", 3.0)) / 5.0, 0.0), 1.0)
        sr = min(max(float(rest_dict.get("spicy_level", 3.0)) / 5.0, 0.0), 1.0)
        spicy_sim = 1.0 - abs(su - sr)
        soup_sim = 1.0 if bool(pref.get("soup", False)) == bool(rest_dict.get("soup", False)) else 0.0
        meat_sim = 1.0 if bool(pref.get("meat", False)) == bool(rest_dict.get("meat", False)) else 0.0
        # spicy(오늘의 기분 축)에 더 큰 가중치. 합=1.0 → 결과는 [0,1].
        return 0.5 * spicy_sim + 0.25 * soup_sim + 0.25 * meat_sim

    def _compute_group_cbf(self, users: List[User], restaurant: Restaurant) -> float:
        """Group Average Strategy: 참여자 전원의 특징 유사도 평균"""
        if not users:
            return 0.0
        rest_dict = restaurant.attributes.model_dump()
        scores = [self._feature_similarity(user.preferences, rest_dict) for user in users]
        return float(np.mean(scores))

    # ── 3단계: Category Preference (설문 Q6) ─────────────────────────

    def _compute_category_preference(self, users: List[User], category: str) -> float:
        """참여자들의 해당 카테고리 선호도 평균 (0.0~1.0)"""
        scores = []
        for user in users:
            if user.category_scores and category in user.category_scores:
                scores.append(user.category_scores[category] / 5.0)
            else:
                scores.append(0.6)  # 기본값 3/5
        return float(np.mean(scores)) if scores else 0.6

    # ── 4단계: MAB UCB 스코어링 ──────────────────────────────────────

    def _compute_final_score(
        self,
        group_cbf: float,
        category_pref: float,
        restaurant: Restaurant,
        total_clicks: int
    ) -> Tuple[float, float, float]:
        """
        가중합 → 0~100% 매칭률 환산

        final = cbf_weight × CBF유사도
              + category_weight × 카테고리선호도
              + exploit_weight × 평균만족도(피드백)
              + explore_weight × UCB탐색보너스
        """
        mab = restaurant.mab_stats
        clicks = mab.clicks if mab else 0
        avg_reward = mab.avg_reward if mab else 0.0

        # [Fix 4] Exploitation: 콜드스타트 낙관적 사전(Bayesian smoothing).
        # 기존엔 미방문 식당 avg_reward=0 → exploit=0/5=0.0 이라 '0점 맛집'으로 오판됐다.
        # 사전평균 3.5점(별점)·가상표본 3표로 스무딩 → 미방문은 중립(0.7)에서 출발,
        # 데이터가 쌓일수록 실제 평점으로 수렴한다.
        PRIOR_MEAN, PRIOR_STRENGTH = 3.5, 3
        total_reward = avg_reward * clicks
        smoothed_reward = (total_reward + PRIOR_MEAN * PRIOR_STRENGTH) / (clicks + PRIOR_STRENGTH)
        exploit_score = min(max(smoothed_reward / 5.0, 0.0), 1.0)

        # Exploration: UCB 신뢰구간 보너스
        if total_clicks > 0 and clicks > 0:
            ucb_bonus = self.ucb_c * math.sqrt(math.log(total_clicks + 1) / (clicks + 1))
        else:
            ucb_bonus = self.ucb_c * 0.8  # 미방문 식당에 탐색 보너스 부여

        # 가중합 → 0~100%
        raw = (
            self.cbf_weight * group_cbf
            + self.category_weight * category_pref
            + self.exploit_weight * exploit_score
            + self.explore_weight * min(ucb_bonus, 1.0)
        )
        final_percent = round(min(raw * 100.0, 100.0), 1)

        return final_percent, exploit_score, ucb_bonus

    # ── 추천 사유 생성 ──────────────────────────────────────────────

    def _generate_reason(
        self,
        restaurant: Restaurant,
        group_cbf: float,
        category_pref: float,
        clicks: int,
        avg_reward: float
    ) -> str:
        parts = []
        cat = restaurant.attributes.category

        if category_pref >= 0.8:
            parts.append(f"멤버들이 선호하는 {cat} 카테고리이며")
        elif category_pref >= 0.6:
            parts.append(f"{cat} 카테고리를 대체로 좋아하는 멤버 구성이고")
        else:
            parts.append(f"다양한 입맛을 고려한 {cat} 선택이며")

        if group_cbf >= 0.7:
            parts.append("맵기·국물·고기 취향 매칭이 높고")
        elif group_cbf >= 0.4:
            parts.append("전반적인 맛 취향에 부합하며")

        parts.append("알러지·기피 안전 검증 통과.")

        if clicks >= 3 and avg_reward >= 4.0:
            parts.append(f"구성원 평균 만족도 {avg_reward:.1f}점 검증 맛집.")
        elif clicks >= 1:
            parts.append(f"구성원 {clicks}건 피드백 반영.")
        else:
            parts.append("신규 탐색(MAB Exploration) 추천.")

        return " ".join(parts)

    # ── [Fix 2] 명시적 음식 = 하드 프리필터, 일반 키워드 = 부드러운 신호 ──

    def _detect_explicit_dish(self, query_text: str) -> Optional[str]:
        """질의에 '요리 종류'가 명시됐으면 그 종류를 반환(하드 필터용). 없으면 None."""
        if not query_text:
            return None
        q = query_text.lower()
        for dish, kws in DISH_KEYWORDS.items():
            if any(k in q for k in kws):
                return dish
        return None

    def _dish_matches(self, rest: Restaurant, dish: str) -> bool:
        hay = f"{rest.name} {rest.attributes.category}".lower()
        return any(k in hay for k in DISH_KEYWORDS[dish])

    def _soft_keyword_signal(self, rest: Restaurant, query_text: str) -> float:
        """
        맑은탕/국물/일반명사 등 '부드러운' 질의 적합도를 [-1, 1]로 반환.
        기존 ±45~55점 가산은 ML 전체(50~70%대)를 덮어써 순위를 전복시켰다.
        → 정규화된 신호로 바꿔 recommend()에서 '가중 재랭킹'(±%)으로만 반영한다.
        """
        if not query_text:
            return 0.0
        q = query_text.lower()
        name = rest.name.lower()
        cat = rest.attributes.category.lower()

        # 맑은 국물 요청
        if any(k in q for k in ["맑은", "맑은탕", "지리", "복국", "연포탕", "곰탕"]):
            if any(k in name for k in ["복국", "복집", "지리", "곰탕", "설렁탕", "대구지리", "맑은", "나주곰탕", "연포"]):
                return 0.8
            if "개미집" in name:
                return 0.4
            if any(k in name for k in ["우대갈비", "갈비", "삼겹살", "돈카츠", "돈까스", "마라탕", "불짬뽕", "닭볶음탕"]):
                return -0.7
            return 0.0
        # 일반 국물/탕/찌개
        if any(k in q for k in ["국물", "탕", "찌개", "전골", "해장"]):
            if rest.attributes.soup or any(k in name for k in ["탕", "찌개", "국", "전골", "짬뽕", "라멘"]):
                return 0.5
            return -0.4

        # 일반 명사 키워드가 식당명/카테고리에 직접 포함
        ignore_words = {"추천해줘", "추천", "오늘", "점심", "뭐먹지", "부탁해", "먹고싶어", "메뉴", "맛집", "근처"}
        for w in q.split():
            if len(w) >= 2 and w not in ignore_words and (w in name or w in cat):
                return 0.6
        return 0.0


    def _infer_menu_and_reason(self, rest: Restaurant, query_text: str, base_reason: str) -> Tuple[str, str]:
        """식당별 추천 대표 메뉴(rec_menu) 및 맞춤 추천 사유 생성"""
        q = (query_text or "").lower()
        name = rest.name
        cat = rest.attributes.category

        if "어글리버거" in name or "ugly" in name.lower():
            return ("어글리 더블 치즈버거 세트 / 아보카도 버거", "두툼한 육즙 패티와 신선한 재료가 일품인 수제버거 맛집입니다. " + base_reason)
        elif "맥도날드" in name:
            return ("빅맥 맥런치 세트 / 베이컨 토마토 디럭스", "빠르고 든든하게 즐기는 대표 버거 런치 세트입니다. " + base_reason)
        elif any(k in name for k in ["버거", "burger", "크라이치즈", "프랭크"]):
            return ("시그니처 수제 치즈버거 세트", "육즙 가득한 패티와 바삭한 감자튀김을 함께 즐기는 점심 특선 버거 세트입니다. " + base_reason)
        elif "우대갈비" in name or "전설의우대갈비" in name:
            if any(k in q for k in ["맑은", "탕", "국물"]):
                return ("한우 왕갈비탕 점심 특선", "고기 전문점에서 깊게 우려낸 시원하고 개운한 점심 갈비탕입니다. " + base_reason)
            return ("소갈비살 정식 [Lunch 특선 28,000원]", "점심 시간에 부담 없이 프리미엄 소갈비 본연의 풍미를 든든하게 즐길 수 있는 런치 정식입니다. " + base_reason)
        elif "갈비" in name:
            return ("점심 특선 소갈비살 정식 / 갈비탕", "점심 특선으로 든든하고 고품격으로 즐기는 고기 정식 메뉴입니다. " + base_reason)
        elif "개미집" in name:
            if any(k in q for k in ["맑은", "맑은탕", "지리", "국물"]):
                return ("낙지 맑은 연포탕 / 조개탕", "개미집에서 개운하고 깔끔한 국물을 원하실 때 가장 맞춤인 시원한 낙지 연포탕 메뉴를 추천합니다. " + base_reason)
            return ("낙곱새 (낙지+곱창+새우 전골) 점심 특선", "개미집의 시그니처 매콤하고 든든한 전골 요리입니다. " + base_reason)
        elif any(k in name for k in ["복국", "복집", "대림복국", "지리"]):
            return ("참복 맑은 지리탕 / 밀복국", "요청하신 '맑은탕'에 완벽히 부합하는 시원하고 깔끔한 국물 요리 맛집입니다. " + base_reason)
        elif any(k in name for k in ["곰탕", "나주곰탕", "설렁탕"]):
            return ("한우 맑은 나주곰탕 / 수육곰탕", "기름기 없이 맑고 깊게 우려낸 국물로 '맑은 국물' 요청에 최적화된 메뉴입니다. " + base_reason)
        elif "참치공방" in name or "참치" in name:
            return ("점심 참치회 정식 / 특회덮밥", "신선한 참치와 알차게 구성된 점심 특선 코스 및 덮밥 메뉴입니다. " + base_reason)
        elif "라멘" in name:
            return ("정통 오사카 돈코츠 / 카라미소 라멘", "진하고 뜨끈한 면발과 깊은 맛의 국물을 함께 즐길 수 있는 추천 메뉴입니다. " + base_reason)
        elif "짬뽕" in name or cat == "중식":
            if any(k in q for k in ["맑은", "담백"]):
                return ("해물 백짬뽕 / 맑은 우동 정식", "자극적이지 않고 개운하고 담백한 육수를 낸 맑은 중식 요리입니다. " + base_reason)
            return ("얼큰 차돌 불짬뽕 & 찹쌀 탕수육 세트", "얼큰하고 진한 국물과 바삭한 탕수육이 어우러진 인기 메뉴입니다. " + base_reason)
        elif "닭볶음탕" in name:
            return ("묵은지 뚝배기 닭볶음탕 특선", "칼칼하고 든든하게 즐기는 대표 한식 국물 메뉴입니다. " + base_reason)
        elif "돈카츠" in name or "돈까스" in name or "카츠" in name:
            return ("겉바속촉 로스 돈카츠 & 미니 우동 정식", "바삭하게 튀겨낸 두툼한 카츠와 시원한 국물을 함께 즐기는 런치 세트입니다. " + base_reason)
        elif any(k in name for k in ["초밥", "스시", "sushi"]):
            return ("오늘의 특선 초밥 정식 (런치 12p)", "신선한 네타와 알찬 구성으로 든든한 점심 특선 스시 메뉴입니다. " + base_reason)
        elif any(k in name for k in ["피자", "pizza", "파스타"]):
            return ("런치 프리미엄 화덕피자 / 파스타 세트", "풍부한 치즈와 풍미를 자랑하는 대표 양식 런치 메뉴입니다. " + base_reason)
        else:
            if cat == "한식":
                return ("오늘의 점심 제육 쌈정식 / 특선 찌개 정식", "한국인이 가장 사랑하는 든든하고 깔끔한 가정식 점심 정식입니다. " + base_reason)
            elif cat == "일식":
                return ("생연어 사케동 & 돈카츠 정식", "깔끔하고 정갈한 일식 런치 인기 정식입니다. " + base_reason)
            elif cat == "양식":
                return ("런치 특선 파스타 & 스테이크 샐러드", "분위기 있고 맛있는 점심 식사를 위한 추천 런치 메뉴입니다. " + base_reason)
            elif cat == "분식":
                return ("스페셜 즉석 떡볶이 & 모둠 튀김 세트", "푸짐하고 맛있게 먹는 대표 분식 세트입니다. " + base_reason)
            else:
                return (f"{rest.name} 점심 대표 인기 특선 메뉴", base_reason)

    # ── 메인 파이프라인 ──────────────────────────────────────────────

    def recommend(
        self,
        users: List[User],
        restaurants: List[Restaurant],
        top_k: int = 3,
        query_text: str = ""
    ) -> List[RecommendationItem]:
        """
        전체 추천 파이프라인 실행:
        Least Misery → Group CBF → Category Preference → MAB UCB → Query Keyword Match → Top K
        """
        # 0) [Fix 2] 명시적 음식 종류(버거/피자/돈까스/초밥) → 하드 프리필터.
        #    해당 음식 파는 곳만 후보로 좁힌다. 하나도 없으면 원복(Fallback).
        dish = self._detect_explicit_dish(query_text)
        if dish:
            matched = [r for r in restaurants if self._dish_matches(r, dish)]
            if matched:
                restaurants = matched

        total_clicks = sum((r.mab_stats.clicks if r.mab_stats else 0) for r in restaurants)

        scored = []
        for rest in restaurants:
            # 1) Least Misery 필터
            is_safe, conflicts = self._check_least_misery(users, rest)
            if not is_safe:
                continue

            # 2) Group Average CBF
            group_cbf = self._compute_group_cbf(users, rest)

            # 3) Category Preference
            category_pref = self._compute_category_preference(users, rest.attributes.category)

            # 4) MAB UCB → 0~100% 매칭률
            final_score, exploit, explore = self._compute_final_score(
                group_cbf, category_pref, rest, total_clicks
            )

            # 5) [Fix 2] 부드러운 키워드 신호를 '가중 재랭킹'(±35%)으로만 반영.
            #    기존 ±45~55 '덧셈'이 ML 전체(50~70%대)를 덮어써 순위를 전복시키던 문제 해소.
            kw_signal = self._soft_keyword_signal(rest, query_text)   # [-1, 1]
            adjusted_score = round(min(max(final_score * (1.0 + 0.35 * kw_signal), 5.0), 99.5), 1)

            clicks = rest.mab_stats.clicks if rest.mab_stats else 0
            avg_reward = rest.mab_stats.avg_reward if rest.mab_stats else 0.0
            base_reason = self._generate_reason(rest, group_cbf, category_pref, clicks, avg_reward)

            rec_menu, tailored_reason = self._infer_menu_and_reason(rest, query_text, base_reason)

            scored.append(RecommendationItem(
                rest_id=rest.rest_id,
                name=rest.name,
                category=rest.attributes.category,
                final_score=adjusted_score,
                recommended_menu=rec_menu,
                reason=tailored_reason
            ))

        scored.sort(key=lambda x: x.final_score, reverse=True)
        return scored[:top_k]
