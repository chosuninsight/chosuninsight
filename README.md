# 🎓 조선인사이트 (ChosunInsight)
### 조선대학교 AI 통합 행정 안내 서비스

조선인사이트는 조선대학교 구성원을 위한 지능형 학사 안내 챗봇입니다. 학사 규정, 졸업 요건, 교수진 정보, 실시간 식단 등 대학 생활에 필요한 정보를 대화형으로 제공합니다.

---

## 🏗️ 시스템 구성

본 프로젝트는 RAG(Retrieval-Augmented Generation)와 의도 기반 아키텍처를 결합하여 개발되었습니다.

- **Backend**: FastAPI (Python)
- **Frontend**: Vue 3 (Vite)
- **AI/LLM**: OpenAI GPT-4o-mini, LangChain
- **Database**: ChromaDB (Vector Store)
- **Web Search**: Jina AI Reader API
- **Infra**: Docker, Docker Compose

---

## ✨ 주요 기능

1. **학사 상담**: 졸업 학점, 교양 이수 요건 등 복잡한 학사 지침을 정확하게 안내합니다.
2. **실시간 검색**: 최신 뉴스나 공지사항은 Jina AI 웹 검색을 통해 답변합니다.
3. **특화 도메인**: 교수진 조회, 학사 일정, 식단 등 자주 묻는 질문은 정형 데이터를 활용해 정확도를 높였습니다.
4. **개인화 맥락 유지**: 대화 중 파악된 학과나 학번 정보를 기억해 상황에 맞는 답변을 제공합니다.
5. **데이터 자동 업데이트**: 매일 오전 최신 학사 정보를 수집하여 벡터 DB를 동기화합니다.

---

## 🚀 시작하기

### 1. 환경 변수 설정
루트 디렉토리에 `.env` 파일을 생성하고 API 키를 입력합니다. (`.env.example` 참고)

```env
OPENAI_API_KEY=your_openai_api_key
JINA_API_KEY=your_jina_api_key
MEMORY_PROVIDER=mem0
# MEMORY_PROVIDER=local
# MEMORY_STORE_PATH=backend/data/local_memory_store.json
# MEMORY_AGENT_ID=chosuninsight
```

### 2. 실행
Docker Compose를 이용해 전체 서비스를 구동합니다.

```bash
docker compose up --build -d
```

### 3. 접속 정보
- **Frontend**: `http://localhost:9001`
- **Backend API**: `http://localhost:8001`

---

## 🛠️ 운영 및 관리

- **데이터 동기화**: `chosun_updater`가 매일 최신 데이터를 크롤링하고 벡터 DB를 갱신합니다.
- **질문 의도 분석**: 모든 질문은 LLM이 도메인을 분류하며, 결과에 따라 RAG 또는 전용 핸들러를 호출합니다.
- **로그 확인**:
  ```bash
  docker compose logs -f backend
  ```

---

## 👥 기여하기
버그 리포트나 기능 제안은 Issue 탭을 통해 남겨주세요.
