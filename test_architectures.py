
import asyncio
import time
import os
import sys
from dotenv import load_dotenv

# Ensure we can import from backend
sys.path.append(os.getcwd())

from backend.main import (
    build_official_web_search_answer,
    build_official_web_search_answer_direct,
    ChatHistoryMessage
)
from backend.jina_utils import web_search_cache

load_dotenv()

async def run_test(name, func, question, interpretation):
    print(f"\n>>> Running Test: {name}")
    # Clear cache to start fresh for each architecture test
    web_search_cache.data = {}
    
    print(f"--- Round 1 (Fresh) ---")
    start = time.time()
    await func(question, [], interpretation)
    print(f"Time: {time.time() - start:.2f}s")
    
    print(f"\n--- Round 2 (Same Question) ---")
    start = time.time()
    await func(question, [], interpretation)
    print(f"Time: {time.time() - start:.2f}s")

async def main():
    question = "2026년 조선대학교 축제 라인업 알려줘"
    interpretation = {
        "standalone_question": "조선대학교 2026년 축제 대동제 라인업"
    }

    print("="*60)
    print("ARCHITECTURAL COMPARISON: AGENT VS DIRECT-PASS")
    print("="*60)
    print(f"Question: {question}")
    
    # Test Agent-based
    await run_test("AGENT-BASED (Reasoning)", build_official_web_search_answer, question, interpretation)
    
    print("\n" + "="*60)
    
    # Test Direct-pass
    await run_test("DIRECT-PASS (Execution)", build_official_web_search_answer_direct, question, interpretation)

if __name__ == "__main__":
    asyncio.run(main())
