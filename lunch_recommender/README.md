# 사내 점심 메뉴 추천 AI 서비스 (Lunch Recommendation AI Service)

사내 구성원의 취향·알러지·기피 음식 제약조건과 당일 자연어 대화를 결합해 점심 맛집 Top 3를 추천하는 **프로덕션 수준의 하이브리드 AI 마이크로서비스 및 웹 포털**입니다.

- **Backend / Frontend 분리 아키텍처**: `main.py`는 순수 REST API 및 정적 파일 호스팅을 담당하며, 프론트엔드(`static/` 폴더)는 모듈화된 HTML/CSS/JS 파일로 구성되어 향후 백엔드·프론트엔드 개발자 모두 독립적인 수정과 유지보수가 가능합니다.
- **실전형 하이브리드 알고리즘**: Least Misery(알러지/기피 100% 필터링) + Group Average CBF(콘텐츠 기반 유사도) + MAB UCB(탐색/활용 균형)를 통해 과적합 없이 동작합니다.

---

## 1. 프로젝트 폴더 구조 (Architecture & Modules)

```
lunch_recommender/
├── main.py                     # FastAPI 백엔드 API 서버 (엔드포인트 및 정적 에셋 서빙)
├── recommender.py              # 4단계 추천 알고리즘 핵심 엔진 (Least Misery + CBF + MAB UCB)
├── nlp_parser.py               # 자연어 점심 문맥 파서 (참여자, 제외 카테고리, 선호도 파싱)
├── schemas.py                  # Pydantic 데이터 스키마 정의 (User, Restaurant, RecommendationItem 등)
├── static/                     # 모듈화된 프론트엔드 에셋 디렉토리
│   ├── index.html              # 점심 메뉴 추천 검색 웹 홈 화면
│   ├── survey.html             # 구성원 입맛 설문 및 프로필 설정 화면
│   ├── css/style.css           # UI 공통 스타일시트
│   └── js/
│       ├── app.js              # 추천 검색 API 연동 및 결과 카드 렌더링 스크립트
│       └── survey.js           # 설문 관리 및 API 저장 스크립트
├── surveys_data.json           # 직원 입맛 설문 데이터 저장소
├── test_sample.py              # 파이프라인 자동화 검증 단위 테스트
├── Dockerfile                  # 도커 프로덕션 컨테이너 빌드 설정
├── start.sh / stop.sh          # 독립 포트(7120) 배포 및 관리 쉘 스크립트
└── PORTFOLIO_RECOMMENDATION_SYSTEM.md  # 기획자·PM·디자이너 직군 포트폴리오 안내서
```

---

## 2. 웹 서비스 및 엔드포인트 안내 (Port: 7120)

| 페이지 / 기능 | URL 경로 | 설명 |
|---|---|---|
| **🏠 추천 검색 홈** | `http://localhost:7120/` | 자연어로 점심 요구사항을 검색하고 사유가 포함된 Top 3 추천을 확인하는 화면 |
| **📝 취향 설문 포털** | `http://localhost:7120/survey` | 구성원이 본인의 입맛(맵기, 국물, 고기)과 알러지/기피 음식을 설정하는 화면 |
| **📘 API 명세서 (Swagger)** | `http://localhost:7120/docs` | 백엔드 API 연동을 위한 OpenAPI 명세서 및 인터랙티브 테스트 문서 |
| **💓 헬스체크 API** | `http://localhost:7120/health` | 서비스 상태 검사 및 등록된 구성원 프로필 수 반환 |

---

## 3. 백엔드 / 프론트엔드 유지보수 가이드

### 백엔드 개발자 (Backend API & AI Engine)
- **추천 로직 수정**: `recommender.py`의 `LunchRecommender` 클래스에서 CBF 유사도, Least Misery 조건, UCB 가중치 파라미터를 수정할 수 있습니다.
- **자연어 파싱 수정**: `nlp_parser.py`에서 사내 구성원 식별 규칙이나 카테고리 제외 키워드를 확장할 수 있습니다.
- **API 엔드포인트 추가**: `main.py`는 순수 REST API 엔드포인트(`/api/search`, `/api/survey`, `/recommend` 등)로 구성되어 있으므로 표준 FastAPI 방식으로 손쉽게 확장 가능합니다.

### 프론트엔드 개발자 (UI / UX)
- 모든 UI 코드는 `static/` 디렉토리 하위에 독립된 파일로 구성되어 있습니다.
- HTML(`index.html`, `survey.html`), CSS(`css/style.css`), JavaScript(`js/app.js`, `js/survey.js`)를 직접 편집하면 백엔드 코드 수정 없이 즉시 반영됩니다.

---

## 4. 서비스 시작 및 관리

```bash
# 컨테이너 빌드 및 7120 포트 서비스 실행
bash start.sh

# 서비스 종료
bash stop.sh
```
