# 배포 — GitHub → Vercel

목표: **푸시하면 자동으로 배포되고, PR 을 열면 그 브랜치 전용 미리보기 주소가 생긴다.**
한 번만 세팅하면 그다음부터는 아무것도 안 해도 된다.

---

## 1. 레포에 올리기 (최초 1회)

```bash
cd feedit-web
git init
git add .
git commit -m "chore: 프로젝트 초기 구성"
git branch -M main
git remote add origin https://github.com/<계정>/<레포>.git
git push -u origin main
```

> `node_modules/` 와 `dist/` 는 `.gitignore` 에 있으니 올라가지 않는다. 정상이다.
> 이미지 14MB 는 그대로 올라간다. 나중에 사진이 더 늘어나면 그때 CDN 으로 빼자.

## 2. 팀원 초대

GitHub 레포 → **Settings → Collaborators → Add people**
같이 작업하는 프론트 팀원은 Write 권한, 보기만 하는 팀원은 초대할 필요 없다 (Vercel 주소만 주면 된다).

## 3. Vercel 연결 (최초 1회)

1. [vercel.com](https://vercel.com) 에 **GitHub 계정으로** 로그인
2. **Add New… → Project**
3. 방금 만든 레포를 **Import**
4. 설정 화면에서 확인만 하고 넘어간다 — `vercel.json` 에 다 적혀 있어서 자동으로 잡힌다

   | 항목 | 값 |
   | --- | --- |
   | Framework Preset | Vite |
   | Build Command | `npm run build` |
   | Output Directory | `dist` |
   | Install Command | `npm install` |

5. **Deploy**

1~2분 뒤 `https://<프로젝트이름>.vercel.app` 이 나온다. 이 주소를 팀에 공유하면 된다.

## 4. 이후엔 자동

| 상황 | 결과 |
| --- | --- |
| `main` 에 푸시 | 운영 주소가 자동으로 갱신된다 |
| 다른 브랜치에 푸시 | 그 브랜치 전용 **Preview 주소**가 생긴다 |
| PR 을 연다 | PR 코멘트에 Vercel 봇이 미리보기 링크를 자동으로 달아 준다 |
| 빌드 실패 | 배포가 안 되고 기존 화면이 그대로 유지된다. PR 에 실패 표시가 뜬다 |

**팀원에게 시안을 보여줄 땐 main 에 바로 밀지 말고 브랜치를 파서 Preview 링크를 주는 게 낫다.**
확정되면 그때 머지한다.

---

## 페이지별 주소

| 페이지 | 경로 |
| --- | --- |
| 메인 목업 | `/` |
| 등급 뱃지 시안 | `/badges` |
| 로고 시스템 | `/logo` |
| 심볼 마크 비교 | `/marks` |
| 폰트 프리뷰 | `/font` |

`vercel.json` 에 `cleanUrls: true` 를 켜 둬서 `.html` 을 붙이지 않아도 열린다.

---

## 배포 전 자가 점검

```bash
npm run build     # 에러 없이 끝나는지
npm run preview   # 빌드된 결과물이 실제로 잘 뜨는지 (localhost:4173)
```

로컬 `npm run dev` 는 되는데 배포본이 깨지는 경우는 거의 항상 둘 중 하나다:

1. 새 HTML 페이지를 `vite.config.js` 의 `input` 목록에 안 넣었다
2. 이미지 경로를 `public/` 밖에서 참조했다 (이미지는 반드시 `public/assets/` 아래)

## 롤백

Vercel 대시보드 → **Deployments** → 되돌리고 싶은 배포 → **⋯ → Promote to Production**.
깃을 건드리지 않고 즉시 이전 버전으로 돌아간다.
