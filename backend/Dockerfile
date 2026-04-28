FROM python:3.10-slim

# ✅ 수정한 1번 섹션
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl \
    libnss3 libxss1 libasound2 \
    libgbm-dev libgtk-3-0 libatk-bridge2.0-0 \
    && mkdir -p /etc/apt/keyrings \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# 2. 의존성 설치 (타임아웃 방지 옵션 추가)
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 3. 윈도우 스타일 경로 미리 생성 (Update_date.py 호환성)
RUN mkdir -p /root/Desktop /C:/chroma_db_update /app/chroma_db

COPY . .

EXPOSE 8000
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 기본 실행 명령 (docker-compose의 command 설정이 이를 덮어씌웁니다)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
