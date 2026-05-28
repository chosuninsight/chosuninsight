
import json
import os
import requests
import hashlib
import time
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from backend.utils import is_official_source_url
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# --- Web Search Cache ---
class WebSearchCache:
    def __init__(self, cache_file: str = "backend/data/web_cache.json"):
        self.cache_file = cache_file
        self.data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                print(f"Warning: 캐시 로드 실패: {e}")
                self.data = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: 캐시 저장 실패: {e}")

    def get(self, query: str) -> Optional[Dict[str, Any]]:
        query_hash = hashlib.md5(query.strip().lower().encode("utf-8")).hexdigest()
        entry = self.data.get(query_hash)
        if entry:
            expires_at = entry.get("expires_at", 0)
            if time.time() < expires_at:
                return entry["result"]
            else:
                del self.data[query_hash]
                self._save()
        return None

    def set(self, query: str, result: Dict[str, Any], ttl_seconds: int = 3600):
        query_hash = hashlib.md5(query.strip().lower().encode("utf-8")).hexdigest()
        self.data[query_hash] = {
            "query": query,
            "result": result,
            "expires_at": time.time() + ttl_seconds,
            "cached_at": time.time()
        }
        self._save()

web_search_cache = WebSearchCache()

class JinaSearchTool:
    name = "jina_search"
    description = (
        "조선대학교 관련 최신 정보(축제 라인업, 공지사항 등)를 웹에서 검색할 때 사용합니다. "
        "검색 쿼리를 입력하면 검색 결과의 정제된 텍스트 내용을 반환합니다."
    )

    def __init__(self, api_key: Optional[str] = None, max_results: int = 3):
        self.api_key = api_key
        self.max_results = max_results
        self.base_url = "https://s.jina.ai/"

    def run(self, query: str, official_only: bool = False) -> str:
        cache_query = f"{query} official_only={official_only}"
        cached_result = web_search_cache.get(cache_query)
        if cached_result:
            print(f"Log: [Cache Hit] Query: {query}")
            return cached_result["formatted_text"]

        search_query = query
        if official_only and "site:chosun.ac.kr" not in search_query:
            search_query = f"{query} site:chosun.ac.kr"

        url = f"{self.base_url}{requests.utils.quote(search_query)}"
        headers = {
            "Accept": "application/json",
            "X-With-Generated-Alt": "true"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            print(f"Log: [Jina API Call] Query: {query}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            summary = "" if official_only else data.get("chatResponse", "")
            results = data.get("data", [])
            if official_only:
                results = [res for res in results if is_official_source_url(res.get("url", ""))]
            
            if not results and not summary:
                return "검색 결과가 없습니다."
            
            formatted = []
            if summary:
                # Clean asterisks from summary as requested
                clean_summary = summary.replace("*", "")
                formatted.append(f"--- Jina AI Summary ---\n{clean_summary}\n")
            
            for i, res in enumerate(results[:self.max_results]):
                title = res.get("title", "No Title")
                # Clean asterisks from content
                content = res.get("content", "No Content").replace("*", "")
                link = res.get("url", "")
                formatted.append(f"[{i+1}] {title}\nURL: {link}\nContent: {content}\n")
            
            formatted_text = "\n".join(formatted)
            if official_only and not formatted_text.strip():
                return "조선대학교 공식 출처 검색 결과가 없습니다."

            ttl = 3600 if any(k in query for k in ["축제", "대동제", "라인업"]) else 21600
            web_search_cache.set(cache_query, {"formatted_text": formatted_text, "raw_data": data}, ttl_seconds=ttl)
            
            return formatted_text
        except Exception as e:
            return f"Jina Search API 호출 중 오류 발생: {str(e)}"
