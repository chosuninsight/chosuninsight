# ChosunInsight

조선대학교 학사 행정 및 대학 생활 안내를 위한 하이브리드 RAG 챗봇입니다. 정형 JSON 데이터, ChromaDB 기반 문서 검색, 공식 웹 검색 보조 경로를 함께 사용해 학사 일정, 공지, 식단, 졸업/교양 요건, 교수/학과 정보, 학과/대학 사이트 링크를 안내합니다.

## 주요 기능

- **Hybrid RAG 라우팅**: 질문 의도를 분석해 정형 데이터 핸들러, 벡터 검색, 공식 웹 검색 중 적절한 경로로 답변합니다.
- **학과/대학 사이트 링크 resolver**: `backend/data/department_site_links.json`를 alias 인덱스로 사용해 `컴공 사이트 알려줘`, `글로벌인문대는?` 같은 명시/후속 질문을 단일 공식 링크로 안내합니다.
- **클릭 가능한 링크 응답**: 백엔드 `sources`를 프론트 링크 버튼으로 렌더링하고, 답변 본문의 URL도 바로 클릭할 수 있습니다.
- **세션 메모리**: 사용자 동의 시 학과, 입학연도, 이수학점 등 대화 맥락을 세션 단위로 유지합니다.
- **데이터 업데이트 파이프라인**: `updater` 컨테이너가 최신 원천 데이터를 갱신하고 완료 플래그 생성 후 백엔드가 기동됩니다.

## 기술 스택

- **Backend**: Python 3.10, FastAPI, Uvicorn
- **Frontend**: Vue 3, Vite, Lucide Icons, Nginx
- **AI/RAG**: OpenAI, LangChain, ChromaDB, Korean sentence embedding model
- **Infra**: Docker, Docker Compose

## 프로젝트 구조

```text
.
├── backend/
│   ├── data/                       # 정형 지식 베이스(JSON)
│   │   └── department_site_links.json
│   ├── tests/                      # API 회귀 테스트 케이스
│   ├── handlers.py                 # 도메인별 답변 핸들러
│   ├── main.py                     # FastAPI 엔트리포인트
│   └── site_link_resolver.py       # 학과/대학 사이트 링크 매칭
├── frontend/                       # Vue 3 프론트엔드
├── chosun_rag_data/                # RAG 인덱싱용 원천 TXT 데이터
├── chroma_db_store/                # ChromaDB 저장소(git ignored)
├── chroma_db_update/               # 갱신용 ChromaDB 저장소(git ignored)
├── docker-compose.yml
├── update_date.py                  # 최신 데이터 갱신
├── rebuild_chroma.py               # ChromaDB 재빌드
└── requirements.txt
```

## 환경 변수

`.env.example`를 복사해 `.env`를 만들고 값을 채웁니다.

```powershell
Copy-Item .env.example .env
```

필수 값:

```env
OPENAI_API_KEY=...
INTERNAL_API_KEY=...
VITE_INTERNAL_API_KEY=...
```

`INTERNAL_API_KEY`와 `VITE_INTERNAL_API_KEY`는 같은 값이어야 합니다. 프론트는 정적 번들에 포함되므로 이 값은 강한 보안 secret이 아니라 내부 API 호출 확인용 게이트로 취급해야 합니다.

선택 값:

```env
JINA_API_KEY=...
MEMORY_ENCRYPTION_KEY=...
DEBUG=false
```

## 실행

Docker Desktop을 실행한 뒤 프로젝트 루트에서:

```powershell
docker compose up -d --build
```

접속:

- Frontend: `http://localhost:9001/chatbot/`
- Backend health: `http://127.0.0.1:8001/`
- RAG health: `http://127.0.0.1:8001/health/rag`
- API docs: `http://127.0.0.1:8001/docs`

로그 확인:

```powershell
docker compose logs -f updater backend
docker compose logs -f frontend
```

백엔드는 `updater`가 `/root/tmp/update_complete.flag`를 만든 뒤 시작합니다. `backend` 로그가 `Waiting for update_complete.flag...`에서 멈추면 `updater` 로그를 먼저 확인하세요.

## 테스트

백엔드 문법/JSON 검증:

```powershell
python -m py_compile backend\site_link_resolver.py backend\handlers.py backend\main.py
python -m json.tool backend\tests\chat_cases.json > $null
python -m json.tool backend\data\department_site_links.json > $null
```

메모리 저장소 테스트:

```powershell
python -m unittest backend.tests.test_memory_store
```

컨테이너가 떠 있고 `.env`의 `INTERNAL_API_KEY`가 현재 셸에 잡혀 있으면 API 회귀 테스트를 실행할 수 있습니다.

```powershell
$env:INTERNAL_API_KEY = "<.env와 같은 값>"
python backend\tests\run_chat_cases.py
```

## 사이트 링크 데이터

학과/대학 공식 사이트는 `backend/data/department_site_links.json`를 기준으로 합니다. 루트의 `대학학부사이트링크.json`는 원본/참고 파일이며, 실제 백엔드 로직은 `backend/data/department_site_links.json`를 읽습니다.

사이트 링크 resolver는 다음을 지원합니다.

- 정식 명칭: `전자공학과 사이트 알려줘`
- 축약 명칭: `컴공 사이트 알려줘`
- 후속 질문: `글로벌인문대는?`
- URL 임의 생성 방지: 확인된 JSON 데이터에 없는 학과는 링크를 만들지 않음

## 운영 메모

- `chosun_rag_data/` 변경은 검색 결과에 직접 영향을 주는 데이터 업데이트입니다. 코드 변경과 분리해 커밋하는 것을 권장합니다.
- `docker_build*.log` 같은 빌드 로그는 커밋하지 않습니다.
- `.env`와 `frontend/.env`는 gitignore 대상입니다.

---

본 프로젝트는 조선대학교 산학 프로젝트를 목적으로 개발되었습니다.
