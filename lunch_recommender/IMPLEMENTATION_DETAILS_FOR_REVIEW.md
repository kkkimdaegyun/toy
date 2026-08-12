# 사내 맞춤 점심 메뉴 AI 추천 시스템 — 전체 구현 기능 및 아키텍처 상세 보고서 (외부 검토용)

이 보고서는 **Claude** 등 외부 AI 및 코드 리뷰어가 본 프로젝트(`lunch_recommender`)의 아키텍처, 추천 알고리즘 설계, NLP 처리 방식, UI/UX 및 데이터 동기화 메커니즘을 엄밀하게 검토할 수 있도록 상세히 서술한 문서입니다.

---

## 1. 시스템 개요 및 기술 스택 (System Overview & Stack)

- **Backend**: Python 3.11 + **FastAPI** (비동기 REST API 서버)
- **Frontend**: Vanilla HTML5, CSS3 (Glassmorphism & Responsive Design), Vanilla ES6 JavaScript
- **Recommendation Engine**: 하이브리드 추천 파이프라인 (Least Misery + Group CBF + Category Pref + MAB UCB + Keyword Strict Matching)
- **External API**: 네이버 지역 검색 API (`Naver Local Search API`) — 상암동 누리꿈스퀘어 1km 반경 실제 식당 매칭
- **Persistence Layer**: 파일 기반 JSON DB (`surveys_data.json`) — Linux / GPU 서버 환경 버퍼링 방지를 위한 `f.flush() + os.fsync()` 강제 동기화

---

## 2. 핵심 5단계 하이브리드 추천 알고리즘 (5-Stage Hybrid Recommendation Engine)

백엔드의 `recommender.py`는 단일 추천 기법의 한계(콜드스타트, 취향 왜곡)를 극복하기 위해 **5단계 다층 파이프라인**을 실행합니다.

```
[입력: 식당 풀 & 사용자 목록 & 검색어]
        │
        ▼
[Step 1. Least Misery Hard Filter]  ──(알러지/기피 부합 시 즉시 제외)──► Discard
        │ (통과)
        ▼
[Step 2. Group Average CBF]         ──(참여자 집단 코사인 유사도 연산)
        │
        ▼
[Step 3. Category Preference Matrix]──(1~5점 카테고리 선호 가중치 합산)
        │
        ▼
[Step 4. MAB (UCB Algorithm)]       ──(Exploit 보상 + Explore 탐색 보정)
        │
        ▼
[Step 5. Query Keyword Strict Match]──(메뉴/명사 일치 +55점, 불일치 -45점 페널티)
        │
        ▼
[출력: Top 3 맞춤 식당 + 실제 점심 특선 메뉴 + 개인/집단 맞춤 사유]
```

### Step 1. Least Misery Filter (절대 기피 및 알러지 안전 검증)
- 다인원 점심 결정 시 한 명이라도 먹지 못하는 음식이 선정되는 것을 방지합니다.
- 각 참여자의 `allergies`(예: 땅콩, 갑각류, 우유) 및 `dislikes`(예: 돼지고기, 오이 등)와 식당의 재료(`ingredients`) 및 카테고리를 대조하여 **치명적 충돌이 감지되면 식당 후보군에서 Hard Filtering으로 100% 제외**합니다.

### Step 2. Group Average CBF (콘텐츠 기반 집단 협업 필터링)
- 각 참여자의 설문 선호 벡터 `[spicy_level(0~5), soup(0/1), meat(0/1)]`의 산술 평균 벡터를 계산합니다.
- 식당 속성 벡터 간의 **코사인 유사도(Cosine Similarity)**를 연산하여 0.0 ~ 1.0 범위의 기본 적합도 점수를 산출합니다.

### Step 3. Category Preference Matrix (카테고리 선호도 행렬)
- 참여 구성원들의 `category_scores`(한식, 중식, 일식, 양식 등 1~5점)를 합산 정규화하여, 집단이 공통적으로 선호하는 카테고리에 점수 가중치를 부여합니다.

### Step 4. MAB (Multi-Armed Bandit — Upper Confidence Bound, UCB1)
- 사용자의 실시간 피드백(`👍 추천 방문함`, `👎 다른 곳 방문`)이 누적됨에 따라, 단순 CBF 점수에 머무르지 않고 실제 방문 성과를 학습합니다.
- 수식:
  $$\text{Score} = w_1 \cdot \text{CBF} + w_2 \cdot \text{CatPref} + w_3 \cdot \hat{\mu}_i + c \sqrt{\frac{\ln t}{N_i}}$$
  - 방문 건수가 많은 검증된 맛집은 평균 만족도($\hat{\mu}_i$)를 활용(Exploit)하고, 신규 식당은 탐색 보너스($\sqrt{\ln t / N_i}$)를 줘서 다양한 식당을 발굴(Explore)합니다.

### Step 5. Query Keyword Strict Match & 실제 점심 메뉴 추론
- 사용자가 명시적으로 입력한 음식 키워드(`햄버거`, `버거`, `피자`, `돈까스`, `초밥`, `맑은탕` 등)가 식당명 또는 카테고리와 매칭될 경우 **+50~55점의 강력 부스트**를 부여하고, 불일치 식당에는 **-40~45점의 페널티**를 적용합니다.
- 식당명과 카테고리를 분석해 추상적인 `~ 시그니처 대표 메뉴`가 아닌 **실제 직장인 점심 런치 메뉴**를 반환합니다:
  - 예: `전설의우대갈비` 👉 `소갈비살 정식 [Lunch 특선 28,000원]`
  - 예: `어글리버거` 👉 `어글리 더블 치즈버거 세트 / 아보카도 버거`
  - 예: `개미집` 👉 `낙곱새 (낙지+곱창+새우 전골) 점심 특선`

---

## 3. 자연어 처리(NLP) 및 참여자 동적 매칭 (`nlp_parser.py`)

- **멘션 파싱 (`@이름`)**: 자연어 질의 내 `@대균 @윤아 국물 있는 한식` 입력 시 서버 DB에서 해당 구성원들의 12개 문항 취향 데이터만을 추출해 그룹 추천을 수행합니다. 멘션이 없을 경우 등록된 사내 인원 전체 평균 취향을 반영합니다.
- **제외 조건 파싱**: `중식 제외`, `일식 빼고` 등의 문구를 파싱해 해당 카테고리를 후보군에서 즉시 제거합니다.
- **맛/상태 보정**: `얼큰한`, `해장`, `담백한`, `맑은탕` 등의 표현을 인지해 당일 추천 벡터를 동적으로 조정합니다.

---

## 4. 데이터 영구 저장 및 안전 동기화 메커니즘 (`main.py`)

- **OS 버퍼링 방지 (`os.fsync`)**:
  ```python
  def save_surveys():
      with open(SURVEY_FILE, "w", encoding="utf-8") as f:
          json.dump({k: v.model_dump() for k, v in employee_surveys.items()}, f, ensure_ascii=False, indent=2)
          f.flush()
          os.fsync(f.fileno())  # OS 페이지 캐시를 디스크 물리 블록으로 즉시 동기화
  ```
  - Linux / A6000 서버 등에서 파일 입출력 버퍼로 인해 데이터가 유실되는 현상을 완벽히 차단했습니다.

---

## 5. 프론트엔드 UI/UX 및 편의 기능 (`app.js`, `survey.js`)

1. **상단 실시간 설문 완료자 뱃지 & 통계 모달**:
   - 모든 페이지 우측 상단에 **`✅ 대균님 설문 완료 (총 1명) [📊 명단/통계]`** 고정 뱃지 노출.
   - 5초 간격으로 백엔드 API(`GET /api/surveys/stats`)를 실시간 폴링하여 새로고침 없이 다른 직원의 설문 완료 여부를 즉시 반영합니다.
2. **설문 작성 완료 후 즉시 복귀 플로우**:
   - 12개 문항 취향 설문 제출 완료 시, 저장 확인 안내와 함께 즉시 메인 추천 홈(`/`)으로 자동 이동(`location.href="/"`)합니다.
3. **테스트용 전체 초기화 기능**:
   - 모달 창 하단 및 네비게이션 바에 **`🗑️ 설문 전체 초기화 (테스트용)`** 버튼 탑재.
   - 클릭 시 `DELETE /api/surveys/reset`을 호출해 DB를 0건으로 리셋하고 로컬스토리지까지 초기화합니다.

---

## 6. 주요 API 엔드포인트 목록

| HTTP Method | Endpoint | 설명 |
| :--- | :--- | :--- |
| `POST` | `/api/search` | 자연어 질의 및 구성원 취향 기반 Top 3 점심 식당 추천 |
| `POST` | `/api/survey` | 직원 12개 문항 취향 설문 등록 및 디스크 영구 저장 |
| `GET` | `/api/surveys` | 전체 등록된 직원 설문 목록 조회 |
| `GET` | `/api/surveys/stats` | 설문 참여자 명단 및 카테고리/알러지 취합 통계 조회 |
| `DELETE/POST` | `/api/surveys/reset` | (테스트용) 저장된 모든 설문 DB 0건 초기화 |
| `POST` | `/api/feedback` | 식당별 방문 및 평가 피드백 저장 (MAB Bandit 갱신) |
| `GET` | `/api/mab-stats` | AI 성과 대시보드용 방문 통계 및 만족도 지표 반환 |
