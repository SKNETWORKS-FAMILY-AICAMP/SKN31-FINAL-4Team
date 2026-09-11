from __future__ import annotations

ZIGZAG_BASE_URL = "https://zigzag.kr"
SEARCH_RESULT_API_URL = "https://api.zigzag.kr/api/2/graphql/GetSearchResult"
SHOP_COMPONENT_API_URL = "https://api.zigzag.kr/api/2/graphql/GetComponentList"
PRODUCT_BASE_URL = "https://store.zigzag.kr/app/catalog/products/{goods_id}?browsing_type=NATIVE_BROWSER"

DEFAULT_PAGE_ID = "web_srp_clp_category"
DEFAULT_SORT = "200"
DEFAULT_LIMIT = 100
REQUEST_TIMEOUT = 20
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
        managed_category_list { id value key depth }
      }
    }
  }
}
""".strip()

SHOP_COMPONENT_QUERY = r"""
fragment ShopUxProductCardItem on ShopUxProductCardItem {
  product {
    shop_product_no
    catalog_product_id
    shop_id
    url
    image_url
    name
    price
    discount_rate
  }
  shop_name
  final_price
  ranking
  review_count
  review_score
  fomo { text }
  managed_category_list { id category_id value depth key }
}

query GetComponentList(
  $shop_id: ID!
  $category_id: ID
  $after_id: ID
  $sorting_item_id: ID
  $check_button_item_ids: [ID]
  $sub_filter_id_list: [ID]
) {
  shop_ux_component_list(
    shop_id: $shop_id
    category_id: $category_id
    after_id: $after_id
    sorting_item_id: $sorting_item_id
    check_button_item_ids: $check_button_item_ids
    sub_filter_id_list: $sub_filter_id_list
  ) {
    after_id
    has_next_page
    category_list { id name }
    item_list {
      type
      ... on ShopUxProductCarousel { component_list { ...ShopUxProductCardItem } }
      ... on ShopUxProductGroup { product_carousel { component_list { ...ShopUxProductCardItem } } }
      ... on ShopUxBestProductCarousel { category_group_list { item_list { ...ShopUxProductCardItem } } }
      ...ShopUxProductCardItem
    }
  }
}
""".strip()
