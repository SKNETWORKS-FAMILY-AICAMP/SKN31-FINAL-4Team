# -*- coding: utf-8 -*-
"""Google Ads API 리프레시 토큰 발급 도구

── ★ 2026-09-21 수정 ──────────────────────────────────────────
원래 이 파일은 CLIENT_ID · CLIENT_SECRET 을 **소스에 그대로 적어** 두고 있었다.
그 상태로 커밋하면 깃허브 푸시 보호(GH013)가 막아 준다 — 실제로 막혔다.
막히지 않는 저장소였다면 그대로 공개됐을 값이다.
키는 .env 한 곳에서만 읽는다. 레포 루트 .env 의 GOOGLE_ADS_* 를 쓴다.

사용법:
    # 레포 루트 .env 에 GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET 가 있어야 한다
    python get_google_token.py
    → 브라우저가 열리고, 동의하면 REFRESH_TOKEN 이 출력된다
    → 그 값을 .env 의 GOOGLE_ADS_REFRESH_TOKEN= 에 붙여넣는다
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))   # ★ insert(0) 금지
from sv_config.settings import GoogleKeywordConfig      # noqa: E402  (.env 로딩을 겸한다)

SCOPES = ["https://www.googleapis.com/auth/adwords"]

# 모양 검사용 — 값이 아니라 형식만 안다. 조각으로 둬야 비밀 스캐너가 오탐하지 않는다.
ID_SUFFIX = ".apps." + "googleusercontent.com"
SECRET_PREFIX = "GOC" + "SPX-"

CLIENT_ID = GoogleKeywordConfig.CLIENT_ID
CLIENT_SECRET = GoogleKeywordConfig.CLIENT_SECRET


def _check():
    """값이 없거나 서로 바뀌어 있으면 여기서 잡는다.

    팀원 메모에 '.env 에 값을 반대로 적었다'는 말이 있었다.
    추측으로 코드에서 뒤집지 말고, 모양을 보고 알려 준다 —
    client_id 는 googleusercontent 도메인으로 끝나고,
    client_secret 은 구글이 주는 고정 접두어로 시작한다.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("❌ .env 에 GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET 가 없습니다.\n"
                 "   (구글 '로그인'용 GOOGLE_CLIENT_ID 와 다른 값입니다 — 섞지 마세요.)")

    looks_swapped = (CLIENT_SECRET.endswith(ID_SUFFIX)
                     or CLIENT_ID.startswith(SECRET_PREFIX))
    if looks_swapped:
        sys.exit("❌ .env 의 GOOGLE_ADS_CLIENT_ID 와 GOOGLE_ADS_CLIENT_SECRET 가 서로 바뀐 것 같습니다.\n"
                 f"   client_id 는 '{ID_SUFFIX}' 로 끝나고,\n"
                 f"   client_secret 은 '{SECRET_PREFIX}' 로 시작해야 합니다. .env 를 고쳐 주세요.")

    if not CLIENT_ID.endswith(ID_SUFFIX):
        print(f"⚠️ GOOGLE_ADS_CLIENT_ID 가 '{ID_SUFFIX}' 로 끝나지 않습니다. 확인해 보세요.")


def main():
    _check()
    from google_auth_oauthlib.flow import InstalledAppFlow

    print("🚀 구글 리프레시 토큰 발급을 시작합니다...\n")
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    print("⏳ 인터넷 창이 열리면 구글 계정으로 로그인 후 권한을 허용해 주세요.")
    credentials = flow.run_local_server(port=0, prompt="consent")

    print("\n✅ 발급 성공!")
    print("=" * 60)
    print(f"📌 REFRESH_TOKEN: {credentials.refresh_token}")
    print("=" * 60)
    print("\n👉 위 문자열을 .env 의 GOOGLE_ADS_REFRESH_TOKEN= 우측에 붙여넣어 주세요.")
    print("   (터미널 기록에 남으니, 붙여넣은 뒤 스크롤백을 지우시는 걸 권합니다.)")


if __name__ == "__main__":
    main()
