# 1. Base Image: 경량화 및 보안이 뛰어난 Python 3.11 Slim 이미지 사용
FROM python:3.11-slim

# 2. 메타데이터 및 환경변수 설정
LABEL maintainer="AI Recommendation Architect"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# 3. 작업 디렉토리 생성
WORKDIR /app

# 4. 시스템 패키지 업데이트 및 빌드에 필요한 기본 도구 설치 (캐시 레이어 최적화)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. 요구 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. 소스코드 복사
COPY . .

# 7. 비루트 사용자 생성 및 권한 설정 (보안 강화)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 8. 컨테이너 포트 노출
EXPOSE 8000

# 9. 헬스체크 설정 (컨테이너 내 API 정상 작동 모니터링)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 10. 서비스 시작 명령어 (Uvicorn을 이용한 고성능 비동기 실행)
ENTRYPOINT ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
