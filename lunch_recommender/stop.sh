#!/usr/bin/env bash
set -e

CONTAINER_NAME="lunch-recommender-ai"

echo "======================================================="
echo "  컨테이너($CONTAINER_NAME) 중지 및 삭제 중..."
echo "======================================================="

if [ "$(docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
    echo "✅ 컨테이너($CONTAINER_NAME)가 성공적으로 삭제되었습니다."
else
    echo "ℹ️ 실행 중이거나 존재하는 컨테이너($CONTAINER_NAME)가 없습니다."
fi
