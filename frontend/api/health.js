/* GET /api/health — 배포된 곳에서 AWS RDS 가 실제로 어떤 상태인지 그대로 본다.
 *
 * ── 왜 제일 먼저 이걸 만드나 ──────────────────────────────
 * 지금까지 RDS 상태는 사용자 맥에서 SSM 굴을 뚫고 확인해 왔다.
 * 그래서 "버셀에서도 되나"는 아무도 몰랐다. 이 엔드포인트를 배포하면
 * 브라우저로 주소 한 번 열어서 **추측 없이** 알 수 있다:
 *
 *   · 버셀 함수가 RDS 에 닿는가
 *   · 어느 표에 몇 행이 있는가
 *   · 지표에 필요한 컬럼(temp·momentum·ma7·ma28)이 있는가
 *
 * 2026-09-02 사용자 맥에서 잰 값은 이랬다 — 다르면 그새 바뀐 것이다:
 *   commerce.product 3,375 · dictionary.brand 2,775 · dictionary_term 394
 *   analysis.term_metric_daily **0** · term_assoc_daily **0** · text_document **0**
 */

import { timingSafeEqual } from 'node:crypto';
import { q, isConfigured, backendBase, backendToken, viaBackend } from './_lib/db.js';

// 화면이 쓰는 표만 본다. 47개를 다 세면 느리고, 볼 이유도 없다.
const TABLES = [
  ['commerce.product', '상품'],
  ['commerce.product_source', '상품-출처'],
  ['commerce.product_term', '상품-용어'],
  ['dictionary.brand', '브랜드'],
  ['dictionary.dictionary_term', '용어 사전'],
  ['dictionary.term_alias', '용어 별칭'],
  ['snapshot.product_source_snapshot', '가격 스냅샷'],
  ['snapshot.resale_snapshot', '리세일 스냅샷'],
  ['analysis.term_metric_daily', '★ 트렌드 지표'],
  ['analysis.term_assoc_daily', '★ 연관어'],
  ['analysis.text_document', '텍스트 원문'],
  ['collection.source', '수집 출처'],
];

export default async function handler(req, res) {
  /* ★ 2026-09-09 — 길이 둘이 됐다.
   *
   *   이 파일은 **pg 직결만** 보고 있었다. 그래서 SSM 굴을 걷어내고
   *   EC2 의 Django 를 거치도록 바꾼 뒤에는, 다른 엔드포인트가 전부 멀쩡히
   *   도는데도 여기만 "AWS RDS 접속 정보가 없습니다" 라고 답했다.
   *   **잘 돌고 있는 것을 고장났다고 말하는 진단**이라 제일 나쁜 종류다.
   *
   *   그래서 다른 엔드포인트와 같은 순서로 본다:
   *     BACKEND_API_URL 이 있으면 → Django 로 넘긴다 (지금 쓰는 길)
   *     없으면                    → pg 직결 (RDS 를 공개로 연 경우)
   */
  const base = backendBase();
  if (base) {
    const relayed = await viaBackend('/health');
    return respond(req, res, {
      checked_at: new Date().toISOString(),
      route: 'backend',
      backend_url: base,
      token_sent: Boolean(backendToken()),
      backend: relayed,
      verdict:
        relayed && relayed.ok
          ? 'Django API 를 거쳐 RDS 를 읽고 있습니다. 아래 backend 를 보세요.'
          : 'Django API 에 닿지 못했거나 오류를 돌려줬습니다. backend.reason 을 보세요.' +
            (relayed && relayed.reason && String(relayed.reason).includes('401')
              ? ' (401 이면 버셀 BACKEND_API_TOKEN 과 서버 FEEDIT_API_TOKEN 이 다릅니다.)'
              : ''),
    });
  }

  const out = {
    checked_at: new Date().toISOString(),
    route: 'pg',
    configured: isConfigured(),
    connected: false,
    server: null,
    tables: {},
    metric_columns: null,
    verdict: '',
  };

  if (!out.configured) {
    out.verdict =
      'BACKEND_API_URL 도 DATABASE_URL 도 없습니다. 버셀 Settings → ' +
      'Environment Variables 에 둘 중 하나를 넣고 다시 배포하세요. ' +
      '(지금 쓰는 방식은 BACKEND_API_URL = http://feedit-official.duckdns.org/api 입니다.)';
    return respond(req, res, out);
  }

  const ver = await q('SELECT version() AS v, current_database() AS db');
  if (!ver.ok) {
    out.verdict =
      `RDS 에 못 붙었습니다 (${ver.code}). ` +
      'RDS 가 밖에서 보이는지(공개 접근 · 보안 그룹)를 DB 팀과 확인하세요.';
    out.detail = ver.error;
    return respond(req, res, out);
  }
  out.connected = true;
  out.server = { version: String(ver.rows[0].v).split(',')[0], database: ver.rows[0].db };

  // 표별 행 수 — 한 번의 질의로 끝낸다.
  const union = TABLES.map(([t], i) => `SELECT ${i} i, count(*) n FROM ${t}`).join(' UNION ALL ');
  const counts = await q(union);
  if (counts.ok) {
    for (const row of counts.rows) {
      const [name, label] = TABLES[Number(row.i)];
      out.tables[name] = { label, rows: Number(row.n) };
    }
  } else {
    out.tables_error = counts.error;
  }

  // ★ 지표 컬럼이 있는지 — 없으면 온도·모멘텀을 아예 못 보낸다.
  //   RDS(Django) 쪽에는 mention_count·trend_score 만 있고
  //   temp·momentum·ma7·ma28 이 없다는 게 2026-09-02 확인이었다.
  const cols = await q(
    `SELECT column_name FROM information_schema.columns
      WHERE table_schema='analysis' AND table_name='term_metric_daily'
      ORDER BY ordinal_position`,
  );
  if (cols.ok) {
    const have = cols.rows.map((r) => r.column_name);
    const want = ['temp', 'momentum', 'ma7', 'ma28', 'level', 'pct_rank'];
    out.metric_columns = {
      all: have,
      needed_present: want.filter((c) => have.includes(c)),
      needed_missing: want.filter((c) => !have.includes(c)),
    };
  }

  out.verdict = verdict(out);
  return respond(req, res, out);
}

function verdict(o) {
  const metric = o.tables['analysis.term_metric_daily'];
  const product = o.tables['commerce.product'];
  const bits = [];

  if (metric && metric.rows > 0) {
    bits.push(`트렌드 지표 ${metric.rows.toLocaleString()}행 — 화면에 실값을 띄울 수 있습니다.`);
  } else if (metric) {
    bits.push(
      '트렌드 지표가 0행입니다. 크롤러의 rds_sync 는 commerce·dictionary·snapshot 8개 표에만 ' +
        '쓰고 analysis.* 에는 쓰지 않습니다 — 보내는 코드가 아직 없는 것이지 연결이 끊긴 게 아닙니다.',
    );
  }
  if (product && product.rows > 0) {
    bits.push(`상품은 ${product.rows.toLocaleString()}건 있어 목록·가격은 실값으로 보여 줄 수 있습니다.`);
  }
  if (o.metric_columns && o.metric_columns.needed_missing.length) {
    bits.push(
      `지표 표에 ${o.metric_columns.needed_missing.join('·')} 컬럼이 없습니다. ` +
        '온도·모멘텀을 보내려면 metrics(JSON) 에 담거나 스키마를 고쳐야 합니다 — DB 팀과 정할 일입니다.',
    );
  }
  return bits.join(' ');
}

/* ★ 2026-09-21 보안 — 이 진단은 내부 구조를 통째로 말한다.
 *
 *   backend_url(프로토콜까지) · 스키마와 표 이름 · 각 표의 정확한 행 수 ·
 *   지표 버전까지 나간다. 누구나 열 수 있으면 공격자에게 "어디를 무엇으로
 *   치면 되는지"를 그대로 건네주는 셈이다.
 *
 *   그렇다고 없애면 배포된 곳 상태를 볼 길이 사라진다. 그래서 **닫되
 *   열쇠를 만든다**:
 *
 *     · 로컬 개발 · 테스트(NODE_ENV!=='production')  → 지금까지처럼 전문
 *     · 배포                                        → 요약만
 *       전문을 보려면 버셀 환경변수 HEALTH_DIAG_TOKEN 을 정하고
 *         /api/health?key=<그 값>   (또는 머리글 X-FEEDiT-Diag)
 *
 *   요약도 거짓말은 하지 않는다 — 검사는 똑같이 하고, 결과만 접어서 준다.
 */
function diagAllowed(req) {
  const deployed = process.env.NODE_ENV === 'production' || Boolean(process.env.VERCEL);
  if (!deployed) return true;

  const want = (process.env.HEALTH_DIAG_TOKEN || '').trim();
  if (!want) return false;                       // 열쇠를 안 정했으면 안 연다

  const url = new URL(req.url, 'http://x');
  const got = String(
    url.searchParams.get('key') || req.headers['x-feedit-diag'] || '',
  ).trim();

  // 길이가 다르면 timingSafeEqual 이 던진다. 먼저 걸러내고 상수 시간으로 견준다.
  const a = Buffer.from(got, 'utf8');
  const b = Buffer.from(want, 'utf8');
  return a.length === b.length && timingSafeEqual(a, b);
}

/** 전문을 줄지 요약만 줄지 여기서 한 번에 가른다. */
function respond(req, res, body) {
  if (diagAllowed(req)) return json(res, body);

  // 요약 — "붙었나" 하나만. 표 이름도 행 수도 주소도 나가지 않는다.
  const ok =
    body.route === 'backend'
      ? Boolean(body.backend && body.backend.ok)
      : Boolean(body.connected);
  return json(res, {
    status: ok ? 'ok' : 'error',
    checked_at: body.checked_at,
  });
}

function json(res, body) {
  res.statusCode = 200;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store'); // 진단은 늘 지금 값이어야 한다
  res.end(JSON.stringify(body, null, 1));
}
