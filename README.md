# SKN31-FINAL-4Team
# 팀명




## 🔥깃 협업 규칙!!!⚠️
깃 충돌을 막고자 규칙을 좀 정하고자 합니다.   
**팀원별 Branch + Commit + Pull Request(PR)** 방식

### 1. 전체적인 깃 구조
main은 최종적으로 안정된 코드만 모이는 곳  
각자 자기 브런치에서 작업 진행 후 커밋 > 푸쉬 > **PR**   
**PR:** 내 작업을 main에 합쳐달라고 요청  -> 승인 후 merge  
즉 각자 자신의 Branch를 만들어 작업하기!   
**예시 :** 
```text
main
 │
 ├── dev/봉남
 ├── dev/진영
 ├── dev/현아
 ├── dev/서연
 └── dev/혁진
```
#### 🚩2. 세팅법.
처음 프로젝트 받는 경우 
```bash
git clone <GitHub Repository 주소>
cd <프로젝트 폴더>
```
클론하고 자기 Branch 생성하기
```bash
git checkout -b dev/봉남
```
나중에 푸쉬할 때
```Bash
git push -u origin dev/봉남
```

#### 개별 작업 흐름 
**① 작업 시작하기 전에 main 최신 코드 확인!**
```bash
git checkout main
git pull origin main
```
**② 내 Branch로 돌아오기**
```bash
git checkout dev/내이름
```
**③ 최신 main의 변경사항을 자신의 Branch에 반영하기**
```bash
git merge main
```
**④ 자기 브런치에서 개발 후 커밋**  
커밋 메세지 규칙 : [기능타입] <변경내용 구체적 & 한줄로>
```bash
git add .
git commit -m "기능: 트렌드 분석 API 구현"
```
**⑤ 자기 브런치에 Push**
```bash
git push origin dev/봉
```
**⑥ Pull Request 생성**
자기 브런치를 푸쉬하면 깃헙에 **Compare & pull request** 나타남. > 클릭해서 PR생성
> 내가 작업한 내용을 확인하고 main에 합쳐주세요 > 확인 후 머지

#### 간단 정리 
- 🌳 Branch = 내 작업 공간
- 💾 Commit = 작업 기록
- ☁️ Push = GitHub에 올리기
- 📩 PR = main에 합쳐달라고 요청
- 👀 Review = 팀원이 코드 확인
- 🔀 Merge = main에 합치기
- 📥 Pull = 최신 코드 가져오기
