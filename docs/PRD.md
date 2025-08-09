## Discord 메시지 아카이빙 API 서비스 - 제품 요구사항 명세서 (PRD)

### 1) 제품 개요
본 서비스는 `DiscordChatExporter`(이하 DCE) CLI를 감싼 경량 REST API입니다. 사용자가 HTTP 요청으로 특정 기간(ISO 8601 형식의 `start_at` / `end_at`) 동안 Discord 채널의 메시지를 내보내고, 결과를 Supabase(Postgres)에 저장합니다. 서비스는 FastAPI 기반으로 Render에 단일 Docker 컨테이너(“API + DCE CLI” 포함)로 배포됩니다.

참고:
- GitHub: DiscordChatExporter — https://github.com/Tyrrrz/DiscordChatExporter/tree/master?tab=readme-ov-file
- Docker Hub: tyrrrz/discordchatexporter — https://hub.docker.com/r/tyrrrz/discordchatexporter

### 2) 목표 및 KPI
- 성능: 메시지 10k 건 이하 기준, 요청 시작 → DB 저장 완료까지 30초 이내(평균).
- 무결성: DB에 삽입된 메시지 수가 DCE가 보고한 메시지 수와 100% 일치.
- 안정성: 월간 호출 100회 기준, 실패율 < 1%.
- 보안: API/로그/코드에 민감정보(Discord 토큰, Supabase 키) 노출 금지.

### 3) 범위
- 포함: 단일 사용자(개인 토큰) 시나리오, 단일 채널 단일 기간 아카이빙, JSON 파싱 후 DB 저장, 작업 상태 조회.
- 본 API는 하나의 고정 채널/서버만 대상으로 합니다. 채널/서버 식별자는 환경변수로 구성되며 요청 본문에서 받지 않습니다.
- 제외(향후 검토): 다중 채널 동시 처리, 대용량 첨부 다운로드 보존, 멀티 테넌시/권한 관리, 실시간 스트리밍 수집.

### 4) 사용자 스토리
- 솔로 개발자로서, 지난 N일 간 특정 채널 메시지를 버튼/스크립트 한 번으로 내보내고 Supabase에 안전하게 저장하고 싶다.
- 환경 구성이나 서버 관리 없이, Render에 배포해 즉시 사용하고 싶다.

### 5) 기능 요구사항

#### 5.0 환경/설정 (.env)
- 로컬 개발 시 `.env` 파일을 사용하여 환경변수를 주입합니다. 운영(Render)에서는 대시보드에 환경변수를 설정합니다.
- 지원 키(로컬 기준):
  - `DISCORD_TOKEN`: DCE가 사용할 사용자/봇 토큰
  - `SUPABASE_URL`: Supabase 프로젝트 URL
  - `SUPABASE_KEY`: Supabase 서비스 키(서버 전용 보관)
  - `SUPABASE_Access_Token`(선택): CI/관리 작업용 토큰. 런타임 필수 아님
  - `DEFAULT_CHANNEL_ID`(필수): 본 API가 대상으로 하는 고정 채널 ID
  - `DEFAULT_SERVER_ID`(선택): 향후 참고용. 본 API의 내보내기에는 필수 아님
- 보안: `.env`는 절대 커밋하지 않습니다. Render에는 동일 키를 환경변수로 등록합니다.

#### 5.1 비동기 내보내기 요청
- Endpoint: POST `/exports`
- Request (JSON):
  - `start_at` (string, 필수, ISO 8601, UTC, 예: `2025-07-01T00:00:00Z`)
  - `end_at` (string, 필수, ISO 8601, UTC)
  - `format` (string, 선택, 기본 `Json`, 허용: `Json`, `PlainText`, `HtmlDark`, `HtmlLight`, `Csv`)
  - `media` (boolean, 선택, 기본 `false`)
  - `filter` (string, 선택): 메시지 필터 구문. 가이드는 참고 문서 참조
- Response:
  - 성공: `202 Accepted`, `{ "job_id": "uuid" }`
  - 실패: `400 Bad Request` (검증 실패), `500 Internal Server Error` (서버 오류)

- CLI 매핑(개발 참고): `export -t $DISCORD_TOKEN -c $DEFAULT_CHANNEL_ID --after $start_at --before $end_at -f $format -o /tmp/out.json [--filter "$filter"] [--media]`
  - 포맷/필터/날짜 구문은 `docs/Reference/Guide_DiscordChatExporter.md`를 따릅니다. 본 API의 기본 포맷은 `Json`입니다.

#### 5.2 작업 상태 조회
- Endpoint: GET `/exports/{job_id}`
- Response:
  - 성공: `200 OK`
    - `{ "job_id": "...", "status": "pending|running|completed|failed", "created_at": "...", "message_count": 123, "inserted_count": 123, "error": null }`
  - 실패: `404 Not Found` (존재하지 않는 job)

#### 5.3 헬스/상태/메트릭(선택)
- GET `/health` — 헬스체크용 단순 OK
- GET `/status` — 최근 작업 목록
- GET `/metrics` — Prometheus 텍스트 형식의 기본 메트릭

### 6) 처리 플로우(요약)
1) 클라이언트가 `POST /exports` 호출 → `job_id` 발급, 상태 `pending` 기록
2) 백그라운드에서 DCE CLI 실행:
   - `DiscordChatExporter.Cli export -t $DISCORD_TOKEN -c $DEFAULT_CHANNEL_ID --after $start --before $end -f Json -o /tmp/out.json`
3) JSON 결과 파싱 → `messages` 테이블에 일괄 삽입
4) 성공 시 상태 `completed`, 카운트 업데이트 / 실패 시 `failed`와 에러 기록

### 7) 데이터 모델 (Supabase / Postgres)

#### 7.1 `exports` (작업 로그)
- `job_id` uuid PK
- `channel_id` text
- `start_at` timestamptz (UTC)
- `end_at` timestamptz (UTC)
- `status` text check in ('pending','running','completed','failed')
- `message_count` int default 0
- `inserted_count` int default 0
- `duration_ms` int
- `error` text null
- `created_at` timestamptz default now()
- 인덱스: (`channel_id`, `created_at`), (`status`, `created_at`)

#### 7.2 `messages`
- `message_id` text PK (Discord 메시지 ID)
- `channel_id` text
- `author_id` text
- `author_name` text
- `content` text
- `timestamp` timestamptz
- `attachments` jsonb
- `embeds` jsonb
- `raw` jsonb (원본 레코드)
- `job_id` uuid (FK → exports.job_id)
- 인덱스: (`channel_id`, `timestamp`), (`author_id`, `timestamp`)
- 중복 방지: `ON CONFLICT (message_id) DO NOTHING`

### 8) 비즈니스 규칙
- 대상 채널은 환경변수 `DEFAULT_CHANNEL_ID`로 고정되며, 요청으로 변경할 수 없습니다.
- 시간구간: `--after`는 시작 시점 포함, `--before`는 종료 시점 제외(DiscordChatExporter 동작에 맞춤). 문서/코드에 명시.
- 무결성: `inserted_count == message_count`를 수용 기준으로 강제. 다르면 실패 처리.
- 재시도: 실패 시 동일 `job_id`로 재실행하지 않음. 새 요청으로 재시도.
- 중복 메시지: PK 충돌 시 삽입 건너뛰되 카운트는 무결성에서 감안(최종 inserted_count 기준).

### 9) 비기능 요구사항
- 성능: 10k 건 ≤ 30초(평균). 파싱/삽입은 batch 처리.
- 관측성: 구조화 로그(JSON), 기본 메트릭(요청 수/성공/실패/작업 시간).
- 확장성: 단일 컨테이너. 추후 워커 분리 고려.
- 가용성: Render 1인 개발 기준의 단순 SLA(장애시 수동 재배포).

### 10) 보안/준수
- Secrets는 오직 환경변수로 주입: `DISCORD_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`.
- 소스/문서/로그에 토큰 원문 저장 금지. 마스킹 출력.
- 과거 노출된 키/토큰은 즉시 회수(rotate)하고 저장소 히스토리에서도 제거 권장.
- Discord 약관 준수, 개인 토큰 사용시 책임은 사용자에게 귀속.

### 11) 운영/배포
- 컨테이너: Python 3.12 + DCE CLI(Linux x64).
- 런타임: Uvicorn(FastAPI).
- Render: Dockerfile로 배포, 환경변수 등록.
- Apple Silicon 로컬 테스트: `--platform=linux/amd64`로 빌드/실행.

※ 구현 과정에서는 Render MCP를 활용해 서비스 생성/환경변수 업데이트/배포 상태 확인/로그·메트릭 조회를 수행할 수 있으나, 런타임 API에는 MCP가 포함되지 않습니다.

### 12) 외부 의존성
- DCE CLI: 버전 고정(예: 2.46), 호환성 테스트 필수.
- FastAPI, Uvicorn, supabase Python SDK.

### 13) 에러 처리/응답 규격
- 400: 검증 실패(필드/형식 오류)
- 404: 존재하지 않는 `job_id`
- 500: 내부 오류(메시지 마스킹)
- 공통 에러 포맷: `{ "error": { "code": "string", "message": "string" } }`

### 14) 수용 기준(AC)
- AC1: `POST /exports` → `202`와 `job_id` 반환
- AC2: 정상 범위 요청 시, `completed` 상태와 `message_count == inserted_count`
- AC3: ISO8601 형식 오류 → `400`
- AC4: 보안: 환경변수 없을 때 실행 중단 및 로그에 원시 토큰 미노출
- AC5: 10k 메시지 ≤ 30초 내 완료(샘플 데이터 기준)

### 15) 참고 링크
- GitHub: DiscordChatExporter — https://github.com/Tyrrrz/DiscordChatExporter/tree/master?tab=readme-ov-file
- Docker Hub: tyrrrz/discordchatexporter — https://hub.docker.com/r/tyrrrz/discordchatexporter

- 내부 참고: `docs/Reference/Guide_DiscordChatExporter.md` — CLI 명령/옵션 상세, 날짜/필터 구문, 포맷 목록

### 16) 구현 도구 및 MCP 사용 고지
- 본 프로젝트의 구현·운영 편의를 위해 MCP 기반 도구를 사용합니다. 이는 개발/배포 과정에서만 사용되며, 런타임 API에 포함되지 않습니다.
  - Supabase MCP: 테이블 생성/마이그레이션 적용(`/supabase/migrations/*.sql`), 어드바이저 점검(보안/성능), 실시간 쿼리/로그 확인, 타입 생성 등 개발 보조.
  - Render MCP: 웹 서비스 생성/설정 변경(환경변수 업데이트 포함), 배포 상태 조회, 빌드/런타임 로그와 메트릭 확인.
- 보안 상 MCP 사용 시에도 원시 토큰은 로그에 노출하지 않습니다. 모든 비밀은 환경변수를 통해 주입합니다.
- 내부 참고: `docs/Reference/Guide_DiscordChatExporter.md` — CLI 명령/옵션 상세, 날짜/필터 구문, 포맷 목록


