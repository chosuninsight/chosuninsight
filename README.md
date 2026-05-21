# ChosunInsight

조선대학교 학사 행정, 대학 생활, 공지, 학과 정보를 안내하는 하이브리드 RAG 챗봇입니다.  
정형 JSON 데이터, ChromaDB 문서 검색, 최신 수집 데이터, 공식 웹 검색 보조 경로를 함께 사용해 질문 유형별로 더 안정적인 답변을 제공합니다.

## 주요 기능

- **하이브리드 라우팅**
  - 질문 의도를 분석해 정형 핸들러, 벡터 검색, 공식 웹 검색 중 적절한 경로로 답변합니다.
  - 학사일정, 졸업요건, 교양 이수체계, 교수진, 학생지원 포털, 학과/대학 사이트 링크는 구조화 답변을 우선 사용합니다.

- **조선대학교 특화 정형 답변**
  - 2026 학사일정
  - 졸업이수학점/교양 이수학점
  - 교수진 연구실/전화번호
  - THE조아, 수강신청 시스템 등 학생지원 포털 경로
  - 학과/단과대 공식 사이트 링크

- **사이트 링크 resolver**
  - `컴공 사이트 알려줘`, `글로벌인문대는?` 같은 축약/후속 질문을 공식 링크로 안내합니다.
  - 확인된 데이터에 없는 학과명은 URL을 임의 생성하지 않습니다.

- **세션 메모리**
  - 사용자가 허용한 경우에만 학과, 학번, 이수학점 등 개인 맥락을 세션 단위로 기억합니다.
  - 프론트의 메모리 동의 상태가 `granted`일 때만 백엔드에 `memory_enabled: true`를 보냅니다.

- **프론트 UI**
  - Vue 3 기반 챗봇 UI
  - 채팅 히스토리 사이드바
  - 메모리 관리 패널
  - 클릭 가능한 URL/출처 버튼
  - 키보드 포커스, ARIA 라벨, reduced motion 등 기본 접근성 보강

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn, Pydantic |
| Frontend | Vue 3, Vite, Lucide Icons, Nginx |
| RAG/Search | LangChain, ChromaDB, sentence-transformers, BM25, OpenAI/Gemini, Jina |
| Infra | Docker, Docker Compose |

## 프로젝트 구조

```text
.
├── backend/
│   ├── data/
│   │   ├── academic_policies.json
│   │   ├── academic_reference_answers.json
│   │   ├── department_site_links.json
│   │   ├── faculty_profiles.json
│   │   └── local_memory_store.json
│   ├── tests/
│   │   ├── chat_cases.json
│   │   ├── deep_chat_cases.json
│   │   ├── run_chat_cases.py
│   │   ├── run_deep_chat_cases.py
│   │   └── test_memory_store.py
│   ├── config.py
│   ├── handlers.py
│   ├── main.py
│   ├── memory.py
│   ├── search_logic.py
│   └── site_link_resolver.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── composables/
│   │   ├── data/
│   │   ├── services/
│   │   └── views/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
├── chosun_rag_data/          # RAG 검색용 최신 수집 TXT 데이터
├── chroma_db_store/          # 원본 ChromaDB 저장소
├── chroma_db_update/         # 최신 데이터 ChromaDB 저장소
├── docker-compose.yml
├── rag_pipeline.py
├── rebuild_chroma.py
├── update_date.py
└── requirements.txt
```

## 환경 변수

`.env.example`을 복사해서 `.env`를 만듭니다.

```powershell
Copy-Item .env.example .env
```

필수 설정:

```env
INTERNAL_API_KEY=
VITE_INTERNAL_API_KEY=
OPENAI_API_KEY=
```

`INTERNAL_API_KEY`와 `VITE_INTERNAL_API_KEY`는 같은 값으로 맞춥니다.  
프론트 번들에 포함되는 값이므로 강한 비밀키라기보다 내부 API 호출 게이트로 사용됩니다.

LLM 제공자는 설정에 따라 OpenAI 또는 Gemini를 사용할 수 있습니다.

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...

# 또는
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash-lite
```

선택 설정:

```env
JINA_API_KEY=
WEB_SEARCH_ENABLED=true
MEMORY_PROVIDER=mem0
MEMORY_ENCRYPTION_KEY=
DEBUG=false
```

## Docker 실행

Docker Desktop을 켠 뒤 프로젝트 루트에서 실행합니다.

```powershell
docker compose up -d --build
```

접속 주소:

```text
Frontend: http://localhost:9001/chatbot/
Backend health: http://127.0.0.1:8001/
RAG health: http://127.0.0.1:8001/health/rag
API docs: http://127.0.0.1:8001/docs
```

로그 확인:

```powershell
docker compose logs -f updater backend
docker compose logs -f frontend
```

백엔드는 `updater` 컨테이너가 최신 데이터를 갱신하고 `/root/tmp/update_complete.flag`를 만든 뒤 시작합니다.  
백엔드 로그가 `Waiting for update_complete.flag...`에서 멈춰 있으면 먼저 `updater` 로그를 확인하세요.

코드만 바꾼 뒤 백엔드 재시작:

```powershell
docker compose restart backend
```

프론트 빌드 설정이나 env build arg가 바뀐 경우:

```powershell
docker compose up -d --build frontend
```

## 로컬 프론트 개발

```powershell
cd frontend
npm install
npm run dev
```

Vite 개발 서버는 기본적으로 `5173` 포트를 사용합니다.  
Docker 배포에서는 Nginx가 `/chatbot/` 경로로 정적 파일을 제공합니다.

프론트 빌드 검증:

```powershell
cd frontend
npm run build
```

PowerShell 실행 정책 때문에 `npm`이 막히면 `npm.cmd`를 사용합니다.

```powershell
npm.cmd run build
```

## 테스트

백엔드 문법/JSON 검증:

```powershell
python -m py_compile backend\site_link_resolver.py backend\handlers.py backend\main.py
python -m json.tool backend\tests\chat_cases.json > $null
python -m json.tool backend\tests\deep_chat_cases.json > $null
python -m json.tool backend\data\department_site_links.json > $null
```

메모리 저장소 단위 테스트:

```powershell
python -m unittest backend.tests.test_memory_store
```

API 회귀 테스트:

```powershell
$env:INTERNAL_API_KEY = ((Get-Content .\.env | Where-Object { $_ -match '^INTERNAL_API_KEY=' }) -replace '^INTERNAL_API_KEY=', '')
python backend\tests\run_chat_cases.py
python backend\tests\run_deep_chat_cases.py
```

`run_chat_cases.py`는 기본 회귀 케이스를 검증합니다.  
`run_deep_chat_cases.py`는 환각 방지, follow-up 맥락, 부분 문자열 오탐, 프롬프트 인젝션성 질문을 더 강하게 검증합니다.

## 주요 API

### `POST /chat`

요청 예시:

```json
{
  "question": "컴퓨터공학과 사이트 알려줘",
  "history": [],
  "session_id": "demo-session",
  "memory_enabled": false,
  "debug": true
}
```

응답 예시:

```json
{
  "success": true,
  "answer": "확인된 조선대학교 학과/대학 사이트 링크입니다.\n- AI·SW학부(컴퓨터공학전공): https://ce.chosun.ac.kr/ce/index.do",
  "sources": ["https://ce.chosun.ac.kr/ce/index.do"],
  "suggestions": [],
  "debug": {
    "answer_mode": "department_site_link"
  }
}
```

### 메모리 API

```text
GET    /memory/{session_id}
DELETE /memory/{session_id}
DELETE /memory/{session_id}/items/{memory_id}
```

메모리 기능은 서버 전역 설정 `CHAT_MEMORY_ENABLED`와 요청별 `memory_enabled`가 모두 true일 때만 동작합니다.

## 답변 모드

테스트와 디버그에서 자주 보는 `answer_mode`는 다음과 같습니다.

| 모드 | 의미 |
| --- | --- |
| `department_site_link` | 학과/대학 공식 사이트 링크 |
| `student_support_portal` | THE조아, 수강신청 등 포털 경로 |
| `academic_calendar_2026` | 2026 학사일정 |
| `graduation_policy` | 졸업요건/이수학점 |
| `general_education_YYYY` | 입학연도별 교양 이수체계 |
| `faculty_profile` | 교수진/연구실/전화번호 |
| `clarifying_question` | 학과/학번/일정명 등 추가 정보 요청 |
| `official_fallback` | 최신성이 높아 공식 공지 확인 필요 |
| `memory_recall` | 저장된 사용자 맥락 조회 |
| `rag` | ChromaDB/RAG 검색 기반 답변 |

## 데이터 관리

### 정형 데이터

백엔드 구조화 답변은 주로 `backend/data/`의 JSON 파일을 사용합니다.

- `academic_policies.json`: 졸업요건/이수학점
- `academic_reference_answers.json`: 학사일정, 교양 이수체계, 학사 행정 참고 답변
- `department_site_links.json`: 학과/대학 사이트 링크
- `faculty_profiles.json`: 교수진, 연구실, 전화번호
- `web_knowledge_store.json`: 공식 fallback 지식

### RAG 데이터

`chosun_rag_data/`는 최신 공지, 비교과, 식단, 장학금 등 검색용 TXT 데이터입니다.  
이 폴더 변경은 챗봇 검색 결과에 직접 영향을 주므로 코드 변경과 분리해 커밋하는 것을 권장합니다.

### ChromaDB

- `chroma_db_store/`: 기본 검색 DB
- `chroma_db_update/`: 최신 수집 데이터 DB

필요 시 재빌드:

```powershell
python rebuild_chroma.py
```

## UI/UX 메모

프론트는 다음 흐름을 기준으로 동작합니다.

- 첫 방문 시 메모리 동의 배너 표시
- `허용하기`: `localStorage.chosun_memory_consent = granted` 저장, 메모리 활성화
- `나중에`: 저장하지 않고 배너만 닫음, 다음 방문 시 다시 표시
- 사이드바 메모리 패널에서 기능 켜기/끄기 및 저장 항목 삭제 가능

접근성 보강 사항:

- 아이콘 버튼 `aria-label`
- 채팅 로그 `aria-live`
- 키보드 포커스 스타일
- 클릭 가능한 히스토리 항목을 실제 버튼으로 구성
- `prefers-reduced-motion` 대응
- 모바일 `100dvh`, safe-area 대응

## 운영/커밋 주의사항

- `.env`, `frontend/.env`, `node_modules/`, `frontend/dist/`, 빌드 로그는 커밋하지 않습니다.
- `chosun_rag_data/조선대학교_식단.txt`처럼 수집시각만 바뀐 데이터는 UI/코드 커밋에 섞지 않는 것이 좋습니다.
- Windows에서 `LF will be replaced by CRLF` 경고는 줄바꿈 변환 경고입니다. 실제 diff를 확인한 뒤 커밋하세요.
- 프론트 보안 경고는 `npm audit`으로 별도 확인합니다.

## 자주 쓰는 명령

```powershell
# 전체 컨테이너 시작
docker compose up -d --build

# 백엔드만 재시작
docker compose restart backend

# 로그 확인
docker compose logs -f backend

# 기본 QA
python backend\tests\run_chat_cases.py

# 심화 QA
python backend\tests\run_deep_chat_cases.py

# 프론트 빌드
cd frontend
npm.cmd run build
```

---

본 프로젝트는 조선대학교 산학 프로젝트를 목적으로 개발되었습니다.
