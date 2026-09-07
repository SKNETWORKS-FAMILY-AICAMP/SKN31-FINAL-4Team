GRAPHQL_BASE_URL = "https://api.zigzag.kr/api/2/graphql"
SEARCH_RESULT_API_URL = f"{GRAPHQL_BASE_URL}/GetSearchResult"

ZIGZAG_BASE_URL = "https://zigzag.kr"
PRODUCT_BASE_URL = "https://store.zigzag.kr/app/catalog/products/{goods_id}"

REQUEST_TIMEOUT = 20

DEFAULT_PAGE_ID = "web_srp_clp_category"
DEFAULT_SORT = "200"
DEFAULT_LIMIT = 100

GOODS_CARD_TYPE = "UX_GOODS_CARD_ITEM"

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
