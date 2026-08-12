import json
import os
import re
import time
import logging
import urllib.request
import urllib.parse
from typing import List, Dict, Optional

logger = logging.getLogger("NaverAPI")

# 디폴트 기준 위치: 상암동 누리꿈스퀘어
DEFAULT_LANDMARK = "누리꿈스퀘어"
DEFAULT_LOCATION = "상암동"

# 카테고리별 검색 키워드 (네이버 지역 검색 API display 최대 5건이므로 카테고리별 병렬 검색)
SEARCH_CATEGORIES = [
    "맛집", "한식", "중식", "일식", "양식", "분식",
    "치킨", "피자", "국밥", "찌개", "고기", "해산물", "면"
]


class NaverLocalSearch:
    """
    네이버 지역 검색 API 클라이언트
    - 카테고리별 검색으로 누리꿈스퀘어 근방 식당 풀을 수집
    - 1시간 캐시로 API 호출 최소화
    """

    BASE_URL = "https://openapi.naver.com/v1/search/local.json"
    CACHE_TTL = 3600  # 1시간

    def __init__(self):
        self.client_id = os.environ.get("NAVER_CLIENT_ID", "")
        self.client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")
        self._cache: Dict[str, tuple] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _call_api(self, query: str, display: int = 5, sort: str = "comment") -> List[Dict]:
        """네이버 지역 검색 API 단건 호출"""
        params = urllib.parse.urlencode({
            "query": query,
            "display": min(display, 5),
            "sort": sort
        })
        url = f"{self.BASE_URL}?{params}"
        req = urllib.request.Request(url)
        req.add_header("X-Naver-Client-Id", self.client_id)
        req.add_header("X-Naver-Client-Secret", self.client_secret)

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("items", [])
        except Exception as e:
            logger.error(f"네이버 API 호출 실패 (query={query}): {e}")
            return []

    @staticmethod
    def _clean_html(text: str) -> str:
        """네이버 API 응답의 <b> 등 HTML 태그 제거"""
        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _extract_main_category(category_str: str) -> str:
        """'한식>백반>국밥' → '한식' 1차 카테고리 추출"""
        if not category_str:
            return "기타"
        main = category_str.split(">")[0].strip()
        # 음식점 카테고리 정규화
        category_map = {
            "음식점": "기타", "카페,디저트": "카페", "술집": "기타",
        }
        return category_map.get(main, main)

    def search_nearby_restaurants(
        self,
        location: str = DEFAULT_LOCATION,
        landmark: str = DEFAULT_LANDMARK,
        categories: Optional[List[str]] = None,
        exclude_categories: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        누리꿈스퀘어 근처 식당을 카테고리별로 검색 후 중복 제거하여 반환.

        Returns:
            [{"title", "category", "full_category", "address", "road_address",
              "telephone", "link", "naver_map_url"}, ...]
        """
        if not self.is_configured:
            logger.warning("네이버 API 키 미설정 — 기본 식당 데이터로 폴백")
            return []

        search_cats = categories if categories else SEARCH_CATEGORIES
        if exclude_categories:
            search_cats = [c for c in search_cats if c not in exclude_categories]

        # 캐시 확인
        cache_key = f"{location}_{landmark}_{'|'.join(sorted(search_cats))}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if time.time() - cached_time < self.CACHE_TTL:
                logger.info(f"캐시 적중: {len(cached_data)}개 식당")
                return cached_data

        # 카테고리별 검색 및 합산
        all_results = []
        seen_titles = set()

        for cat in search_cats:
            query = f"{location} {landmark} {cat}"
            items = self._call_api(query, display=5, sort="comment")

            for item in items:
                clean_title = self._clean_html(item.get("title", ""))
                if not clean_title or clean_title in seen_titles:
                    continue

                seen_titles.add(clean_title)
                main_cat = self._extract_main_category(item.get("category", ""))
                naver_map_url = f"https://map.naver.com/v5/search/{urllib.parse.quote(clean_title)}"

                all_results.append({
                    "title": clean_title,
                    "category": main_cat,
                    "full_category": item.get("category", ""),
                    "address": item.get("address", ""),
                    "road_address": item.get("roadAddress", ""),
                    "telephone": item.get("telephone", ""),
                    "link": item.get("link", ""),
                    "naver_map_url": naver_map_url,
                })

        # 캐시 저장
        self._cache[cache_key] = (time.time(), all_results)
        logger.info(f"네이버 API: {len(all_results)}개 식당 수집 완료 ({location} {landmark})")
        return all_results

    def search_keyword(
        self,
        keyword: str,
        location: str = DEFAULT_LOCATION,
        landmark: str = DEFAULT_LANDMARK
    ) -> List[Dict]:
        """특정 키워드(대안 방문 식당 등)로 누리꿈스퀘어 근방 식당 검색"""
        if not self.is_configured:
            return []
        query = f"{location} {landmark} {keyword}".strip()
        items = self._call_api(query, display=5, sort="comment")
        results = []
        for item in items:
            clean_title = self._clean_html(item.get("title", ""))
            if not clean_title:
                continue
            main_cat = self._extract_main_category(item.get("category", ""))
            naver_map_url = f"https://map.naver.com/v5/search/{urllib.parse.quote(clean_title)}"
            results.append({
                "title": clean_title,
                "category": main_cat,
                "full_category": item.get("category", ""),
                "address": item.get("address", "") or item.get("roadAddress", ""),
                "road_address": item.get("roadAddress", ""),
                "telephone": item.get("telephone", ""),
                "naver_map_url": naver_map_url
            })
        return results
