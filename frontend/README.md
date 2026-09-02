# FEEDiT — Web

패션 트렌드 플랫폼 FEEDiT 의 프론트엔드 목업.
설명 덱(00–06) → 메인 앱(홈 · 트렌드 분석 · 살!말? · 스타일 · 요금제) 전체 흐름이 한 페이지에 들어 있다.

배포: **main 에 푸시하면 Vercel 이 자동으로 올린다.** PR 을 열면 그 브랜치 전용 미리보기 주소가 따로 생긴다.

---

## 시작하기

```bash
git clone <레포 주소>
cd feedit-web
npm install
npm run dev
```

`http://localhost:5173` 이 자동으로 열린다.
CSS 는 저장하는 즉시 새로고침 없이 반영되고, JS·HTML 은 저장하면 페이지가 자동으로 새로고침된다.

| 명령어 | 하는 일 |
| --- | --- |
| `npm run dev` | 개발 서버 (5173) |
| `npm run build` | 배포용 빌드 → `dist/` |
| `npm run preview` | 빌드 결과물을 로컬에서 그대로 확인 (4173) |

Node 20 이상. `.nvmrc` 가 있으니 nvm 쓰면 `nvm use` 한 줄이면 된다.

### `Cannot find module @rollup/rollup-darwin-arm64` 가 뜬다면

`node_modules/` 를 **다른 OS 나 다른 CPU 에서 설치한 채로 가져온** 경우다.
rollup 은 플랫폼별 네이티브 바이너리를 쓰기 때문에 폴더째 옮기면 안 된다.

```bash
rm -rf node_modules
npm install
```

`package-lock.json` 은 지우지 말 것. 모든 플랫폼의 바이너리 목록이 다 들어 있어서,
맥에서 설치하든 Vercel(리눅스)에서 설치하든 각자 맞는 걸 받아 간다.
`node_modules/` 는 애초에 `.gitignore` 에 있으니 깃으로는 절대 옮겨지지 않는다.

---

## 폴더 구조

```
feedit-web/
├─ index.html            메인 목업 — 마크업만. 25KB 라 통째로 읽을 수 있다
├─ badges.html           등급 뱃지 시스템 시안 (7단계)
├─ logo.html             로고 시스템
├─ marks.html            심볼 마크 비교안
├─ font.html             폰트 프리뷰
│
├─ src/
│  └─ styles.css         전체 스타일 (약 4,000줄)
│
├─ public/               여기 있는 건 그대로 서빙된다
│  ├─ js/app.js          앱 전체 로직 (약 4,200줄)
│  └─ assets/hi/*.jpg    상품 이미지 35장
│
├─ docs/
│  ├─ DEPLOY.md          GitHub → Vercel 연결 절차
│  └─ WORKFLOW.md        브랜치 · PR · 담당 구역
│
├─ vite.config.js        페이지 목록 · 빌드 설정
└─ vercel.json           배포 설정
```

### 왜 `app.js` 만 `public/` 안에 있나

앱 코드는 ES 모듈이 아니라 **전역 스코프에서 도는 클래식 스크립트**다.
모듈로 바꾸면 `var`·`function` 선언이 전역에서 사라져서 지금 동작이 깨진다.
`public/` 에 두면 Vite 가 건드리지 않고 그대로 내보내므로, 원본과 100% 같은 코드가 배포된다.

나중에 모듈로 쪼갤 때는 `src/` 로 옮기고 `<script type="module">` 로 바꾸면 된다. 그때 한 번에 하는 게 안전하다.

---

## 파일 나눠 쓰는 법

원래 430KB 짜리 HTML 한 장이었다. 둘이서 같은 파일을 만지면 깃 충돌이 계속 나서 셋으로 갈랐다:

- **마크업만 고칠 때** → `index.html`
- **색·간격·모션 CSS** → `src/styles.css`
- **동작·데이터·애니메이션 스크립트** → `public/js/app.js`

같은 화면을 둘이 동시에 만질 때도 한 명은 CSS, 한 명은 JS 로 나누면 충돌이 거의 안 난다.
자세한 담당 구역은 [docs/WORKFLOW.md](docs/WORKFLOW.md).

---

## 새 시안 페이지 추가

1. 루트에 `something.html` 을 만든다
2. `vite.config.js` 의 `input` 목록에 한 줄 추가

```js
something: page('something.html'),
```

이걸 빠뜨리면 로컬에선 보이는데 배포본에는 안 들어간다. 가장 흔한 실수.

---

## 외부 의존성

빌드에 포함되지 않고 CDN 에서 바로 불러온다. 오프라인에선 모션이 안 돈다.

- [anime.js 4.5.0](https://animejs.com) — 모든 동적 애니메이션
- [Lenis 1.3.26](https://lenis.darkroom.engineering) — 부드러운 스크롤
- Roboto Flex 600 (로고) · Space Grotesk (숫자) · Pretendard (본문)

## 디자인 기조

깔끔함 · 세련됨 · 고급짐. 모션은 섬세하게, 절제해서.
색은 `src/styles.css` 최상단 `:root` 에 모여 있다 — 코랄 `#ff6b4a`, 지면 `#f1efea`, 잉크 `#0a0a0a`.
