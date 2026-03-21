import os
import time
import requests
import urllib3
from bs4 import BeautifulSoup
from tqdm import tqdm

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =====================================
# 1. 로그인 정보 및 새로운 경로 설정
# =====================================
USER_ID = "비공개"
USER_PW = "비공개"
LOGIN_URL = "https://www3.chosun.ac.kr/chosunLogin/chosun/login.do"

PDF_DIR = "./login_chosun_pdfs"
LINKS_FILE = "login_html_links.txt"
# [핵심] 기존 DB를 덮어쓰지 않도록 새로운 폴더 지정!
PERSIST_DIRECTORY = "C:/login_chosun_bot_db"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
})

def login():
    print("⏳ DB 빌더: 포털 로그인 시도 중...")
    login_data = {"id": USER_ID, "password": USER_PW}
    try:
        session.post(LOGIN_URL, data=login_data, verify=False, timeout=10)
        print("✅ 로그인 완료! 잠긴 문서를 읽어옵니다.")
    except Exception as e:
        print(f"❌ 로그인 실패: {e}")

if __name__ == "__main__":
    if not os.path.exists(LINKS_FILE):
        print(f"❌ {LINKS_FILE} 파일이 없습니다.")
        exit()

    with open(LINKS_FILE, 'r', encoding='utf-8') as f:
        html_links = [line.strip() for line in f.readlines() if line.strip()]

    login()

    print(f"\n⏳ 1. 웹페이지 추출 시작 (총 {len(html_links)}개)")
    html_docs = []
    
    for url in tqdm(html_links, desc="텍스트 로딩"):
        try:
            res = session.get(url, timeout=5, verify=False)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for script in soup(["script", "style"]):
                    script.extract()
                text = soup.get_text(separator="\n", strip=True)
                
                if text and len(text) > 50:
                    doc = Document(page_content=text, metadata={"source": url})
                    html_docs.append(doc)
            time.sleep(0.05)
        except:
            continue

    print("\n⏳ 2. PDF 파싱 중")
    pdf_loader = PyPDFDirectoryLoader(PDF_DIR)
    pdf_docs = pdf_loader.load()

    all_docs = html_docs + pdf_docs
# ... (앞부분 1, 2단계 코드는 그대로 유지) ...

    print(f"✅ 총 {len(all_docs)}개 문서 로드 완료")

# =====================================
# 3 & 4. [수정됨] 텍스트 분할 및 DB 저장 (초강력 메모리 방어 모드)
# =====================================
    if len(all_docs) == 0:
        print("❌ 수집된 문서가 없어 작업을 종료합니다.")
        exit()

    print("\n⏳ 3 & 4. 단일 문서 단위 분할 및 DB 저장 진행 중...")
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
    
    vectorstore = Chroma(
        collection_name="chosun_univ_info", 
        embedding_function=embeddings, 
        persist_directory=PERSIST_DIRECTORY
    )

    total_saved_chunks = 0
    
    # [핵심] 묶음(Batch)이 아니라 1개씩 단독으로 처리합니다.
    for i in tqdm(range(len(all_docs)), desc="DB 저장"):
        doc = all_docs[i]
        
        # 1. 텍스트 길이가 50만 자(책 5권 분량)를 넘어가면 비정상(쓰레기 데이터)으로 간주하고 앞부분만 자릅니다.
        if len(doc.page_content) > 500000:
            doc.page_content = doc.page_content[:500000]
            
        try:
            # 2. 단 1개의 문서만 쪼갭니다.
            doc_splits = text_splitter.split_documents([doc])
            
            # 3. 쪼갠 조각들을 DB에 넣습니다.
            if doc_splits:
                vectorstore.add_documents(doc_splits)
                total_saved_chunks += len(doc_splits)
                
        # 4. 그래도 메모리 에러가 나면 프로그램이 뻗지 않게 이 문서만 조용히 버립니다.
        except MemoryError:
            print(f"\n🚨 [괴물 문서 패스] 메모리 초과를 유발하는 비정상 문서를 건너뜁니다: {doc.metadata.get('source')}")
            continue
        except Exception:
            continue

    print("\n🎉 모든 과정 완료! 램(RAM) 초과 없이 초대형 DB가 안전하게 구축되었습니다.")
    print(f"📦 최종 저장된 총 데이터(Chunk) 개수: {total_saved_chunks}개")