import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

/* FEEDiT — 여러 장의 정적 페이지를 한 프로젝트로 묶는다.
   여기 등록된 html 만 빌드 결과물(dist)에 들어간다.
   새 시안 페이지를 만들면 이 목록에 한 줄 추가할 것. */
const page = (name) => fileURLToPath(new URL(`./${name}`, import.meta.url));

export default defineConfig({
  server: {
    port: 5173,
    open: true,          // npm run dev 하면 브라우저가 알아서 열린다
  },
  build: {
    outDir: 'dist',
    /* 번들 결과물은 _build/ 로 뺀다.
       public/assets/ (사진) 가 dist/assets/ 로 그대로 복사되기 때문에,
       기본값(assets)을 쓰면 두 종류가 같은 폴더에서 섞인다. */
    assetsDir: '_build',
    rollupOptions: {
      input: {
        main: page('index.html'),   // 메인 목업 (덱 + 앱)
      },
    },
  },
});
