GRAPHQL_BASE_URL = "https://api.zigzag.kr/api/2/graphql"

SEARCH_RESULT_API_URL = f"{GRAPHQL_BASE_URL}/GetSearchResult"

ZIGZAG_BASE_URL = "https://zigzag.kr"

PRODUCT_BASE_URL = "https://store.zigzag.kr/app/catalog/products/{goods_id}"

REQUEST_TIMEOUT = 10

DEFAULT_PAGE_ID = "web_srp_clp_category"

# ui_item_list 안에서 실제 상품 카드를 나타내는 type 값
# (그 외에 UX_SEARCH_RESULT_HEADER, UX_CHECK_BUTTON_AND_SORTING,
#  UX_LINE_WITH_MARGIN 등 UI 전용 아이템이 섞여 있음)
GOODS_CARD_TYPE = "UX_GOODS_CARD_ITEM"

# HAR에서 캡처한 실제 쿼리는 filter_list 등 화면 렌더링용 필드까지
# 포함한 매우 긴 쿼리라, 수집에 필요한 필드만 남긴 최소 쿼리로 재구성.
# (실제 스키마와 어긋나는 필드가 있으면 GraphQL Playground/Insomnia로
#  한 번 재검증 필요 — 특히 managed_category_list, review 관련 필드)
SEARCH_RESULT_QUERY = """
query GetSearchResult($input: SearchResultInput!) {
  search_result(input: $input) {
    end_cursor
    has_next
    ui_item_list {
      __typename
      type
      ... on UxGoodsCardItem {
        goods_id
        catalog_product_id
        shop_id
        shop_name
        is_brand
        title
        product_url
        image_url
        price
        final_price
        discount_rate
        review_score
        display_review_count
        sellable_status
        is_ad
        managed_category_list {
          id
          value
          key
          depth
        }
      }
    }
  }
}
""".strip()
