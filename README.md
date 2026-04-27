chosun_updater이 먼저 실행해서 갱신 DB 설정 후 신호를 보내서 감지하면 backend 실행

git bash 창에서
docker compose up --build

구동 안될 시 해당 명령어로 
docker compose -f "docker compose.yml" up --build

docker로 바로 실행



