#!/bin/bash

# 1. 경로 고정
cd "$(dirname "$0")"
echo "🚀 [Project CLMN] 환경 세팅을 시작합니다..."

# 2. 가상환경(venv) 생성 (py, python3, python 순서로 시도)
if [ ! -d "venv" ]; then
    echo "📦 가상환경(venv) 폴더를 생성합니다..."
    py -3.11 -m venv venv || python -m venv venv || python3 -m venv venv
else
    echo "✅ 이미 가상환경이 존재합니다."
fi

# 3. 가상환경 파이썬 경로 설정 (윈도우/맥 호환)
if [ -f "./venv/Scripts/python.exe" ]; then
    VENV_PYTHON="./venv/Scripts/python.exe"
else
    VENV_PYTHON="./venv/bin/python"
fi

# 4. 라이브러리 설치 (가장 확실한 방식)
echo "📥 라이브러리 설치를 시작합니다..."
$VENV_PYTHON -m pip install --upgrade pip

# 상대 경로 문제 해결을 위해 파일 존재 여부 확인 후 설치
if [ -f "requirements.txt" ]; then
    REQ_PATH="requirements.txt"
elif [ -f "backend/requirements.txt" ]; then
    REQ_PATH="backend/requirements.txt"
fi

echo "📍 사용하는 설정 파일: $REQ_PATH"
$VENV_PYTHON -m pip install --no-cache-dir -r $REQ_PATH

# 5. Ollama 모델 자동 다운로드 (팀장님 요청사항 반영)
echo "🤖 Ollama AI 모델 확인 및 다운로드..."
ollama pull gemma3:4b

echo "------------------------------------------"
echo "🎉 세팅 완료! 이제 'run_all.bat'를 실행하세요."
echo "------------------------------------------"