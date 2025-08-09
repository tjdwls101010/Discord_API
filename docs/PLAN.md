## 프로젝트 실행 계획 (PLAN)

### 1) 아키텍처 개요
- 단일 컨테이너: Python(FastAPI) + DiscordChatExporter CLI(Linux x64)
- 흐름:
  1. `POST /exports` → `job_id` 발급, `exports` 레코드 생성(`pending`)
  2. 백그라운드에서 DCE CLI 실행(`--after/--before`), JSON 출력
  3. JSON 파싱 후 `messages`에 batch insert, 카운트 집계
  4. 상태/카운트/에러 업데이트 → `completed` 또는 `failed`
  5. `GET /exports/{job_id}`로 상태 확인

### 2) 저장소 구조(제안)
```
Discord_API/
  app/
    main.py              # FastAPI 엔트리
    dce.py               # DCE CLI 래퍼
    supa.py              # Supabase 클라이언트/DAO
    models.py            # pydantic 스키마
    workers.py           # 백그라운드 작업/오케스트레이션
    metrics.py           # 메트릭/로깅 도우미
  Dockerfile
  requirements.txt
  docs/
    PRD.md
    PLAN.md
```

### 3) 스키마/DDL (Supabase)
- `exports`와 `messages` 테이블은 PRD와 동일. 배포 전 Supabase SQL 에디터에서 생성.
- 대용량 대비 인덱스 생성, JSONB 컬럼 사용, `ON CONFLICT (message_id) DO NOTHING` 적용.
 - 환경변수는 `.env`와 Render 대시보드를 통해 주입: `SUPABASE_URL`, `SUPABASE_KEY`, `DISCORD_TOKEN` 등. `.env`는 로컬 테스트 용도로만 사용하고 저장소에 커밋하지 않음.

### 4) 개발 단계(WBS)

#### Phase 0 — 준비/보안
- Git 히스토리에서 노출된 토큰/키 제거, 모두 회수(rotate).
- Render와 Supabase 프로젝트 생성, 환경변수 준비.
 - (MCP) Supabase MCP/Render MCP 사용 준비: 인증 설정(워크스페이스 선택), 비용 확인/승인 흐름 숙지.

#### Phase 1 — 스캐폴딩
- FastAPI 앱 최소 엔드포인트(`/health`), 프로젝트 구조 생성.
- `requirements.txt`:
  - fastapi
  - uvicorn[standard]
  - supabase
  - pydantic
  - python-dateutil
- 로컬 실행/헬스 체크.
 - `.env` 사용을 위해 `python-dotenv`(선택) 고려. 단, 운영(Render)에서는 사용하지 않음.

#### Phase 2 — DCE 래퍼
- `app/dce.py`:
  - 실행 경로: `/opt/dce/DiscordChatExporter.Cli`
  - 인터페이스: `export_json(token, channel_id, start_at, end_at, media=False) -> dict`
  - 서브프로세스 타임아웃/에러 캡처/마스킹 로깅
 - 개발 참고 자료: `docs/Reference/Guide_DiscordChatExporter.md`의 포맷/날짜/필터 옵션을 주기적으로 반영

#### Phase 3 — Supabase DAO
- `app/supa.py`:
  - `get_client()` — 환경변수 로드/검증
  - `insert_export(job)` / `update_export(job)` / `insert_messages(batch)`
  - `ON CONFLICT (message_id) DO NOTHING` (서버 RPC 또는 클라이언트 upsert)
 - (MCP) Supabase 마이그레이션: `/supabase/migrations/`에 SQL 파일로 생성 및 적용.

#### Phase 4 — API 구현
- `POST /exports` 입력 검증(pydantic): ISO8601, UTC 강제
- `GET /exports/{job_id}` 상태 조회
- 공통 에러 포맷 일원화
- 채널/서버는 고정값 사용: API 요청 본문에서는 받지 않음. 내부적으로 `DEFAULT_CHANNEL_ID`를 사용

#### Phase 5 — 백그라운드 처리
- FastAPI `BackgroundTasks` 또는 `asyncio.create_task`로 비동기 실행
- 상태 전이: `pending → running → completed|failed`
- 카운트, 소요시간(ms) 기록

#### Phase 6 — 관측성
- 구조화 로그(JSON), 요청 ID/`job_id` 상관관계 저장
- `/metrics` 기본 카운터/히스토그램(선택)

#### Phase 7 — 컨테이너/Dockerfile
- Python 3.12 slim 베이스
- DCE 릴리스 zip(Linux x64) 다운로드/설치
- Apple Silicon: `--platform=linux/amd64`로 빌드/실행
 - (MCP) Render 서비스 생성/설정은 Render MCP로 자동화 가능.

#### Phase 8 — 테스트
- 단위: DCE 명령 생성, 파싱, DAO 에러 핸들링
- 통합: 로컬 Docker 컨테이너로 end-to-end(실 토큰/테스트 채널)
- 성능: 10k 메시지 샘플에서 30초 이내 확인

#### Phase 9 — 배포
- Render: Docker deploy from repo, 환경변수 등록
- 롤아웃 검증: 헬스 체크 → 소규모 실제 작업 → 모니터링

#### Phase 10 — 하드닝
- 속도 제한(분당 10회), 입력 검증 강화
- 대용량 batch insert 최적화, 재시도 정책

### 5) Dockerfile(권장)
```dockerfile
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip ca-certificates && rm -rf /var/lib/apt/lists/*

ARG DCE_VERSION=2.46
RUN curl -L -o /tmp/dce.zip "https://github.com/Tyrrrz/DiscordChatExporter/releases/download/${DCE_VERSION}/DiscordChatExporter.Cli.Linux-x64.zip" \
 && unzip /tmp/dce.zip -d /opt/dce \
 && chmod +x /opt/dce/DiscordChatExporter.Cli \
 && rm /tmp/dce.zip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

환경변수 매핑(로컬 `docker run` 예시):
```bash
docker run --rm -p 8000:8000 \
  -e DISCORD_TOKEN="$(grep -E '^DISCORD_TOKEN' .env | cut -d '=' -f2-)" \
  -e SUPABASE_URL="$(grep -E '^SUPABASE_URL' .env | cut -d '=' -f2-)" \
  -e SUPABASE_KEY="$(grep -E '^SUPABASE_KEY' .env | cut -d '=' -f2-)" \
  -e DEFAULT_CHANNEL_ID="$(grep -E '^DEFAULT_CHANNEL_ID' .env | cut -d '=' -f2-)" \
  my/dce-api:dev
```

### 6) 코드 스켈레톤(발췌)

`app/dce.py`
```python
import json, os, subprocess, tempfile
from typing import Dict, Any

DCE_BIN = "/opt/dce/DiscordChatExporter.Cli"

def export_json(token: str, channel_id: str, start_at: str, end_at: str, media: bool=False) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.json")
        cmd = [
            DCE_BIN, "export",
            "-t", token, "-c", channel_id,
            "--after", start_at, "--before", end_at,
            "-f", "Json", "-o", out
        ]
        if media:
            cmd += ["--media", "true"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise RuntimeError(f"DCE failed: {proc.returncode}")
        with open(out, "r") as f:
            return json.load(f)
```

`app/supa.py`
```python
import os
from supabase import create_client, Client

def get_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)
```

`app/models.py`
```python
from pydantic import BaseModel
from typing import Optional

class ExportCreate(BaseModel):
    channel_id: str
    start_at: str  # ISO8601 UTC
    end_at: str    # ISO8601 UTC
    format: Optional[str] = "Json"
    media: Optional[bool] = False
```

`app/main.py`
```python
import os, time, uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException
from app.models import ExportCreate
from app import dce, supa

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}

def run_job(job_id: str, payload: ExportCreate):
    client = supa.get_client()
    start_ms = time.time()
    client.table("exports").update({"status": "running"}).eq("job_id", job_id).execute()
    data = dce.export_json(os.environ["DISCORD_TOKEN"], payload.channel_id, payload.start_at, payload.end_at, payload.media)
    messages = data.get("messages", data)
    inserted = 0
    for m in messages:
        try:
            client.table("messages").insert({
                "message_id": str(m["id"]),
                "channel_id": payload.channel_id,
                "author_id": str(m.get("author", {}).get("id")),
                "author_name": m.get("author", {}).get("name"),
                "content": m.get("content"),
                "timestamp": m.get("timestamp"),
                "attachments": m.get("attachments"),
                "embeds": m.get("embeds"),
                "raw": m,
                "job_id": job_id
            }).execute()
            inserted += 1
        except Exception:
            pass
    dur = int((time.time() - start_ms) * 1000)
    client.table("exports").update({
        "status": "completed",
        "message_count": len(messages),
        "inserted_count": inserted,
        "duration_ms": dur
    }).eq("job_id", job_id).execute()

@app.post("/exports", status_code=202)
def create_export(req: ExportCreate, bg: BackgroundTasks):
    if req.format != "Json":
        raise HTTPException(status_code=400, detail="Only Json supported in MVP")
    job_id = str(uuid.uuid4())
    client = supa.get_client()
    client.table("exports").insert({
        "job_id": job_id,
        "channel_id": req.channel_id,
        "start_at": req.start_at,
        "end_at": req.end_at,
        "status": "pending"
    }).execute()
    bg.add_task(run_job, job_id, req)
    return {"job_id": job_id}

@app.get("/exports/{job_id}")
def get_export(job_id: str):
    client = supa.get_client()
    res = client.table("exports").select("*").eq("job_id", job_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Not found")
    return res.data
```

### 7) 로컬 개발/테스트

#### Docker 빌드/실행(Apple Silicon 포함)
```bash
docker build --platform=linux/amd64 -t my/dce-api:dev .
docker run --rm --platform=linux/amd64 -p 8000:8000 \
  -e DISCORD_TOKEN="$DISCORD_TOKEN" \
  -e SUPABASE_URL="$SUPABASE_URL" \
  -e SUPABASE_KEY="$SUPABASE_KEY" \
  -e DEFAULT_CHANNEL_ID="$DEFAULT_CHANNEL_ID" \
  my/dce-api:dev
```

#### API 호출 예시
```bash
curl -X POST http://localhost:8000/exports \
  -H "Content-Type: application/json" \
  -d '{"start_at":"2025-07-01T00:00:00Z","end_at":"2025-07-07T00:00:00Z"}'
```

### 8) Render 배포
- “Deploy an existing Dockerfile” → 저장소 연결
- 환경변수: `DISCORD_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`, `DEFAULT_CHANNEL_ID`
- 롤아웃 후 `/health` 확인 → 소규모 실제 작업 테스트
 - 필요 시 `DEFAULT_CHANNEL_ID`, `DEFAULT_SERVER_ID`도 환경변수로 등록 가능
 - (MCP) Render MCP로 환경변수 업데이트/배포 재시작/로그·메트릭 조회 절차 문서화

### 9) 리스크 및 대응
- Discord 토큰/레이트리밋: API 레이트리밋(분당 10회) + 백오프
- 대용량 채널: batch insert 및 압축 고려(향후)
- JSON 구조 변경: DCE 버전 고정 및 호환성 테스트
- 로그 민감정보 마스킹
 - (MCP) 변경/배포 자동화 시 휴먼오류 완화, 단 MCP 권한은 최소권한으로 구성

### 10) 백로그(Nice-to-have)
- 다중 채널 배열 입력
- batch insert 최적화 및 페이로드 압축
- `/status` 목록/필터링, `/metrics`(Prometheus)
- 간단한 HTML 상태 페이지
 - `guide`/`channels` 래핑 API: `docs/Reference/Guide_DiscordChatExporter.md`의 CLI 가이드를 HTTP로 노출


