# DeepAgent-Base 팀원 배포 가이드

## 전제 조건

| 항목 | 요구사항 |
|------|----------|
| Docker | Docker Engine 20.10+ |
| Docker Compose | v2 (docker compose 명령어 사용) |
| 네트워크 | vLLM 서버 `10.1.61.227:8002` 접근 가능 |
| 포트 | 3000 (프론트엔드), 8000 (백엔드), 1879 (MCP) 사용 가능 |

---

## 빠른 시작 (3단계)

```bash
# 1. 소스코드 받기
git clone <레포지토리 URL>
cd DeepAgent-Base

# 2. 환경변수 설정
cp .env.example .env

# 3. 빌드 & 실행
docker compose up --build
```

> 처음 빌드 시 Docker 이미지 다운로드 포함 약 5~10분 소요됩니다.

---

## 환경변수 설정 상세

`.env` 파일을 열어 자신의 환경에 맞게 수정합니다.

```env
# vLLM 서버 주소 — 팀 공용 서버를 사용하면 그대로 유지
VLLM_BASE_URL=http://10.1.61.227:8002/v1

# 브라우저에서 백엔드에 접근하는 주소
# !! 반드시 자신의 서버 IP로 변경하세요 !!
NEXT_PUBLIC_API_URL=http://<자신의_서버_IP>:8000
```

### NEXT_PUBLIC_API_URL 설정 방법

| 상황 | 값 |
|------|-----|
| 본인 PC에서만 사용 | `http://localhost:8000` |
| 팀원들이 브라우저로 접속 | `http://<서버_IP>:8000` |

자신의 서버 IP 확인:
```bash
hostname -I | awk '{print $1}'
```

> **주의:** `NEXT_PUBLIC_API_URL`은 Next.js 빌드타임에 번들에 하드코딩됩니다.
> 값을 변경하면 반드시 `docker compose up --build frontend`로 프론트엔드를 재빌드해야 합니다.

---

## 서비스 구조

```
docker compose up --build 실행 시 시작 순서:

  mcp-news (포트 1879)      MCP 뉴스 검색 서버
      │ health check 통과
      ▼
  backend (포트 8000)        FastAPI + 멀티 에이전트
      │ health check 통과
      ▼
  frontend (포트 3000)       Next.js 채팅 UI
```

---

## 접속 확인

빌드 완료 후 아래 URL로 접속합니다.

| 서비스 | URL | 설명 |
|--------|-----|------|
| 채팅 UI | `http://<서버IP>:3000` | 메인 채팅 인터페이스 |
| 백엔드 상태 | `http://<서버IP>:8000/api/health` | `{"status":"ok"}` 반환 시 정상 |
| MCP 대시보드 | `http://<서버IP>:8000/mcp/dashboard` | MCP 서버 상태 모니터링 |

---

## 주요 명령어

```bash
# 전체 시작 (백그라운드)
docker compose up --build -d

# 전체 중지
docker compose down

# 로그 확인 (전체)
docker compose logs -f

# 특정 서비스 로그 확인
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f mcp-news

# 특정 서비스만 재빌드
docker compose up --build backend
docker compose up --build frontend

# 컨테이너 상태 확인
docker compose ps
```

---

## 문제 해결

### 1. backend가 unhealthy / 계속 재시작

**증상:** `docker compose ps`에서 backend가 `unhealthy` 또는 `restarting`

**원인:** 대부분 vLLM 서버 연결 실패

```bash
# vLLM 서버 접근 가능한지 확인
curl http://10.1.61.227:8002/v1/models

# 방화벽 문제일 수 있음 — 네트워크 관리자에게 8002 포트 확인 요청
```

### 2. 프론트엔드에서 메시지 전송 시 에러

**증상:** 채팅 입력 후 응답 없음 또는 네트워크 에러

**원인:** `NEXT_PUBLIC_API_URL` 설정 오류

```bash
# 1. .env에서 NEXT_PUBLIC_API_URL 확인
cat .env

# 2. 해당 주소로 백엔드 접근 가능한지 테스트
curl http://<설정한_IP>:8000/api/health

# 3. 값을 수정했다면 반드시 프론트엔드 재빌드
docker compose up --build frontend
```

### 3. 포트 충돌

**증상:** `Bind for 0.0.0.0:8000 failed: port is already allocated`

```bash
# 해당 포트를 사용 중인 프로세스 확인
sudo lsof -i :8000

# 프로세스 종료 후 재시작
sudo kill -9 <PID>
docker compose up --build
```

### 4. Docker 빌드 실패

```bash
# 개별 서비스 빌드로 원인 파악
docker compose build mcp-news
docker compose build backend
docker compose build frontend

# 캐시 무시하고 완전 재빌드
docker compose build --no-cache
```

### 5. 디스크 공간 부족

```bash
# 사용하지 않는 Docker 리소스 정리
docker system prune -f

# 이미지까지 포함하여 정리
docker system prune -a -f
```

---

## 참고: 빌드 이미지 크기

| 서비스 | 이미지 크기 | 베이스 이미지 |
|--------|-------------|---------------|
| backend | ~450 MB | python:3.11-slim |
| frontend | ~207 MB | node:20-alpine (standalone) |
| mcp-news | ~186 MB | python:3.11-slim |

---

## 참고: 환경변수 전체 목록

| 변수 | 기본값 | 설명 | 변경 시점 |
|------|--------|------|-----------|
| `VLLM_BASE_URL` | `http://10.1.61.227:8002/v1` | vLLM 서버 주소 | 런타임 (재시작만 필요) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | 브라우저→백엔드 주소 | **빌드타임** (재빌드 필요) |
| `DOCKER_ENV` | `1` (docker-compose에서 설정) | Docker 환경 여부 | 변경 불필요 |
| `AGENT_ROOT_DIR` | `/app` (Docker 내부) | 에이전트 작업 디렉토리 | 변경 불필요 |
| `MCP_PORT` | `1879` | MCP 서버 포트 | 변경 불필요 |
