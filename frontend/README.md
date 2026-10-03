# FEEDiT Frontend

Vite + Vanilla JavaScript 기반 사용자 화면과 Vercel 서버리스 API입니다. 기준일: 2026-10-04.

```bash
nvm use
npm ci
npm run dev
npm run build
npm test
```

| 위치 | 역할 |
| --- | --- |
| `index.html`, `main.js`, `main.css` | 화면·기능·스타일 진입점 |
| `core/`, `app_shell/`, `intro/` | 공통 모듈·라우팅·소개 화면 |
| `home/`, `trend/`, `style/`, `salmal/` | 대화·트렌드·스타일·살말 |
| `account/`, `pricing/` | 계정·프로필·알림·플랜 화면 |
| `api/` | Vercel 함수 |
| `tests/` | Node/jsdom 회귀 테스트 |
| `public/` | 공개 정적 자산 |

개발 서버는 5173이며 API·챗봇을 별도로 실행해야 합니다. 기능 폴더의 JS/CSS를 루트 진입점에서 조합하며 `src/` 중심 프레임워크 구조가 아닙니다.

[전체 실행](../docs/DEVELOPMENT.md) · [배포](../docs/DEPLOYMENT.md) · [기술 버전](../docs/TECHNOLOGY.md) · [작업 규칙](AGENTS.md) · [개발 로그](docs/DEVELOPLOG.md)
