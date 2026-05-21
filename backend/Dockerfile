FROM python:3.10-slim

RUN apt-get -o Acquire::Retries=3 update && \
    apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
    curl \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. 의존성 설치 (타임아웃 방지 옵션 추가)
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    # 핵심: 700MB 대신 200MB 이하의 CPU 전용 torch를 공식 서버에서 직접 설치합니다.
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    # 나머지 패키지는 공식 PyPI 저장소에서 안정적으로 설치합니다.
    pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# 3. 필요한 디렉토리 생성
RUN mkdir -p /app/chroma_db /root/chroma_db_update

COPY . .

EXPOSE 8000
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# 기본 실행 명령 (docker-compose의 command 설정이 이를 덮어씌웁니다)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
