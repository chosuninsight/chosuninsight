import os
import time
import shutil
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import urllib3
import schedule

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =====================================================================
# 📁 전역 경로 설정 (데이터 저장 폴더 및 갱신 전용 DB 폴더)
# =====================================================================
# 1. 텍스트 파일이 모일 바탕화면 폴더
DESKTOP_PATH = os.path.join(os.path.expanduser("~"), "Desktop")
DATA_SAVE_DIR = os.path.join(DESKTOP_PATH, "chosun_rag_data")

# 2. 갱신 데이터 '전용' 크로마 DB 경로 (기존 DB와 완전히 분리됨)
UPDATE_DB_DIR = r"C:\chroma_db_update"
UPDATE_COLLECTION_NAME = "chosun_daily_update"

if not os.path.exists(DATA_SAVE_DIR):
    os.makedirs(DATA_SAVE_DIR)

# =====================================================================
# 1~6. 웹 크롤링 수집 함수들 (변경 없음, DATA_SAVE_DIR에 저장)
# =====================================================================
def crawl_extracurricular_data():
    url = "https://thechoa.chosun.ac.kr/ncrProgramAppl/a/m/getProgramApplList.do"
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    collected_data = []

    try:
        print(f"▶ [1/6] 비교과 사이트 수집 중...")
        driver.get(url)
        time.sleep(5) 
        
        for page in range(1, 4):
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for card in soup.select('div.program_cardtype'):
                status = card.select_one('strong.status_label').text.strip() if card.select_one('strong.status_label') else "상태없음"
                title = card.select_one('dt a').text.strip() if card.select_one('dt a') else "제목없음"
                
                apply_period, op_period, target = "", "", ""
                for dd in card.select('dl dd'):
                    if dd.find('strong', class_='font_orange'): apply_period = dd.text.replace('신청기간', '').strip()
                    elif dd.find('strong', class_='font_green'): op_period = dd.text.replace('운영기간', '').strip()
                    elif dd.find('strong', class_='font_purple'): target = dd.text.replace('참여대상', '').strip()
                
                if "2026" not in apply_period: continue
                    
                mileage = card.select_one('strong.mileage_point span').text.strip() if card.select_one('strong.mileage_point span') else "0점"
                tags_str = " ".join([t.text.strip() for t in card.select('ul.capa_list li')])
                
                collected_data.append(f"상태: {status}\n제목: {title}\n신청기간: {apply_period}\n운영기간: {op_period}\n참여대상: {target}\n마일리지: {mileage}\n역량태그: {tags_str}")
            
            if page < 3: 
                driver.find_element(By.LINK_TEXT, str(page + 1)).click()
                time.sleep(3) 
    except Exception as e: print(f"❌ 비교과 에러: {e}")
    finally:
        driver.quit()
        if collected_data:
            with open(os.path.join(DATA_SAVE_DIR, "비교과데이터_최신.txt"), "w", encoding="utf-8") as f:
                f.write("\n---\n".join(collected_data))
            print(f"  ✅ 비교과 수집 완료 ({len(collected_data)}건)")

def crawl_academic_notices():
    base_url = "https://www4.chosun.ac.kr/acguide/9326/subview.do"
    headers = {"User-Agent": "Mozilla/5.0"}
    collected_data = []

    print(f"▶ [2/6] 학사공지 수집 중...")
    try:
        for page in range(1, 4):
            response = requests.get(f"{base_url}?page={page}", headers=headers, verify=False, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for row in soup.select("table tbody tr"):
                date_tag = row.select_one("td.td-date")
                if not date_tag or not date_tag.text.strip().startswith("2026"): continue

                title_tag = row.select_one("td.td-subject a") or row.select_one("a")
                if not title_tag or 'href' not in title_tag.attrs: continue
                title = title_tag.text.strip()
                link = title_tag['href']
                link = "https://www4.chosun.ac.kr" + link if link.startswith("/") else base_url + link if link.startswith("?") else link
                    
                detail_resp = requests.get(link, headers=headers, verify=False, timeout=10)
                detail_resp.encoding = 'utf-8'
                content_tag = BeautifulSoup(detail_resp.text, 'html.parser').select_one("div.board-view-content, div.b-content-box, div.view-con, div.article")
                content_text = content_tag.get_text(separator='\n', strip=True) if content_tag else "본문 없음"

                collected_data.append(f"분류: 학사공지\n제목: {title}\n날짜: {date_tag.text.strip()}\n내용:\n{content_text}")
                time.sleep(0.5)
    except Exception as e: print(f"❌ 학사공지 에러: {e}")
    finally:
        if collected_data:
            with open(os.path.join(DATA_SAVE_DIR, "학사공지_2026.txt"), "w", encoding="utf-8") as f:
                f.write("\n---\n".join(collected_data))
            print(f"  ✅ 학사공지 수집 완료 ({len(collected_data)}건)")

def crawl_general_notices():
    base_url = "https://www3.chosun.ac.kr/chosun/217/subview.do"
    headers = {"User-Agent": "Mozilla/5.0"}
    collected_data = []

    print(f"▶ [3/6] 교내일반공지 수집 중...")
    try:
        for page in range(1, 4):
            response = requests.get(f"{base_url}?page={page}", headers=headers, verify=False, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for row in soup.select("table tbody tr"):
                date_tag = row.select_one("td.date")
                if not date_tag or not date_tag.text.strip().startswith("2026"): continue

                title_tag = row.select_one("td.subject a")
                if not title_tag or 'href' not in title_tag.attrs: continue
                title = title_tag.text.strip()
                link = title_tag['href']
                link = "https://www3.chosun.ac.kr" + link if link.startswith("/") else base_url + link if link.startswith("?") else link
                    
                detail_resp = requests.get(link, headers=headers, verify=False, timeout=10)
                detail_resp.encoding = 'utf-8'
                content_tag = BeautifulSoup(detail_resp.text, 'html.parser').select_one("div.user-article")
                content_text = content_tag.get_text(separator='\n', strip=True) if content_tag else "본문 없음"

                collected_data.append(f"분류: 교내일반공지\n제목: {title}\n날짜: {date_tag.text.strip()}\n내용:\n{content_text}")
                time.sleep(0.5)
    except Exception as e: print(f"❌ 교내일반공지 에러: {e}")
    finally:
        if collected_data:
            with open(os.path.join(DATA_SAVE_DIR, "교내일반공지_2026.txt"), "w", encoding="utf-8") as f:
                f.write("\n---\n".join(collected_data))
            print(f"  ✅ 교내일반공지 수집 완료 ({len(collected_data)}건)")

def crawl_external_notices():
    base_url = "https://www3.chosun.ac.kr/chosun/2500/subview.do"
    headers = {"User-Agent": "Mozilla/5.0"}
    collected_data = []

    print(f"▶ [4/6] 외부기관공고 수집 중...")
    try:
        for page in range(1, 4):
            response = requests.get(f"{base_url}?page={page}", headers=headers, verify=False, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for row in soup.select("table tbody tr"):
                date_tag = row.select_one("td.date")
                if not date_tag or not date_tag.text.strip().startswith("2026"): continue

                title_tag = row.select_one("td.subject a")
                if not title_tag or 'href' not in title_tag.attrs: continue
                title = title_tag.text.strip()
                link = title_tag['href']
                link = "https://www3.chosun.ac.kr" + link if link.startswith("/") else base_url + link if link.startswith("?") else link
                    
                detail_resp = requests.get(link, headers=headers, verify=False, timeout=10)
                detail_resp.encoding = 'utf-8'
                content_tag = BeautifulSoup(detail_resp.text, 'html.parser').select_one("div.user-article")
                content_text = content_tag.get_text(separator='\n', strip=True) if content_tag else "본문 없음"

                collected_data.append(f"분류: 외부기관공고\n제목: {title}\n날짜: {date_tag.text.strip()}\n내용:\n{content_text}")
                time.sleep(0.5)
    except Exception as e: print(f"❌ 외부기관공고 에러: {e}")
    finally:
        if collected_data:
            with open(os.path.join(DATA_SAVE_DIR, "외부기관공고_2026.txt"), "w", encoding="utf-8") as f:
                f.write("\n---\n".join(collected_data))
            print(f"  ✅ 외부기관공고 수집 완료 ({len(collected_data)}건)")

def crawl_active_scholarships_with_selenium():
    url = "https://scho.chosun.ac.kr/scho/2138/subview.do"
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    collected_data = []

    print(f"▶ [5/6] 장학안내 수집 중...")
    try:
        driver.get(url)
        time.sleep(5) 

        for page in range(1, 4):
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            for row in soup.select("table tbody tr"):
                row_text = row.get_text(separator=' ', strip=True).replace(" ", "")
                if "D-" not in row_text and "D-day" not in row_text.lower(): continue

                d_day_area = row.select_one("div.date_fl")
                raw_dday = d_day_area.get_text(strip=True).replace(" ", "") if d_day_area else "D-Day"
                
                title_tag = row.select_one("td.subject a")
                if not title_tag: continue
                title = title_tag.text.strip()
                link = title_tag['href']
                link = "https://scho.chosun.ac.kr" + link if link.startswith("/") else url + link if link.startswith("?") else link
                    
                try:
                    detail_resp = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=5)
                    detail_resp.encoding = 'utf-8'
                    content_tag = BeautifulSoup(detail_resp.text, 'html.parser').select_one("div.user-article")
                    content_text = content_tag.get_text(separator='\n', strip=True) if content_tag else "본문 없음"
                except Exception: content_text = "본문 수집 에러"

                collected_data.append(f"분류: 장학안내\n상태: {raw_dday}\n제목: {title}\n내용:\n{content_text}")
                
            if page < 3:
                try:
                    driver.find_element(By.LINK_TEXT, str(page + 1)).click()
                    time.sleep(3) 
                except: break
    except Exception as e: print(f"❌ 장학안내 에러: {e}")
    finally:
        driver.quit() 
        if collected_data:
            with open(os.path.join(DATA_SAVE_DIR, "지금_신청_가능한_장학금.txt"), "w", encoding="utf-8") as f:
                f.write("\n---\n".join(collected_data))
            print(f"  ✅ 장학안내 수집 완료 ({len(collected_data)}건)")

def crawl_cafeteria_menus():
    target_menus = {
        "글로벌 기숙사식당": "https://www3.chosun.ac.kr/chosun/608/subview.do",
        "입석홀 식당": "https://www3.chosun.ac.kr/chosun/607/subview.do",
        "백학사 식당(구 서석홀)": "https://www3.chosun.ac.kr/chosun/615/subview.do"
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    collected_data = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"▶ [6/6] 조선대학교 식단표 수집 중...")
    for name, url in target_menus.items():
        try:
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.select_one("table")
            
            if table:
                menu_text = f"분류: 식단안내\n식당명: {name}\n수집일시: {now}\n내용:\n"
                for row in table.find_all("tr"):
                    cells = row.find_all(['th', 'td'])
                    row_text = " | ".join([cell.get_text(separator=', ', strip=True) for cell in cells])
                    if row_text: menu_text += row_text + "\n"
                collected_data.append(menu_text)
            else:
                content_tag = soup.select_one("div.user-article, div.board-view-content")
                if content_tag:
                    text = content_tag.get_text(separator='\n', strip=True)
                    collected_data.append(f"분류: 식단안내\n식당명: {name}\n수집일시: {now}\n내용:\n{text}")
            time.sleep(1)
        except Exception as e: print(f"❌ {name} 에러: {e}")

    if collected_data:
        with open(os.path.join(DATA_SAVE_DIR, "조선대학교_식단.txt"), "w", encoding="utf-8") as f:
            f.write("\n---\n".join(collected_data))
        print(f"  ✅ 식단표 수집 완료 ({len(collected_data)}개 식당)")

# =====================================================================
# 🧠 [수정됨] 갱신 데이터 전용 DB 완전 초기화 및 생성 함수
# =====================================================================
def update_daily_chroma_db():
    print("\n" + "="*60)
    print("🧠 [전용 DB 생성 시작] 기존 갱신 DB를 비우고 오늘의 데이터로 꽉 채웁니다...")
    
    try:
        embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
        
        # 1. 기존에 갱신용 DB 폴더가 있다면 과감하게 삭제 (초기화)
        if os.path.exists(UPDATE_DB_DIR):
            print("  🗑️ 어제 만들어둔 갱신 DB 폴더를 초기화합니다.")
            shutil.rmtree(UPDATE_DB_DIR)
            time.sleep(1) # 삭제 후 잠시 대기

        # 2. 완전히 깨끗한 새 DB 컬렉션 생성
        vectorstore = Chroma(
            persist_directory=UPDATE_DB_DIR, 
            embedding_function=embeddings, 
            collection_name=UPDATE_COLLECTION_NAME
        )
        
        all_documents = []

        # 3. 바탕화면 전용 폴더에 모인 txt 파일들을 읽어서 청크로 쪼개기
        for filename in os.listdir(DATA_SAVE_DIR):
            if not filename.endswith(".txt"): continue
            
            filepath = os.path.join(DATA_SAVE_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            chunks = [c.strip() for c in content.split("---") if c.strip()]
            
            for i, chunk in enumerate(chunks):
                metadata = {"source": filename, "chunk_index": i}
                all_documents.append(Document(page_content=chunk, metadata=metadata))
                
        # 4. 새 DB에 오늘 수집한 데이터 통째로 밀어넣기
        if all_documents:
            vectorstore.add_documents(all_documents)
            print(f"  ✨ 전용 DB 생성 완료! (총 {len(all_documents)}개 청크 이식됨)")
                
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ 전용 DB 업데이트 중 오류 발생: {e}")

# =====================================================================
# 통합 실행 및 스케줄러 관리
# =====================================================================
def run_pipeline():
    print("\n" + "="*60)
    print(f"🤖 [자동 파이프라인 가동] 현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 1. 데이터 수집 (바탕화면 폴더에 파일 저장)
    crawl_extracurricular_data()
    crawl_academic_notices()
    crawl_general_notices()
    crawl_external_notices()
    crawl_active_scholarships_with_selenium()
    crawl_cafeteria_menus()
    
    # 2. 갱신 전용 DB 초기화 및 생성
    update_daily_chroma_db()
    
    print("🎉 [파이프라인 완료] 오늘의 교내 데이터 수집 및 전용 DB 갱신이 끝났습니다.")

if __name__ == "__main__":
    # 프로그램을 켜자마자 즉시 1회 전체 파이프라인 실행
    run_pipeline()
    
    # 매일 한국시간 오전 9시에 반복 실행되도록 스케줄 등록
    # (주의: 코드가 실행되는 컴퓨터의 시스템 시간이 한국 시간(KST)으로 설정되어 있어야 합니다)
    schedule.every().day.at("09:00").do(run_pipeline)
    
    print("⏰ 파이프라인 스케줄러가 백그라운드에서 가동 중입니다...")
    print(f"📁 텍스트 파일 모음 폴더: {DATA_SAVE_DIR}")
    print(f"🧠 갱신 데이터 전용 DB 폴더: {UPDATE_DB_DIR}")
    print("※ 매일 오전 9시에 자동 갱신됩니다. 이 터미널 창을 닫지 마세요.")
    print("※ 종료하시려면 Ctrl + C 를 누르세요.\n")
    
    while True:
        schedule.run_pending()
        time.sleep(60)
