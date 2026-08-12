#!/usr/bin/env bash
set -e

# ==============================================================================
# AI 점심 추천 마이크로서비스 배포 스크립트 (start.sh)
# 사용 포트: 7120 (사내 점유 포트 7114, 7115, 7118, 7119, 8513, 8550, 8551 제외)
# ==============================================================================

CONTAINER_NAME="lunch-recommender-ai"
IMAGE_NAME="lunch-recommender-ai:latest"
HOST_PORT=7120
CONTAINER_PORT=8000

echo "======================================================="
echo "  [1/4] 기존 컨테이너($CONTAINER_NAME) 중지 및 제거..."
echo "======================================================="
if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo " -> 실행 중이거나 정지된 컨테이너 발견. 중지 및 삭제합니다."
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
else
    echo " -> 기존 컨테이너가 없습니다."
fi

echo ""
echo "======================================================="
echo "  [2/4] Docker 이미지 빌드 ($IMAGE_NAME)..."
echo "======================================================="
docker build -t ${IMAGE_NAME} .

echo ""
echo "======================================================="
echo "  [3/4] 컨테이너 실행 (Port: $HOST_PORT -> $CONTAINER_PORT)..."
echo "======================================================="
docker run -d \
    --name ${CONTAINER_NAME} \
    --restart unless-stopped \
    -p ${HOST_PORT}:${CONTAINER_PORT} \
    ${IMAGE_NAME}

echo ""
echo "======================================================="
echo "  [4/4] 배포 완료 및 상태 확인"
echo "======================================================="
docker ps --filter "name=${CONTAINER_NAME}"

echo ""
echo "-------------------------------------------------------"
echo "✅ AI 점심 추천 서비스가 성공적으로 시작되었습니다!"
echo "📍 직원 취향 설문 페이지: http://localhost:${HOST_PORT}/survey"
echo "📍 Swagger API 문서     : http://localhost:${HOST_PORT}/docs"
echo "📍 API 헬스체크         : http://localhost:${HOST_PORT}/health"
echo "-------------------------------------------------------"
