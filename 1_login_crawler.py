import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
import concurrent.futures
import os
from tqdm import tqdm
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =====================================
# 1. 로그인 정보 및 [새로운] 초기 설정
# =====================================
USER_ID = "비공개"
USER_PW = "비공개"
LOGIN_URL = "https://www3.chosun.ac.kr/chosunLogin/chosun/login.do" # F12 네트워크 탭에서 확인한 실제 로그인 주소

base_urls = [
    "https://www3.chosun.ac.kr/sites/chosun/index.do",
    "https://eie.chosun.ac.kr/eie/index.do",
    "https://scho.chosun.ac.kr/scho/index.do",
    "https://counsel.chosun.ac.kr/counsel/index.do",
    "https://thechoa.chosun.ac.kr/clientMain/a/t/main.do",
    "https://www3.chosun.ac.kr/chosun/208/subview.do",
    "https://sw.chosun.ac.kr/main/"
]

EXCLUDE_EXT = ('.hwp', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.jpg', '.png', '.gif')

# 기존 데이터와 섞이지 않도록 새로운 이름 사용!
PDF_DIR = "./login_chosun_pdfs"
LINKS_FILE = "login_html_links.txt"
os.makedirs(PDF_DIR, exist_ok=True)

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[ 500, 502, 503, 504 ])
session.mount('http://', HTTPAdapter(max_retries=retries))
session.mount('https://', HTTPAdapter(max_retries=retries))
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8"
})

# =====================================
# 2. 로그인 및 URL 정규화
# =====================================
def login():
    print("⏳ 학교 포털 로그인 시도 중...")
    login_data = {"id": USER_ID, "password": USER_PW} # 파라미터 이름 확인 필요
    try:
        res = session.post(LOGIN_URL, data=login_data, verify=False, timeout=10)
        print("✅ 로그인 요청 완료! (세션 쿠키 획득)")
    except Exception as e:
        print(f"❌ 로그인 요청 실패: {e}")

def normalize_url(url):
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path
    if len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    return urlunparse((parsed.scheme, netloc, path, parsed.params, parsed.query, ''))

# =====================================
# 3. 링크 탐색 함수
# =====================================
def get_links_from_url(url):
    html_links, pdf_links = set(), set()
    try:
        res = session.get(url, timeout=3, verify=False) # 3초 타임아웃 방어막
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for a in soup.find_all("a", href=True):
                raw_url = urljoin(url, a['href']).split('#')[0]
                if "chosun.ac.kr" in raw_url and raw_url.startswith("http"):
                    clean_url = normalize_url(raw_url)
                    lower_url = clean_url.lower()
                    if lower_url.endswith('.pdf'):
                        pdf_links.add(clean_url)
                    elif not lower_url.endswith(EXCLUDE_EXT):
                        html_links.add(clean_url)
    except:
        pass
    return html_links, pdf_links

def crawl_site(start_urls, max_depth=3):
    start_urls = [normalize_url(url) for url in start_urls]
    visited_html = set(start_urls)
    current_level_urls = set(start_urls)
    all_html_links = set(start_urls)
    all_pdf_links = set()

    for depth in range(1, max_depth + 1):
        print(f"\n🔎 [Depth {depth}/{max_depth}] 탐색 시작... (대상 URL: {len(current_level_urls)}개)")
        next_level_urls = set()

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(get_links_from_url, url): url for url in current_level_urls}
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures)):
                htmls, pdfs = future.result()
                all_pdf_links.update(pdfs)
                for link in htmls:
                    if link not in visited_html:
                        visited_html.add(link)
                        next_level_urls.add(link)
                        all_html_links.add(link)

        current_level_urls = next_level_urls
        if not current_level_urls: break

    return list(all_html_links), list(all_pdf_links)

def download_pdf(pdf_url):
    try:
        filename = pdf_url.split('/')[-1].split('?')[0]
        if not filename.lower().endswith('.pdf'): return None
        filepath = os.path.join(PDF_DIR, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0: return filepath
            
        res = session.get(pdf_url, timeout=10, stream=True, verify=False)
        with open(filepath, 'wb') as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath
    except:
        return None

if __name__ == "__main__":
    login()
    print("\n⏳ 1. 링크 탐색 시작 (Max Depth = 3)")
    html_links, pdf_links = crawl_site(base_urls, max_depth=3)
    
    with open(LINKS_FILE, 'w', encoding='utf-8') as f:
        for link in sorted(html_links):
            f.write(link + "\n")
    print(f"\n✅ HTML 링크 {len(html_links)}개 저장 완료 ({LINKS_FILE})")

    print("\n⏳ 2. PDF 파일 다운로드")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        list(tqdm(executor.map(download_pdf, pdf_links), total=len(pdf_links)))
    print("\n🎉 로그인 기반 1단계 완료! теперь 2_login_db_builder.py를 실행하세요.")
