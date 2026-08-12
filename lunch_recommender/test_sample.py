import json
from schemas import RecommendationRequest
from recommender import LunchRecommender

sample_payload = {
    "users": [
        {
            "user_id": "u1",
            "preferences": {"spicy_level": 4, "soup": True, "meat": True},
            "allergies": ["갑각류"],
            "dislikes": ["오이", "마라"]
        },
        {
            "user_id": "u2",
            "preferences": {"spicy_level": 3, "soup": True, "meat": False},
            "allergies": [],
            "dislikes": []
        }
    ],
    "restaurants": [
        {
            "rest_id": "r1",
            "name": "김치찌개 맛집",
            "attributes": {"spicy_level": 4, "soup": True, "meat": True, "ingredients": ["돼지고기", "김치"]},
            "mab_stats": {"clicks": 10, "avg_reward": 4.2}
        },
        {
            "rest_id": "r2",
            "name": "마라탕 식당",
            "attributes": {"spicy_level": 5, "soup": True, "meat": True, "ingredients": ["마라", "소고기", "청경채"]},
            "mab_stats": {"clicks": 15, "avg_reward": 4.5}
        },
        {
            "rest_id": "r3",
            "name": "신규 샐러드 맛집",
            "attributes": {"spicy_level": 1, "soup": False, "meat": False, "ingredients": ["양상추", "토마토"]},
            "mab_stats": {"clicks": 0, "avg_reward": 0.0}
        }
    ]
}

def test_pipeline():
    req = RecommendationRequest(**sample_payload)
    recommender = LunchRecommender()
    results = recommender.recommend(req.users, req.restaurants, top_k=3)
    
    print("=== Recommendation Pipeline Test ===")
    for item in results:
        print(f"- [{item.rest_id}] {item.name}: score={item.final_score} | reason={item.reason}")
    assert len(results) == 2, "마라탕 식당(r2)은 u1의 기피 음식('마라')으로 인해 Least Misery에 의해 제외되어야 합니다."
    assert results[0].rest_id == "r1"
    print("Test passed successfully!")

if __name__ == "__main__":
    test_pipeline()
