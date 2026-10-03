/* 자동 생성된 진입점 — 각 app 모듈을 원본 코드의 등장 순서대로 불러온다.
   모듈 자체의 최상위 부수효과(이벤트 바인딩 등)는 import 시점에 실행되고,
   실제 화면 전환에 필요한 함수 호출(enterMain 안의 hotBuild(); trBuild(); ... 등)은
   각 함수가 정의된 app-shell/router.js 안에 원래 순서 그대로 남아 있다. */
import './core/static/js/dom.js';
import './intro/static/js/loader.js';
import './intro/static/js/deck.js';
import './intro/static/js/visuals.js';
import './app_shell/static/js/router.js';
import './app_shell/static/js/alpha.js';   /* 알파 테스트 모드 — 시연 15일 한정 */
import './app_shell/static/js/assistant_hub.js'; /* 전 페이지 도움말 허브 · 화면별 온보딩 */
import './home/static/js/chat.js';
import './home/static/js/chat_popup.js';
import './trend/static/js/nav_meta.js';
import './trend/static/js/data.js';
import './trend/static/js/chart_engine.js';
import './trend/static/js/count_up.js';
import './trend/static/js/weekly_report.js';
import './trend/static/js/report_export.js';   /* 리포트 엑셀 저장 · 링크 공유 */
import './trend/static/js/render_helpers.js';
import './trend/static/js/saved_keywords.js';
import './trend/static/js/dispatch.js';
import './trend/static/js/discount_resale.js';
import './account/static/js/rank.js';
import './trend/static/js/my_feed.js';
import './account/static/js/profile.js';
import './account/static/js/xp_track.js';   /* 경험치 — 접속 · 트렌드 분석 체류 기록 */
import './account/static/js/xp_panel.js';   /* 경험치 창 · 홈페이지 피드백 창 */
import './account/static/js/notify.js';
import './account/static/js/data_api.js';   /* 데이터 API 키 — 비즈니스 요금제 · 베타 이후에만 메뉴가 선다 */
import './app_shell/static/js/ticker.js';   /* 상단 실시간 공지 — 2026-10-02 */
import './style/static/js/search.js';
import './trend/static/js/assoc_popover.js';
import './salmal/static/js/nav_widget.js';
import './style/static/js/style_page.js';
import './pricing/static/js/pricing.js';
import './account/static/js/badges.js';
import './salmal/static/js/vote_app.js';
