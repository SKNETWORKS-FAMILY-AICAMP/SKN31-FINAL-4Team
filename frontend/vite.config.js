import { defineConfig, loadEnv } from 'vite';
import { fileURLToPath } from 'node:url';

/* FEEDiT — 여러 장의 정적 페이지를 한 프로젝트로 묶는다.
   여기 등록된 html 만 빌드 결과물(dist)에 들어간다.
   새 시안 페이지를 만들면 이 목록에 한 줄 추가할 것. */
const page = (name) => fileURLToPath(new URL(`./${name}`, import.meta.url));

export default defineConfig(({ mode }) => {
  // 로컬 Django 실행 포트인 API_PORT 를 쓴다. 루트 .env 는
  // 프론트 폴더 밖에 있으므로 Vite 기본 로딩만으로는 읽히지 않는다.
  const projectRoot = fileURLToPath(new URL('../', import.meta.url));
  const env = loadEnv(mode, projectRoot, '');
  const djangoApiTarget = env.VITE_DJANGO_API_URL
    || `http://127.0.0.1:${env.API_PORT || '8000'}`;

  return {
    server: {
      port: 5173,
      open: true,          // npm run dev 하면 브라우저가 알아서 열린다
      /* 챗봇 서버(feedit-chat)로 넘기는 길.
         chat_api.js 는 5173/4173 에서 돌 때 API_BASE 를 '/api' 로 잡는다.
         이 프록시가 없으면 /api/v1/health 가 404 라서 isUp() 이 false 가 되고,
         화면은 조용히 목업 답변으로 떨어진다 — 서버가 떠 있어도 그렇다.

         ★ 챗봇 서버를 따로 켜야 한다:
             cd ../ChatBot && python3 server.py
         안 켜져 있으면 여기 프록시가 ECONNREFUSED 를 내고, 역시 목업으로 떨어진다. */
      /* ★ 배포하지 않아도 로컬에서 실데이터를 볼 수 있게 길을 둘로 나눈다.
       *
       *   /api/v1/…  → 챗봇 (feedit-chat, 8770)
       *   /api/…     → Django API (backend, 루트 .env 의 API_PORT)
       *
       *   순서가 중요하다. vite 는 **먼저 맞는 것**을 쓰므로
       *   더 좁은 /api/v1 을 위에 둔다. 뒤집으면 챗봇 요청이 Django 로 간다.
       *
       *   둘 다 안 켜져 있어도 화면은 돈다 — 챗봇은 목업으로,
       *   지표는 '측정 불가'로 떨어진다. 숫자를 지어내지 않는다.
       *
       *   켜는 법:
       *     Django  cd backend && python manage.py runserver $API_PORT
       *     챗봇     cd ../ChatBot && python3 server.py
       */
      proxy: {
        '/api/v1': {
          target: 'http://127.0.0.1:8770',
          changeOrigin: true,
          rewrite: (p) => p.replace(/^\/api/, ''),
          /* ★ 2026-09-23 — 챗봇은 FEEDIT_CHAT_TOKEN 이 있으면 공개 베타 중에도
             토큰을 검사한다. 배포에서는 버셀 함수가 붙이고, 로컬에서는 이
             프록시가 루트 .env 의 값을 붙인다. 브라우저 번들에는 들어가지 않는다
             (이 설정은 개발 서버의 Node 쪽에서만 돈다). */
          headers: env.FEEDIT_CHAT_TOKEN ? { 'X-FEEDiT-Token': env.FEEDIT_CHAT_TOKEN } : {},
        },
        '/api': {
          // Django 는 주소를 /api/… 그대로 받는다 (config/urls.py 에 api/ 로 걸었다).
          // 그래서 여기서는 경로를 고치지 않는다.
          target: djangoApiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      /* 번들 결과물은 _build/ 로 뺀다.
         public/assets/ (사진) 가 dist/assets/ 로 그대로 복사되기 때문에,
         기본값(assets)을 쓰면 두 종류가 같은 폴더에서 섞인다. */
      assetsDir: '_build',
      rollupOptions: {
        input: {
          main: page('index.html'),   // 플랫폼 메인 (덱 + 앱)
        },
      },
    },
  };
});
