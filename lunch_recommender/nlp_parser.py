import re
from typing import List, Dict, Any, Tuple
from schemas import User


def parse_lunch_prompt(
    prompt: str,
    existing_surveys: Dict[str, User]
) -> Tuple[List[User], Dict[str, Any], List[str], List[str]]:
    """
    자연어 입력을 분석하여 점심 추천에 필요한 문맥 정보를 추출합니다.
    - matched_users: 참여 직원 리스트
    - today_modifier: 당일 맛/선호도 보정 파라미터
    - excluded_categories: 제외할 음식 카테고리 (예: 저녁 중복 예정 메뉴)
    - context_notes: 파싱 결과 안내 노트
    """
    prompt_clean = prompt.strip()
    matched_users: List[User] = []
    found_names: List[str] = []

    # 1. 등록된 사내 직원 이름 매칭
    for user_id, user_obj in existing_surveys.items():
        if user_id in prompt_clean:
            matched_users.append(user_obj)
            found_names.append(user_id)

    # 2. 카테고리 제외 조건 — [Fix 1] 단순 언급이 아니라 '제외 의도'가 있을 때만 제외.
    #    기존엔 "일식 먹고싶어"처럼 원하는 카테고리를 말해도 제외돼 버렸다.
    excluded_categories = []
    context_notes = []

    CATS = ["중식", "일식", "양식", "분식", "한식"]
    # 카테고리 '뒤'에 오는 후치 제외 신호(한국어 조사: 빼고/말고/제외…) + 이미 먹은 문맥
    POST_CUES = ["제외", "빼고", "말고", "뺀", "먹음", "먹었", "질렸", "질림", "지겨", "지겹"]
    # 카테고리 '앞'에 오는 시간 문맥(저녁/어제 ~ 예정/먹음)
    PRE_CUES = ["저녁", "어제"]

    # 각 카테고리의 첫 등장 위치를 모아, 해당 카테고리 뒤 ~ 다음 카테고리 앞 구간만 검사
    positions = sorted(
        [(prompt_clean.find(c), c) for c in CATS if c in prompt_clean],
        key=lambda x: x[0]
    )
    for i, (pos, cat) in enumerate(positions):
        next_pos = positions[i + 1][0] if i + 1 < len(positions) else len(prompt_clean)
        after = prompt_clean[pos + len(cat): next_pos]      # 이 카테고리 뒤(다음 카테고리 전까지)
        before = prompt_clean[max(0, pos - 8): pos]         # 카테고리 앞 8글자
        if any(cue in after for cue in POST_CUES) or any(cue in before for cue in PRE_CUES):
            excluded_categories.append(cat)

    if excluded_categories:
        context_notes.append(f"🚫 제외 의도 감지 카테고리: {', '.join(excluded_categories)}")

    # 3. 오늘의 기분 / 맛 선호 조건 분석
    today_modifier: Dict[str, Any] = {}

    # 매운맛/매콤한 맛
    if any(k in prompt_clean for k in ["매콤", "매운", "얼큰", "칼칼", "불닭", "마라", "맵게"]):
        today_modifier["spicy_level"] = 4.8
        context_notes.append("🌶️ 오늘의 맛 선호: 매콤/얼큰한 맛 강력 반영")
    elif any(k in prompt_clean for k in ["순한", "안매운", "담백"]):
        today_modifier["spicy_level"] = 1.0
        context_notes.append("🥬 오늘의 맛 선호: 담백/순한 맛 반영")

    # 국물 여부
    if any(k in prompt_clean for k in ["국물", "찌개", "탕", "전골", "국밥"]):
        today_modifier["soup"] = True
        context_notes.append("🍲 국물 요리 중심")
    elif any(k in prompt_clean for k in ["볶음", "구이", "덮밥", "비빔", "국물없이"]):
        today_modifier["soup"] = False
        context_notes.append("🍛 국물 없는 요리 중심")

    # 고기 여부
    if any(k in prompt_clean for k in ["고기", "육류", "삼겹살", "소고기", "제육"]):
        today_modifier["meat"] = True
        context_notes.append("🥩 고기 위주 요리")

    # 4. 검색 키워드 및 맑은 국물 요리 스타일 분석
    if any(k in prompt_clean for k in ["맑은탕", "맑은 국물", "지리", "복국", "연포탕", "곰탕", "맑은"]):
        today_modifier["soup"] = True
        today_modifier["clear_soup"] = True
        today_modifier["spicy_level"] = 1.0
        context_notes.append("🥣 맑고 개운한 국물 요리 중심 (맑은탕/지리 우선 매칭)")

    filler_words = ["추천해줘", "추천", "오늘", "점심", "뭐먹지", "부탁해", "먹고싶어", "메뉴", "좀"]
    query_text = prompt_clean
    for fw in filler_words:
        query_text = query_text.replace(fw, "")
    today_modifier["query_keyword"] = query_text.strip()
    today_modifier["raw_query"] = prompt_clean

    return matched_users, today_modifier, excluded_categories, context_notes
