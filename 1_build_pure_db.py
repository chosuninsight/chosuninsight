import os
from tqdm import tqdm

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =====================================
# 1. 경로 설정 (순도 100% 새 DB)
# =====================================
TXT_DIR = "./pure_txt_data" 
PERSIST_DIRECTORY = "C:/pure_chosun_bot_db" # 완전히 새로운 경로

if __name__ == "__main__":
    if not os.path.exists(TXT_DIR):
        print(f"❌ '{TXT_DIR}' 폴더가 없습니다. 텍스트 파일을 넣어주세요.")
        exit()

# =====================================
# 2. 정방향 스마트 파싱 (URL -> 내용)
# =====================================
    print(f"\n⏳ 1. 수동 텍스트 파일 분석 중...")
    txt_docs = []
    
    for filename in os.listdir(TXT_DIR):
        if filename.endswith(".txt"):
            filepath = os.path.join(TXT_DIR, filename)
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                    
                current_url = f"수동작성문서({filename})" 
                current_content = []
                
                for line in lines:
                    stripped_line = line.strip()
                    upper_line = stripped_line.upper()
                    
                    if upper_line.startswith("URL:") or stripped_line.startswith("http://") or stripped_line.startswith("https://"):
                        if current_content:
                            text = "\n".join(current_content).strip()
                            if text:
                                txt_docs.append(Document(page_content=text, metadata={"source": current_url}))
                            current_content = []
                        
                        if upper_line.startswith("URL:"):
                            current_url = stripped_line[4:].strip()
                        else:
                            current_url = stripped_line
                    else:
                        if stripped_line: 
                            current_content.append(stripped_line)
                        
                if current_content:
                    text = "\n".join(current_content).strip()
                    if text:
                        txt_docs.append(Document(page_content=text, metadata={"source": current_url}))
                        
            except Exception as e:
                print(f"⚠️ {filename} 파싱 실패: {e}")

    print(f"✅ 총 {len(txt_docs)}개의 정보 덩어리 분리 완료!")
    if not txt_docs: exit()

# =====================================
# 3. 텍스트 분할 & 새 DB 생성
# =====================================
    print("\n⏳ 2. 텍스트 분할 진행 중...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = text_splitter.split_documents(txt_docs)

    print(f"\n⏳ 3. 순도 100% 새 DB({PERSIST_DIRECTORY})를 생성합니다...")
    embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
    vectorstore = Chroma(
        collection_name="chosun_univ_info", 
        embedding_function=embeddings, 
        persist_directory=PERSIST_DIRECTORY
    )
    vectorstore.add_documents(splits)

    print("\n🎉 순도 100% DB 구축 완료!")
    print(f"📦 저장된 데이터 개수: {vectorstore._collection.count()}개")
