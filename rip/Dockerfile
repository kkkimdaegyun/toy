# 가벼운 베이스 이미지 (묘지는 무거우면 안 되니까)
FROM python:3.12-slim

# 파이썬이 .pyc 를 남기지 않고, 로그를 바로 흘려보내도록
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 복사
COPY app.py .
COPY static ./static

# SQLite 파일이 살 곳 (볼륨으로 마운트하면 서버가 죽어도 묘비는 남는다)
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# HTTPS 없음. 순수 HTTP. uvicorn 단일 프로세스 = PID 1.
# '최후의 버튼'이 이 프로세스를 죽이면 컨테이너도 함께 잠든다.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
