FROM python:3.10-slim

# ✅ 수정한 1번 섹션
RUN apt-get update && apt-get install -y \
    unzip curl \
    libnss3 libxss1 libasound2 \
    libgbm-dev libgtk-3-0 libatk-bridge2.0-0 \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# 2. 의존성 설치 (타임아웃 방지 옵션 추가)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    # 🔥 핵심: 700MB 대신 200MB 이하의 CPU 전용 torch를 공식 서버에서 직접 설치합니다.
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    # 나머지 패키지는 공식 PyPI 저장소에서 안정적으로 설치합니다.
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 3. 윈도우 스타일 경로 미리 생성 (Update_date.py 호환성)
RUN mkdir -p /root/Desktop /C:/chroma_db_update /app/chroma_db

COPY . .

EXPOSE 8000
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 기본 실행 명령 (docker-compose의 command 설정이 이를 덮어씌웁니다)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
