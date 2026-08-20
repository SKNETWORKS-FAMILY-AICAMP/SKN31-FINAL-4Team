"""Seed data and API-specific audience settings for NAVER collection."""

from apps.naver.models import Audience, TrendKeyword

KEYWORDS: dict[str, list[str]] = {
    TrendKeyword.Category.STYLE: ["발레코어", "고프코어", "블록코어", "포엣코어", "놈코어", "비즈니스코어", "포멀캐주얼", "애슬레저", "스트릿", "아메카지", "페미닌", "그런지", "클래식", "미니멀", "캐주얼", "빈티지", "Y2K", "프레피", "올드머니", "시티보이", "워크웨어", "스포티", "걸리시"],
    TrendKeyword.Category.COLOR: ["블랙", "화이트", "아이보리", "베이지", "브라운", "카키", "그레이", "네이비", "블루", "스카이블루", "핑크", "레드", "버건디", "그린", "옐로우", "퍼플", "실버", "파스텔"],
    TrendKeyword.Category.FIT: ["오버핏", "세미오버핏", "슬림핏", "레귤러핏", "루즈핏", "와이드핏", "스트레이트핏", "부츠컷", "플레어핏", "크롭핏", "하이웨스트", "로우라이즈", "A라인", "H라인"],
    TrendKeyword.Category.TPO: ["데일리룩", "출근룩", "오피스룩", "하객룩", "데이트룩", "소개팅룩", "여행룩", "공항패션", "캠퍼스룩", "대학생코디", "페스티벌룩", "휴가룩"],
    TrendKeyword.Category.SEASON: ["봄코디", "봄패션", "여름코디", "여름패션", "가을코디", "가을패션", "겨울코디", "겨울패션", "간절기코디", "장마룩"],
    TrendKeyword.Category.OUTER: ["자켓", "블레이저", "가디건", "코트", "트렌치코트", "패딩", "숏패딩", "바람막이", "레더자켓", "데님자켓", "후드집업", "플리스"],
    TrendKeyword.Category.DRESS_SET: ["원피스", "미니원피스", "롱원피스", "셔츠원피스", "니트원피스", "슬립원피스", "셋업", "투피스", "수트", "정장"],
    TrendKeyword.Category.BOTTOM: ["팬츠", "데님", "청바지", "와이드팬츠", "슬랙스", "카고팬츠", "조거팬츠", "숏팬츠", "버뮤다팬츠", "스커트", "미니스커트", "롱스커트", "플리츠스커트"],
    TrendKeyword.Category.TOP: ["티셔츠", "반팔", "긴팔", "셔츠", "블라우스", "니트", "스웨터", "맨투맨", "후드티", "슬리브리스", "크롭탑", "폴로셔츠"],
}

ALIASES = {
    "발레코어": ["발레 코어", "balletcore", "ballet core"],
    "고프코어": ["고프 코어", "gorpcore", "gorp core"],
    "와이드팬츠": ["와이드 팬츠", "와이드바지", "와이드 바지"],
}

# API responses use different age-code systems. 10대 Search Trend is 13-18;
# Shopping Insight's 10대 is 10-19, as defined by NAVER.
AUDIENCE_FILTERS = {
    Audience.TEENS: {"search_ages": ["2"], "shopping_ages": ["10"]},
    Audience.TWENTIES: {"search_ages": ["3", "4"], "shopping_ages": ["20"]},
    Audience.THIRTIES: {"search_ages": ["5", "6"], "shopping_ages": ["30"]},
}

# NAVER Shopping's top-level fashion-apparel category. Keep this explicit so
# product-category detail mappings can be added without changing collectors.
SHOPPING_CATEGORY_CODE = "50000000"
SHOPPING_CATEGORIES = {
    TrendKeyword.Category.OUTER,
    TrendKeyword.Category.DRESS_SET,
    TrendKeyword.Category.BOTTOM,
    TrendKeyword.Category.TOP,
    TrendKeyword.Category.STYLE,
    TrendKeyword.Category.FIT,
}
