# Discord 메시지 아카이빙 API (비개발자용 가이드)

이 서비스는 지정된 디스코드 채널의 특정 시간 구간 메시지를 내보내어 Supabase(Postgres)에 저장하는 간단한 API입니다. 내부적으로 DiscordChatExporter(CLI)를 사용합니다.

- 배포 예시(URL): `https://discord-api-fmwa.onrender.com`
- 이 문서는 “사용자 입장”에서 최대한 쉽게, 단계별로 설명합니다.

---

## 무엇을 할 수 있나요?
- 시작 시간과 종료 시간을 보내면, 그 시간대의 디스코드 채널 메시지를 가져와 데이터베이스에 저장합니다.
- 작업 상태를 조회해 수집이 끝났는지 확인할 수 있습니다.

참고 사항
- 채널은 운영자가 환경변수로 고정해 둡니다. 사용자가 임의로 바꿀 수 없습니다.
- 저장되는 시간(`timestamp`)은 항상 UTC(세계 표준시)입니다.
- API 요청 시 한국시간(Asia/Seoul) 기준으로 보낼 수도 있습니다.

---

## 가장 쉬운 사용법(바로 복붙)
아래는 실제 배포 주소를 그대로 사용합니다: `https://discord-api-fmwa.onrender.com`

1) 서비스가 살아있는지 확인
```bash
curl https://discord-api-fmwa.onrender.com/health
# 기대 응답: {"ok": true}
```

2) 메시지 수집 요청하기(예: 한국시간 2025-08-05 22:30 ~ 23:30)
```bash
curl -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00",
    "end_at":   "2025-08-05T23:30:00",
    "timezone":  "Asia/Seoul"
  }'
# 기대 응답: {"job_id": "..."}
```

3) 작업 상태 확인하기
```bash
curl https://discord-api-fmwa.onrender.com/exports/<여기에_받은_job_id_붙이기>
```

4) 최근 작업 목록 보기(선택)
```bash
curl https://discord-api-fmwa.onrender.com/status
```

5) 서비스 메트릭 보기(선택)
```bash
curl https://discord-api-fmwa.onrender.com/metrics
```

---

## 시간·타임존 안내(중요)
- 입력 필드
  - `start_at`, `end_at`: 시간 문자열(ISO 8601 형식)
  - `timezone`: 선택값(예: `Asia/Seoul`). `start_at`/`end_at`에 시간대 표기가 없으면 이 값으로 해석합니다.
- 내부 동작
  - API는 받은 시간을 UTC로 변환해 처리합니다.
  - 저장되는 `timestamp` 컬럼도 UTC 입니다(한국시간 아님).
- DiscordChatExporter 규칙
  - `--after`(시작 시간)는 “포함”, `--before`(종료 시간)는 “제외”입니다.

예) `2025-08-05 22:30~23:30 Asia/Seoul`로 보내면 내부적으로 `2025-08-05T13:30:00Z ~ 20:30:00Z(UTC)`로 변환됩니다.

---

## API 요약

### POST /exports
- 설명: 메시지 수집 작업을 비동기로 시작합니다.
- 요청(JSON)
  - `start_at`: string, 필수
  - `end_at`: string, 필수
  - `timezone`: string, 선택(기본 `UTC`). 예: `Asia/Seoul`
  - `format`: string, 선택(기본 `Json`). 현재는 `Json`만 지원
  - `media`: boolean, 선택(기본 false)
  - `filter`: string, 선택(DiscordChatExporter의 필터 구문)
- 응답
  - 202 Accepted `{ "job_id": "uuid" }`

예시(UTC로 직접 보낼 때)
```bash
curl -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T13:30:00Z",
    "end_at":   "2025-08-05T20:30:00Z"
  }'
```

### GET /exports/{job_id}
- 설명: 특정 작업의 상태를 조회합니다.
- 응답 예시
```json
{
  "job_id": "...",
  "status": "completed",
  "message_count": 98,
  "inserted_count": 98,
  "duration_ms": 45897,
  "error": null
}
```

상태 값
- `pending`: 대기 중
- `running`: 수집/저장 중
- `completed`: 완료
- `failed`: 실패(에러 메시지 `error` 필드 참고)

특이 케이스: 같은 기간을 여러 번 재수집하면, 이미 저장된 메시지가 있어 `inserted_count`가 0이 될 수 있습니다. 현 설정에서는 “신규 삽입 수와 총 수집 메시지 수가 다르면 failed”로 표기될 수 있습니다(운영 정책에 따라 변경 가능).

### GET /status
- 설명: 최근 작업 목록을 반환합니다.

### GET /health
- 설명: 헬스 체크 엔드포인트(단순 OK)

### GET /metrics
- 설명: 기본 메트릭(Prometheus 텍스트)

---

## 자주 묻는 질문(FAQ)
- Q. 채널 ID만 필요한가요? 서버 ID는요?
  - A. 단일 채널 내보내기는 채널 ID만 있으면 됩니다. 채널 ID는 전역 고유이며, DiscordChatExporter가 서버를 유추합니다.
- Q. 왜 `inserted_count`가 0인데 failed가 나오죠?
  - A. 같은 기간을 재수집하면 DB에 이미 메시지가 있어서 새로 삽입된 건수가 0일 수 있습니다. 현 정책상 “무결성”을 엄격히 적용하여 failed로 표기합니다. 필요 시 정책을 완화할 수 있습니다.
- Q. 0건이 나올 때가 있어요.
  - A. 해당 시간대 실제 메시지가 없거나, 토큰/권한/채널 설정 문제일 수 있습니다. 최근 시간대로 좁혀 테스트해보세요.
- Q. 한국시간으로 보낼 수 있나요?
  - A. 네, `timezone: "Asia/Seoul"`을 함께 보내면 됩니다.

---

## 유지보수자(운영자)용: 로컬 실행 방법(선택)
로컬에서 Docker로 실행하려면(Apple Silicon 포함):
```bash
# 빌드
docker build --platform=linux/amd64 -t discord-archiver:dev .

# 환경변수 설정 후 실행(절대 키를 커밋하지 마세요)
export DISCORD_TOKEN=... \
       SUPABASE_URL=... \
       SUPABASE_KEY=... \
       DEFAULT_CHANNEL_ID=...

docker run --rm --platform=linux/amd64 -p 8000:8000 \
  -e DISCORD_TOKEN -e SUPABASE_URL -e SUPABASE_KEY -e DEFAULT_CHANNEL_ID \
  discord-archiver:dev
```
- 실행 후 브라우저: `http://localhost:8000/health`

필수 환경변수
- `DISCORD_TOKEN`: 디스코드 토큰(유저 또는 봇)
- `SUPABASE_URL`, `SUPABASE_KEY`: Supabase 프로젝트 정보
- `DEFAULT_CHANNEL_ID`: 수집 대상 채널 ID
- (선택) `DEFAULT_SERVER_ID`: 참고용
- (봇 토큰일 경우) `DISCORD_IS_BOT=true` 설정 시 자동으로 `Bot <token>` 형태로 호출합니다.

---

## 문제 해결 팁
- `Authentication token is invalid` → 토큰이 잘못되었거나 권한이 부족합니다.
- `integrity_mismatch (duplicates pre-existed)` → 같은 기간에 이미 저장된 메시지들이 있습니다.
- 처음 요청이 느리다(특히 Free 플랜) → 인스턴스가 절전 상태에서 깨어나는 중일 수 있습니다.

---

## 상황별 예시(복붙)

- 한국시간(KST) 구간 요청(예: 22:30~23:30)
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00",
    "end_at":   "2025-08-05T23:30:00",
    "timezone":  "Asia/Seoul"
  }'
```

- UTC 구간 요청(예: 13:30Z~20:30Z)
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T13:30:00Z",
    "end_at":   "2025-08-05T20:30:00Z"
  }'
```

- 시간대 오프셋을 직접 포함(+09:00)
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00+09:00",
    "end_at":   "2025-08-06T05:30:00+09:00"
  }'
```

- 긴 구간(예: 22:30~다음날 05:30, 한국시간)
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00",
    "end_at":   "2025-08-06T05:30:00",
    "timezone":  "Asia/Seoul"
  }'
```

- 필터 사용(작성자 기준)
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00",
    "end_at":   "2025-08-05T23:30:00",
    "timezone":  "Asia/Seoul",
    "filter":    "from:YourName"
  }'
```

- 필터 사용(이미지 포함 메시지만)
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00",
    "end_at":   "2025-08-05T23:30:00",
    "timezone":  "Asia/Seoul",
    "filter":    "has:image"
  }'
```

- 미디어 다운로드 포함(첨부/아바타 등) — 용량 증가 주의
```bash
curl -sS -X POST https://discord-api-fmwa.onrender.com/exports \
  -H 'Content-Type: application/json' \
  -d '{
    "start_at": "2025-08-05T22:30:00",
    "end_at":   "2025-08-05T23:30:00",
    "timezone":  "Asia/Seoul",
    "media": true
  }'
```

- 작업 상태 폴링(리눅스/맥; jq 설치 시)
```bash
JOB=$(curl -sS -X POST https://discord-api-fmwa.onrender.com/exports -H 'Content-Type: application/json' \
  -d '{"start_at":"2025-08-05T22:30:00","end_at":"2025-08-05T23:30:00","timezone":"Asia/Seoul"}' | jq -r .job_id)
for i in $(seq 1 10); do curl -sS https://discord-api-fmwa.onrender.com/exports/$JOB; echo; sleep 3; done
```

- 작업 상태 단건 조회(복사한 job_id 사용)
```bash
curl -sS https://discord-api-fmwa.onrender.com/exports/<job_id>
```

- 최근 작업 N개(예: 10개)
```bash
curl -sS "https://discord-api-fmwa.onrender.com/status?limit=10"
```

- 헬스/메트릭 빠른 점검
```bash
curl -sS https://discord-api-fmwa.onrender.com/health && echo && curl -sS https://discord-api-fmwa.onrender.com/metrics | head -n 8
```

주의
- DiscordChatExporter 규칙: 시작 시간은 포함, 종료 시간은 제외.
- 레이트리밋: 기본 1분당 10회. 429가 나오면 잠시 후 재시도하세요.

---

## 프론트엔드 연동 가이드(Next.js 예시)

### 핵심 요약
- 버튼 한 번에 결과까지 받고 싶다면: `POST /exports?wait=true&timeout=60`
- 백그라운드로 돌리고 싶다면: `POST /exports` → 반환된 `job_id`로 `GET /exports/{job_id}`를 폴링

### 사전 설치
```bash
npm i @tanstack/react-query
# (선택) 스키마 검증을 원하면
npm i zod
```

### 환경변수(.env.local)
```bash
NEXT_PUBLIC_ARCHIVER_URL=https://discord-api-fmwa.onrender.com
```

### 공통 API 클라이언트
```ts:src/features/exports/api.ts
export const SERVICE_URL = process.env.NEXT_PUBLIC_ARCHIVER_URL ?? 'https://discord-api-fmwa.onrender.com';

export type ExportRequest = {
  start_at: string;   // ISO8601
  end_at: string;     // ISO8601
  timezone?: string;  // 예: 'Asia/Seoul'
  format?: 'Json';
  media?: boolean;
  filter?: string;
};

export type ExportJob = {
  job_id: string;
  status?: 'pending' | 'running' | 'completed' | 'failed';
  message_count?: number;
  inserted_count?: number;
  duration_ms?: number;
  error?: string | null;
};

export async function createExport(req: ExportRequest): Promise<{ job_id: string }> {
  const res = await fetch(`${SERVICE_URL}/exports`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error((await res.text()) || 'request_failed');
  return res.json();
}

export async function createExportAndWait(req: ExportRequest, timeoutSec = 60): Promise<ExportJob> {
  const url = `${SERVICE_URL}/exports?wait=true&timeout=${timeoutSec}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error((await res.text()) || 'request_failed');
  return res.json();
}

export async function getExportStatus(jobId: string): Promise<ExportJob> {
  const res = await fetch(`${SERVICE_URL}/exports/${jobId}`, { cache: 'no-store' });
  if (!res.ok) throw new Error((await res.text()) || 'status_failed');
  return res.json();
}
```

### React Query Provider 설정
```tsx:src/app/providers.tsx
'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

```tsx:src/app/layout.tsx
import type { Metadata } from 'next';
import { Providers } from './providers';

export const metadata: Metadata = { title: 'Discord Archiver' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

### 패턴 A) 버튼 한 번으로 완료까지 대기(wait=true)
```tsx:src/features/exports/components/ExportButtonWait.tsx
'use client'

import { useMutation } from '@tanstack/react-query';
import { createExportAndWait } from '../api';

export function ExportButtonWait() {
  const { mutateAsync, isPending, data, error } = useMutation({
    mutationFn: () =>
      createExportAndWait({
        start_at: '2025-08-05T22:30:00',
        end_at: '2025-08-05T23:30:00',
        timezone: 'Asia/Seoul',
      }, 60),
  });

  return (
    <div>
      <button onClick={() => mutateAsync()} disabled={isPending}>
        {isPending ? '작업 중…' : '메시지 수집(대기)'}
      </button>
      {data && (
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(data, null, 2)}</pre>
      )}
      {error && <p style={{ color: 'red' }}>{String(error)}</p>}
    </div>
  );
}
```

설명
- 성공 시: `status: completed`
- 중복 존재 시: 정책상 `failed`가 될 수 있습니다(예: `integrity_mismatch`). 데이터는 이미 존재하여 신규 삽입이 0건일 수 있습니다.

### 패턴 B) 비동기 실행 + 폴링
```tsx:src/features/exports/components/ExportFlowPolling.tsx
'use client'

import { useMutation, useQuery } from '@tanstack/react-query';
import { createExport, getExportStatus } from '../api';
import { useState } from 'react';

export function ExportFlowPolling() {
  const [jobId, setJobId] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: () =>
      createExport({
        start_at: '2025-08-05T22:30:00',
        end_at: '2025-08-05T23:30:00',
        timezone: 'Asia/Seoul',
      }),
    onSuccess: (res) => setJobId(res.job_id),
  });

  const statusQ = useQuery({
    queryKey: ['export-status', jobId],
    queryFn: () => getExportStatus(jobId!),
    enabled: !!jobId,
    refetchInterval: 2000,
  });

  const isDone = statusQ.data?.status === 'completed' || statusQ.data?.status === 'failed';

  return (
    <div>
      <button onClick={() => createMut.mutate()} disabled={createMut.isPending || (!!jobId && !isDone)}>
        {createMut.isPending ? '요청 중…' : '메시지 수집 시작'}
      </button>

      {jobId && (
        <div style={{ marginTop: 12 }}>
          <div>job_id: {jobId}</div>
          {statusQ.isLoading && <div>상태 조회 중…</div>}
          {statusQ.data && (
            <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(statusQ.data, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}
```

### 타임존 전송 예시(KST)
```ts
await createExport({
  start_at: '2025-08-05T22:30:00',
  end_at: '2025-08-05T23:30:00',
  timezone: 'Asia/Seoul',
});
```

### 에러/경계 상황 UX 권장
- 429(rate_limited): “요청이 많습니다. 잠시 후 다시 시도해주세요.”
- 500(Server not configured…): 운영자에게 문의(환경변수 확인 필요)
- failed + integrity_mismatch: “이미 저장된 메시지가 있어 신규 삽입이 없었습니다.”(추출 자체는 성공일 수 있음)

### 연동 플로우 요약
- 버튼 클릭 → `POST /exports` 또는 `POST /exports?wait=true`
- 즉시 완료 응답을 원하면 wait=true, 오래 걸리면 timeout 시 `job_id`로 전환
- 백그라운드 처리 시에는 `job_id`를 받아 2초 간격 등으로 `GET /exports/{job_id}` 폴링
- 결과 `status`와 카운트(`message_count`, `inserted_count`)를 사용자에게 표시

---

## 문의
문서로 해결되지 않는 문제가 있다면 이 저장소 이슈 또는 운영자에게 문의해주세요.
