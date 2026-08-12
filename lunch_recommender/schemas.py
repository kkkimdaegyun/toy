from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class User(BaseModel):
    user_id: str = Field(..., description="직원 이름 (식별 ID)")
    department: Optional[str] = Field(default="", description="부서")
    position: Optional[str] = Field(default="", description="직급")
    allergies: List[str] = Field(default_factory=list, description="알러지 식품 목록")
    dislikes: List[str] = Field(default_factory=list, description="절대 못 먹는 음식 목록")
    category_scores: Dict[str, int] = Field(default_factory=dict, description="카테고리별 선호도 1~5점")
    taste_preferences: Dict[str, int] = Field(default_factory=dict, description="음식 취향 1~5점")
    lunch_styles: List[str] = Field(default_factory=list, description="점심 식사 스타일")
    budget: Optional[str] = Field(default="", description="점심 예산")
    recent_favorites: Optional[str] = Field(default="", description="최근 자주 드신 음식")
    recent_fatigue: Optional[str] = Field(default="", description="최근 질린 음식")
    priority_order: List[str] = Field(default_factory=list, description="추천 중요 순위")
    data_collection_consent: bool = Field(default=True, description="데이터 수집 동의")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="추천 엔진 연동용 핵심 선호도")


class RestaurantAttributes(BaseModel):
    category: str = Field(default="한식", description="음식 카테고리")
    spicy_level: float = Field(default=3.0, description="맵기 수준 0~5")
    soup: bool = Field(default=True, description="국물 요리 여부")
    meat: bool = Field(default=True, description="고기 포함 여부")
    ingredients: List[str] = Field(default_factory=list, description="주요 재료")

    class Config:
        extra = "allow"


class MABStats(BaseModel):
    clicks: int = Field(default=0, description="방문/피드백 횟수")
    avg_reward: float = Field(default=0.0, description="평균 만족도 (5점 만점)")


class Restaurant(BaseModel):
    rest_id: str = Field(..., description="식당 식별 ID")
    name: str = Field(..., description="식당 이름")
    attributes: RestaurantAttributes = Field(..., description="식당 속성")
    mab_stats: Optional[MABStats] = Field(default_factory=MABStats, description="MAB 통계")


class RecommendationRequest(BaseModel):
    users: List[User] = Field(..., description="점심 참여 직원 리스트")
    restaurants: List[Restaurant] = Field(..., description="후보 식당 리스트")


class RecommendationItem(BaseModel):
    rest_id: str = Field(..., description="식당 식별 ID")
    name: str = Field(..., description="식당 이름")
    category: str = Field(default="", description="음식 카테고리")
    final_score: float = Field(..., description="팀원 취향 매칭률 (0~100%)")
    recommended_menu: str = Field(default="", description="이 식당의 추천 대표 메뉴")
    reason: str = Field(..., description="추천 사유")


class RecommendationResponse(BaseModel):
    recommendations: List[RecommendationItem] = Field(..., description="Top N 추천 식당 목록")


class FeedbackRequest(BaseModel):
    user_id: str = Field(..., description="피드백 제출 직원 이름")
    restaurant_name: str = Field(..., description="추천된 식당 이름")
    rating: int = Field(..., ge=1, le=5, description="만족도 별점 (1~5)")
    visited: bool = Field(default=True, description="추천 식당 실제 방문 여부 (👍=True, 👎=False)")
    actual_restaurant_name: Optional[str] = Field(default="", description="실제 방문한 식당 이름 (RLHF 대안)")
    actual_category: Optional[str] = Field(default="한식", description="실제 방문한 식당 카테고리")


class NearbyRestaurant(BaseModel):
    title: str = Field(..., description="식당명")
    category: str = Field(default="기타", description="1차 카테고리 (한식, 중식 등)")
    full_category: str = Field(default="", description="전체 카테고리 경로")
    address: str = Field(default="", description="지번 주소")
    road_address: str = Field(default="", description="도로명 주소")
    telephone: str = Field(default="", description="전화번호")
    naver_map_url: str = Field(default="", description="네이버 지도 링크")
