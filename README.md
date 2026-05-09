# 🎓 조선인사이트 (ChosunInsight)
**조선대학교 AI 통합 행정 안내 서비스**

조선인사이트는 조선대학교 학생 및 교직원을 위한 지능형 학사 챗봇 서비스입니다. 학사 규정, 졸업 요건, 교수진 정보, 학사 일정 및 실시간 식단 정보 등을 자연스러운 대화 형식으로 안내합니다.

---

## 🏗️ 시스템 아키텍처

본 프로젝트는 최신 AI 기술인 **RAG (Retrieval-Augmented Generation)**와 **의도 중심 설계 (Intent-Driven Architecture)**를 결합하여 구축되었습니다.

- **Backend**: FastAPI (Python)
- **Frontend**: Vue 3 (Vite, Tailwind CSS style)
- **AI/LLM**: OpenAI GPT-4o-mini, LangChain, HuggingFace (Embeddings)
- **Database**: ChromaDB (Vector Store)
- **Web Search**: Jina AI Reader API
- **Infra**: Docker, Docker Compose

---

## ✨ 핵심 기능

1.  **지능형 학사 상담**: 졸업 학점, 교양 이수 요건 등 복잡한 학사 지침을 RAG 기술을 통해 정확하게 안내합니다.
2.  **실시간 정보 검색**: 내부 데이터에 없는 최신 뉴스나 공지사항은 Jina AI를 통해 실시간 웹 검색으로 답변합니다.
3.  **전문 도메인 핸들러**: 교수진 조회, 학사 일정, 식단 안내 등 자주 묻는 질문은 구조화된 데이터를 통해 정밀하게 답변합니다.
4.  **세션 메모리**: 대화 도중 파악된 사용자의 학과, 학번 등의 맥락을 기억하여 개인화된 답변을 제공합니다.
5.  **자동 데이터 갱신**: 매일 오전 9시, 크롤러가 최신 학사 정보를 수집하여 벡터 DB를 자동으로 업데이트합니다.

---

## 🚀 시작하기 (Deployment)

본 프로젝트는 Docker Compose를 통해 간편하게 구동할 수 있습니다.

### 1. 환경 변수 설정
프로젝트 루트에 `.env` 파일을 생성하고 필요한 API 키를 입력합니다. (`.env.example` 참고)

```env
OPENAI_API_KEY=your_openai_api_key
JINA_API_KEY=your_jina_api_key
```

### 2. Docker Compose 실행
컨테이너를 빌드하고 백그라운드에서 실행합니다.

```bash
docker compose up --build -d
```

### 3. 서비스 접속
- **Frontend**: `http://localhost:9001` (Nginx 배포)
- **Backend API**: `http://localhost:8001` (FastAPI)

---

## 🛠️ 운영 및 관리

- **데이터 수집 (Updater)**: `chosun_updater` 컨테이너가 매일 최신 데이터를 크롤링하고 DB를 갱신합니다. 갱신이 완료되면 신호(Flag)를 보내 백엔드 서비스가 최신 데이터를 참조할 수 있도록 합니다.
- **의도 분석 (Interpretation)**: 모든 질문은 LLM에 의해 도메인이 분류되며, 분류 결과에 따라 RAG 또는 전용 핸들러가 가동됩니다.
- **로그 확인**:
  ```bash
  docker compose logs -f backend
  ```

---

## 👥 개발 및 기여
본 서비스는 조선대학교 구성원의 편리한 대학 생활을 위해 제작되었습니다. 버그 리포트나 기능 제안은 Issue 탭을 이용해 주세요.
