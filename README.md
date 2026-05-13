# ChosunInsight: Hybrid-RAG University Assistant

조선대학교 학사 행정 및 대학 생활 안내를 위한 하이브리드 RAG(Retrieval-Augmented Generation) 시스템입니다. 학사 규정 기반의 답변 정확도와 웹 검색의 실시간성을 결합한 아키텍처로 설계되었습니다.

## Key Features

- **Hybrid Search Strategy**: 정형 데이터(JSON) 핸들러와 비형태 데이터(Vector DB) 검색을 병렬 수행하여 답변 신뢰도를 극대화합니다.
- **Intent-based Routing**: LLM을 통해 사용자 질문 의도(학사, 식단, 웹 검색 등)를 분석하고 최적의 데이터 소스로 라우팅합니다.
- **Privacy-First Memory**: 사용자 동의 기반의 세션 메모리를 활용하여 학과, 학번 등 개인화된 맥락을 안전하게 유지합니다. (ChatGPT 스타일의 동의 워크플로우 적용)
- **Automated Data Pipeline**: 크롤러와 연동되어 매일 최신 학사 공지 및 식단 정보를 벡터 DB에 자동 동기화합니다.

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn
- **Frontend**: Vue 3, Vite, Tailwind CSS, Lucide Icons
- **AI/ML**: OpenAI GPT-4o-mini, LangChain, ChromaDB
- **Infra**: Docker, Docker Compose, Nginx

## Project Structure

```text
.
├── backend/            # FastAPI 서버 및 RAG 로직
│   ├── data/           # 정형 지식 베이스 (JSON)
│   └── tests/          # 테스트 케이스 및 검증 스크립트
├── frontend/           # Vue 3 웹 애플리케이션
├── chosun_rag_data/    # RAG 인덱싱용 원천 데이터 (TXT)
├── chroma_db_store/    # 벡터 데이터베이스 저장소 (Git ignored)
├── docker-compose.yml  # 컨테이너 오케스트레이션
└── requirements.txt    # 백엔드 의존성 관리
```

## Setup & Deployment

### Prerequisites
- Docker & Docker Compose
- OpenAI API Key
- Jina AI API Key (Web search 용 옵션)

### Installation
1. 프로젝트를 클론하고 환경 변수를 설정합니다.
```bash
git clone https://github.com/chosuninsight/chosuninsight.git
cd chosuninsight
cp .env.example .env
# .env 파일에 OpenAI 및 Jina API 키 입력
```

2. Docker Compose를 사용하여 서비스를 구동합니다.
```bash
docker compose up -d --build
```

### Access Points
- **Web Frontend**: `http://localhost:9001`
- **Backend API Docs**: `http://localhost:8001/docs`

## Operations

- **Data Sync**: 컨테이너 가동 시 `chosun_updater`가 자동으로 최신 데이터를 수집하고 벡터 DB를 리빌드합니다.
- **Monitoring**: 백엔드 로그를 통해 쿼리 처리 과정과 RAG 히트율을 확인할 수 있습니다.
  ```bash
  docker compose logs -f backend
  ```

---
본 프로젝트는 조선대학교 산학 프로젝트를 목적으로 개발되었습니다.
