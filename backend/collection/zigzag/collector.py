from __future__ import annotations

import random
import time
from typing import Any

import requests

from .config import (
    CNV_ENDPOINT,
    DEFAULT_MAX_DELAY,
    DEFAULT_MIN_DELAY,
)
from .query import GET_CNV_PAGE_ACTION_QUERY


# Exact GetCnvPage document captured from Zigzag web traffic.
GET_CNV_PAGE_QUERY = 'query GetCnvPage($input: CnvPageInput!) {\n  result: cnv_page(input: $input) {\n    ...CnvPageResult\n    __typename\n  }\n}\n\nfragment CnvPageResult on CnvPageResult {\n  layout_id\n  module_spec_list {\n    ...CnvModuleSpec\n    __typename\n  }\n  top_nav_module_spec {\n    ...CnvModuleSpec\n    __typename\n  }\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  __typename\n}\n\nfragment CnvModuleSpec on CnvModuleSpec {\n  meta {\n    ...CnvModuleSpecMeta\n    __typename\n  }\n  body {\n    type\n    ...CnvProductCardModuleSpecBody\n    ...CnvBrandShowcaseModuleSpecBody\n    ...CnvSohoShowcaseModuleSpecBody\n    ...CnvBasicItemCarouselModuleSpecBody\n    ...CnvChipQuickMenuModuleSpecBody\n    ...CnvMainBannerModuleSpecBody\n    ...CnvProductCarouselGroupModuleSpecBody\n    ...CnvRecommendProductCarouselGroupModuleSpecBody\n    ...CnvCategoryChipTabModuleSpecBody\n    ...CnvCategoryTabModuleSpecBody\n    ...CnvSearchResultFilterModuleSpecBody\n    ...CnvSelectedFilterModuleSpecBody\n    ...CnvFilterModuleSpecBody\n    ...CnvContentHeaderModuleSpecBody\n    ...CnvSingleBannerModuleSpecBody\n    ...CnvCarouselBannerModuleSpecBody\n    ...CnvShortFormModuleSpecBody\n    ...CnvCatalogImageModuleSpecBody\n    ...CnvRecommendStoreGroupModuleSpecBody\n    ...CnvPromotionTcModuleSpecBody\n    ...CnvLineWithMarginModuleSpecBody\n    ...CnvBrandTimeDealModuleSpecBody\n    ...CnvCatalogCarouselImageVerticalGroupModuleSpecBody\n    ...CnvSkeletonModuleSpecBody\n    ...CnvAdBannerCardModuleSpecBody\n    ...CnvHighlightBannerModuleSpecBody\n    ...CnvTopNavigationModuleSpecBody\n    ...CnvToolBarModuleSpecBody\n    ...CnvButtonContainerModuleSpecBody\n    ...CnvEmptyViewModuleSpecBody\n    __typename\n  }\n  __typename\n}\n\nfragment CnvModuleSpecMeta on CnvModuleSpecMeta {\n  module_slot_id\n  module_id\n  module_spec_id\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  share_log {\n    ...CnvShareLog\n    __typename\n  }\n  __typename\n}\n\nfragment CnvAction on CnvAction {\n  type\n  trigger_type\n  target {\n    ...CnvActionTarget\n    __typename\n  }\n  option {\n    type\n    server_option\n    ...CnvDeepLinkActionOption\n    ...CnvModuleRefetchActionOption\n    ...CnvSearchFilterChangeActionOption\n    __typename\n  }\n  __typename\n}\n\nfragment CnvActionTarget on CnvActionTarget {\n  module_slot_id\n  module_id_list\n  __typename\n}\n\nfragment CnvDeepLinkActionOption on CnvDeepLinkActionOption {\n  landing_url\n  __typename\n}\n\nfragment CnvModuleRefetchActionOption on CnvModuleRefetchActionOption {\n  delay\n  __typename\n}\n\nfragment CnvSearchFilterChangeActionOption on CnvSearchFilterChangeActionOption {\n  search_query_state {\n    ...CnvSearchQueryState\n    __typename\n  }\n  base_search_query_state {\n    ...CnvSearchQueryState\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSearchQueryState on CnvSearchQueryState {\n  filter_list {\n    filter_type\n    value_list\n    __typename\n  }\n  order\n  __typename\n}\n\nfragment CnvUbl on CnvUbl {\n  object {\n    ...CnvUblObject\n    __typename\n  }\n  server_log\n  __typename\n}\n\nfragment CnvUblObject on CnvUblObject {\n  id\n  idx\n  section\n  type\n  url\n  __typename\n}\n\nfragment CnvShareLog on CnvShareLog {\n  server_log\n  __typename\n}\n\nfragment CnvProductCardModuleSpecBody on CnvProductCardModuleSpecBody {\n  product_card {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCardBlockSpec on CnvProductCardBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  product_card {\n    ...CnvProductCard\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCard on CnvProductCard {\n  product_id\n  product {\n    ...CnvProductCardProduct\n    __typename\n  }\n  price {\n    ...CnvProductCardPrice\n    __typename\n  }\n  review {\n    ...CnvProductCardReview\n    __typename\n  }\n  badge {\n    ...CnvProductCardBadge\n    __typename\n  }\n  shop {\n    ...CnvProductCardShop\n    __typename\n  }\n  shipping {\n    ...CnvProductCardShipping\n    __typename\n  }\n  engagement {\n    ...CnvProductCardEngagement\n    __typename\n  }\n  meta {\n    ...CnvProductCardMeta\n    __typename\n  }\n  tracking {\n    ...CnvProductCardTracking\n    __typename\n  }\n  ui_policy {\n    ...CnvProductCardUiPolicy\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCardProduct on CnvProductCardProduct {\n  title\n  image {\n    ...CnvImage\n    __typename\n  }\n  color_option_list {\n    ...CnvColorChip\n    __typename\n  }\n  __typename\n}\n\nfragment CnvImage on CnvImage {\n  normal\n  dark\n  size {\n    ...CnvImageSize\n    __typename\n  }\n  __typename\n}\n\nfragment CnvImageSize on CnvImageSize {\n  width\n  height\n  ratio\n  __typename\n}\n\nfragment CnvColorChip on CnvColorChip {\n  color {\n    ...CnvColor\n    __typename\n  }\n  border_color {\n    ...CnvColor\n    __typename\n  }\n  __typename\n}\n\nfragment CnvColor on CnvColor {\n  hex {\n    ...CnvHexColor\n    __typename\n  }\n  token {\n    ...CnvTokenColor\n    __typename\n  }\n  __typename\n}\n\nfragment CnvHexColor on CnvHexColor {\n  normal\n  dark\n  __typename\n}\n\nfragment CnvTokenColor on CnvTokenColor {\n  key\n  __typename\n}\n\nfragment CnvProductCardPrice on CnvProductCardPrice {\n  final_price\n  final_price_discount_rate\n  max_price\n  final_price_suffix\n  __typename\n}\n\nfragment CnvProductCardReview on CnvProductCardReview {\n  count\n  score\n  __typename\n}\n\nfragment CnvProductCardBadge on CnvProductCardBadge {\n  plp_badge_list {\n    ...CnvBadge\n    __typename\n  }\n  metadata_emblem_badge_list {\n    ...CnvBadge\n    __typename\n  }\n  thumbnail_nudge_badge_list {\n    ...CnvBadge\n    __typename\n  }\n  thumbnail_emblem_badge_list {\n    ...CnvBadge\n    __typename\n  }\n  brand_name_badge_list {\n    ...CnvBadge\n    __typename\n  }\n  __typename\n}\n\nfragment CnvBadge on CnvBadge {\n  image {\n    ...CnvImage\n    __typename\n  }\n  small_image {\n    ...CnvImage\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  type\n  style\n  background_color {\n    ...CnvColor\n    __typename\n  }\n  __typename\n}\n\nfragment CnvText on CnvText {\n  color {\n    ...CnvColor\n    __typename\n  }\n  html {\n    ...CnvHtmlText\n    __typename\n  }\n  text\n  __typename\n}\n\nfragment CnvHtmlText on CnvHtmlText {\n  normal\n  dark\n  __typename\n}\n\nfragment CnvProductCardShop on CnvProductCardShop {\n  name\n  __typename\n}\n\nfragment CnvProductCardShipping on CnvProductCardShipping {\n  arrival_text {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCardEngagement on CnvProductCardEngagement {\n  is_saved_product\n  fomo {\n    ...CnvProductCardFomo\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCardFomo on CnvProductCardFomo {\n  fomo_text\n  icon_image {\n    ...CnvImage\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCardMeta on CnvProductCardMeta {\n  shop {\n    ...CnvProductCardMetaShop\n    __typename\n  }\n  state {\n    ...CnvProductCardState\n    __typename\n  }\n  __typename\n}\n\nfragment CnvProductCardMetaShop on CnvProductCardMetaShop {\n  shop_id\n  status\n  delete_action\n  __typename\n}\n\nfragment CnvProductCardState on CnvProductCardState {\n  sales_status\n  shipping_type\n  __typename\n}\n\nfragment CnvProductCardTracking on CnvProductCardTracking {\n  performance_measurement\n  __typename\n}\n\nfragment CnvProductCardUiPolicy on CnvProductCardUiPolicy {\n  column_count\n  card_item_style\n  title_line_number\n  image_ratio\n  is_enabled_not_my_tasty\n  __typename\n}\n\nfragment CnvBrandShowcaseModuleSpecBody on CnvBrandShowcaseModuleSpecBody {\n  main_image {\n    ...CnvImageBlockSpec\n    __typename\n  }\n  brand_item_list: item_list {\n    ...CnvBrandShowcaseItemBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvImageBlockSpec on CnvImageBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  __typename\n}\n\nfragment CnvBrandShowcaseItemBlockSpec on CnvBrandShowcaseItemBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  product_id\n  __typename\n}\n\nfragment CnvSohoShowcaseModuleSpecBody on CnvSohoShowcaseModuleSpecBody {\n  showcase_thumbnail {\n    type\n    action_list {\n      ...CnvAction\n      __typename\n    }\n    ubl {\n      ...CnvUbl\n      __typename\n    }\n    image {\n      ...CnvImage\n      __typename\n    }\n    __typename\n  }\n  title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  sub_text {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  store_info {\n    ...CnvSohoShowCaseShopBlockSpec\n    __typename\n  }\n  soho_item_list: item_list {\n    ...CnvSohoShowCaseItemBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvTitleBlockSpec on CnvTitleBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSohoShowCaseShopBlockSpec on CnvSohoShowCaseShopBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  name {\n    ...CnvText\n    __typename\n  }\n  icon {\n    ...CnvImage\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSohoShowCaseItemBlockSpec on CnvSohoShowCaseItemBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  product_id\n  __typename\n}\n\nfragment CnvBasicItemCarouselModuleSpecBody on CnvBasicItemCarouselModuleSpecBody {\n  header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  item_list {\n    ...CnvBasicItemCarouselItemBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvHeaderBlockSpec on CnvHeaderBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  ... on CnvContentHeaderBlockSpec {\n    title {\n      ...CnvText\n      __typename\n    }\n    title_icon {\n      ...CnvIconBlockSpec\n      __typename\n    }\n    icon_button {\n      ...CnvIconBlockSpec\n      __typename\n    }\n    text_button {\n      ...CnvButtonBlockSpec\n      __typename\n    }\n    is_ad_visible\n    sub_title {\n      ...CnvText\n      __typename\n    }\n    __typename\n  }\n  ... on CnvDoubleLinedContentHeaderBlockSpec {\n    title {\n      ...CnvText\n      __typename\n    }\n    title2 {\n      ...CnvText\n      __typename\n    }\n    text_button {\n      ...CnvButtonBlockSpec\n      __typename\n    }\n    icon_button {\n      ...CnvIconBlockSpec\n      __typename\n    }\n    thumbnail_image {\n      ...CnvImageBlockSpec\n      __typename\n    }\n    is_ad_visible\n    __typename\n  }\n  __typename\n}\n\nfragment CnvIconBlockSpec on CnvIconBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  position\n  token\n  tooltip\n  __typename\n}\n\nfragment CnvButtonBlockSpec on CnvButtonBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  position\n  token_icon {\n    ...CnvIconToken\n    __typename\n  }\n  background_color {\n    ...CnvColor\n    __typename\n  }\n  __typename\n}\n\nfragment CnvIconToken on CnvIconToken {\n  key\n  tint_color {\n    ...CnvColor\n    __typename\n  }\n  __typename\n}\n\nfragment CnvBasicItemCarouselItemBlockSpec on CnvBasicItemCarouselItemBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  main_title {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvChipQuickMenuModuleSpecBody on CnvChipQuickMenuModuleSpecBody {\n  bottom_menu_list {\n    ...CnvChipQuickMenuBlockSpec\n    __typename\n  }\n  is_animated\n  top_menu_list {\n    ...CnvChipQuickMenuBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvChipQuickMenuBlockSpec on CnvChipQuickMenuBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  dot_notification {\n    ...CnvOneOffNotification\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  quick_menu_id\n  title {\n    ...CnvText\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  __typename\n}\n\nfragment CnvOneOffNotification on CnvOneOffNotification {\n  id\n  tooltip\n  __typename\n}\n\nfragment CnvMainBannerModuleSpecBody on CnvMainBannerModuleSpecBody {\n  banner_list {\n    ...CnvMainBannerBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvMainBannerBlockSpec on CnvMainBannerBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  title {\n    ...CnvText\n    __typename\n  }\n  title_2 {\n    ...CnvText\n    __typename\n  }\n  sub_title {\n    ...CnvText\n    __typename\n  }\n  video {\n    ...CnvVideo\n    __typename\n  }\n  __typename\n}\n\nfragment CnvVideo on CnvVideo {\n  url\n  thumbnail_image {\n    ...CnvImage\n    __typename\n  }\n  is_sound_enabled\n  __typename\n}\n\nfragment CnvProductCarouselGroupModuleSpecBody on CnvProductCarouselGroupModuleSpecBody {\n  pcg_header: header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  column_count\n  product_card_list {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  background_color {\n    ...CnvColor\n    __typename\n  }\n  __typename\n}\n\nfragment CnvRecommendProductCarouselGroupModuleSpecBody on CnvRecommendProductCarouselGroupModuleSpecBody {\n  rpcg_header: header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  product_card_list {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  column_count\n  __typename\n}\n\nfragment CnvCategoryChipTabModuleSpecBody on CnvCategoryChipTabModuleSpecBody {\n  chip_list {\n    ...CnvChipBlockSpec\n    __typename\n  }\n  is_sticky\n  type\n  __typename\n}\n\nfragment CnvChipBlockSpec on CnvChipBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  selected_text {\n    ...CnvText\n    __typename\n  }\n  text_2 {\n    ...CnvText\n    __typename\n  }\n  image_icon {\n    ...CnvImage\n    __typename\n  }\n  color_chip {\n    ...CnvColorChip\n    __typename\n  }\n  icon {\n    ...CnvIconToken\n    __typename\n  }\n  is_selected\n  __typename\n}\n\nfragment CnvCategoryTabModuleSpecBody on CnvCategoryTabModuleSpecBody {\n  depth_list {\n    ...CnvCategoryTabDepth\n    __typename\n  }\n  is_sticky\n  type\n  more_button {\n    ...CnvToggleIconBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvCategoryTabDepth on CnvCategoryTabDepth {\n  item_list {\n    ...CnvCategoryItemBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvCategoryItemBlockSpec on CnvCategoryItemBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  selected_text {\n    ...CnvText\n    __typename\n  }\n  is_selected\n  __typename\n}\n\nfragment CnvToggleIconBlockSpec on CnvToggleIconBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  item_list {\n    icon {\n      ...CnvIconToken\n      __typename\n    }\n    key\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSearchResultFilterModuleSpecBody on CnvSearchResultFilterModuleSpecBody {\n  type\n  filter_chip_list {\n    ...CnvChipBlockSpec\n    __typename\n  }\n  filter_detail_button {\n    ...CnvNotiIconButtonBlockSpec\n    __typename\n  }\n  reset_button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  is_sticky\n  __typename\n}\n\nfragment CnvNotiIconButtonBlockSpec on CnvNotiIconButtonBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  icon {\n    ...CnvIconToken\n    __typename\n  }\n  noti_badge_text {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSelectedFilterModuleSpecBody on CnvSelectedFilterModuleSpecBody {\n  type\n  chip_list {\n    ...CnvChipBlockSpec\n    __typename\n  }\n  is_sticky\n  __typename\n}\n\nfragment CnvFilterModuleSpecBody on CnvFilterModuleSpecBody {\n  type\n  title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  is_open\n  notification_dot_color {\n    ...CnvColor\n    __typename\n  }\n  filter_item {\n    ... on CnvFilterItemChipBlockSpec {\n      ...CnvFilterItemChipBlockSpec\n      __typename\n    }\n    ... on CnvFilterItemChipGroupBlockSpec {\n      ...CnvFilterItemChipGroupBlockSpec\n      __typename\n    }\n    ... on CnvFilterItemSearchBlockSpec {\n      ...CnvFilterItemSearchBlockSpec\n      __typename\n    }\n    ... on CnvFilterItemSliderBlockSpec {\n      ...CnvFilterItemSliderBlockSpec\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CnvFilterItemChipBlockSpec on CnvFilterItemChipBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  chip_list {\n    ...CnvChipBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvFilterItemChipGroupBlockSpec on CnvFilterItemChipGroupBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  chip_group_list {\n    title {\n      ...CnvText\n      __typename\n    }\n    chip_list {\n      ...CnvChipBlockSpec\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CnvFilterItemSearchBlockSpec on CnvFilterItemSearchBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  title {\n    ...CnvText\n    __typename\n  }\n  empty_description\n  max_row\n  search_input {\n    ...CnvFilterItemSearchInputBlockSpec\n    __typename\n  }\n  chip_list {\n    ...CnvChipBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvFilterItemSearchInputBlockSpec on CnvFilterItemSearchInputBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  placeholder\n  keyword\n  __typename\n}\n\nfragment CnvFilterItemSliderBlockSpec on CnvFilterItemSliderBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  min\n  max\n  current_min\n  current_max\n  interval\n  decimal\n  unit {\n    is_prefix\n    unit\n    __typename\n  }\n  replace_text {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvContentHeaderModuleSpecBody on CnvContentHeaderModuleSpecBody {\n  header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvSingleBannerModuleSpecBody on CnvSingleBannerModuleSpecBody {\n  single_banner {\n    ...CnvSingleBannerBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvSingleBannerBlockSpec on CnvSingleBannerBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  title {\n    ...CnvText\n    __typename\n  }\n  title_2 {\n    ...CnvText\n    __typename\n  }\n  sub_title {\n    ...CnvText\n    __typename\n  }\n  background_color {\n    ...CnvColor\n    __typename\n  }\n  is_ad\n  __typename\n}\n\nfragment CnvCarouselBannerModuleSpecBody on CnvCarouselBannerModuleSpecBody {\n  carousel_banner_list: banner_list {\n    ...CnvSingleBannerBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvShortFormModuleSpecBody on CnvShortFormModuleSpecBody {\n  header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  short_form_item_list: item_list {\n    ...CnvShortformItemBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvShortformItemBlockSpec on CnvShortformItemBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  product_card_list {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  video {\n    ...CnvVideo\n    __typename\n  }\n  __typename\n}\n\nfragment CnvCatalogImageModuleSpecBody on CnvCatalogImageModuleSpecBody {\n  banner_image {\n    ...CnvImageBlockSpec\n    __typename\n  }\n  banner_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  banner_sub_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  product_card_list {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvRecommendStoreGroupModuleSpecBody on CnvRecommendStoreGroupModuleSpecBody {\n  header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  shop_list {\n    ...CnvRecommendStoreBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvRecommendStoreBlockSpec on CnvRecommendStoreBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  bottom_button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  bottom_title {\n    ...CnvText\n    __typename\n  }\n  product_image_list {\n    ...CnvImageBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvPromotionTcModuleSpecBody on CnvPromotionTcModuleSpecBody {\n  header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  promotion_tc_banner_list: banner_list {\n    ...CnvPromotionTcBannerBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvPromotionTcBannerBlockSpec on CnvPromotionTcBannerBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  banner_type\n  image {\n    ...CnvImage\n    __typename\n  }\n  image_title {\n    ...CnvImage\n    __typename\n  }\n  title1 {\n    ...CnvText\n    __typename\n  }\n  title2 {\n    ...CnvText\n    __typename\n  }\n  sub_title {\n    ...CnvText\n    __typename\n  }\n  button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvLineWithMarginModuleSpecBody on CnvLineWithMarginModuleSpecBody {\n  line_margin {\n    ...CnvLineMarginBlockSpec\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvLineMarginBlockSpec on CnvLineMarginBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  color {\n    ...CnvColor\n    __typename\n  }\n  height\n  divider {\n    ...CnvDivider\n    __typename\n  }\n  __typename\n}\n\nfragment CnvDivider on CnvDivider {\n  color {\n    ...CnvColor\n    __typename\n  }\n  height\n  margin {\n    ...CnvMargin\n    __typename\n  }\n  __typename\n}\n\nfragment CnvMargin on CnvMargin {\n  top\n  left\n  right\n  __typename\n}\n\nfragment CnvBrandTimeDealModuleSpecBody on CnvBrandTimeDealModuleSpecBody {\n  title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  sub_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  schedule {\n    ...CnvSchedule\n    __typename\n  }\n  pre_open_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  pre_open_description {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  brand_banner {\n    ...CnvBrandTimeDealBrandBannerBlockSpec\n    __typename\n  }\n  product_card_list {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSchedule on CnvSchedule {\n  date_started\n  date_ended\n  __typename\n}\n\nfragment CnvBrandTimeDealBrandBannerBlockSpec on CnvBrandTimeDealBrandBannerBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  icon_image {\n    ...CnvImageBlockSpec\n    __typename\n  }\n  title {\n    ...CnvText\n    __typename\n  }\n  shop_name {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvCatalogCarouselImageVerticalGroupModuleSpecBody on CnvCatalogCarouselImageVerticalGroupModuleSpecBody {\n  header {\n    ...CnvHeaderBlockSpec\n    __typename\n  }\n  catalog_carousel_image_vertical_group_list {\n    ...CnvCatalogCarouselImageVerticalGroupBlockSpecBody\n    __typename\n  }\n  type\n  __typename\n}\n\nfragment CnvCatalogCarouselImageVerticalGroupBlockSpecBody on CnvCatalogCarouselImageVerticalGroupBlockSpecBody {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  banner_image {\n    ...CnvImageBlockSpec\n    __typename\n  }\n  banner_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  banner_title_2 {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  banner_sub_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  coupon_badge_title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  product_card_list {\n    ...CnvProductCardBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvSkeletonModuleSpecBody on CnvSkeletonModuleSpecBody {\n  target_module_type\n  type\n  __typename\n}\n\nfragment CnvAdBannerCardModuleSpecBody on CnvAdBannerCardModuleSpecBody {\n  type\n  banner_card {\n    ...CnvAdBannerCardBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvAdBannerCardBlockSpec on CnvAdBannerCardBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  image {\n    ...CnvImage\n    __typename\n  }\n  title {\n    ...CnvText\n    __typename\n  }\n  title_2 {\n    ...CnvText\n    __typename\n  }\n  sub_title {\n    ...CnvText\n    __typename\n  }\n  background_color {\n    ...CnvColor\n    __typename\n  }\n  more_button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  column_count\n  __typename\n}\n\nfragment CnvHighlightBannerModuleSpecBody on CnvHighlightBannerModuleSpecBody {\n  type\n  banner {\n    ...CnvHighlightBannerBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvHighlightBannerBlockSpec on CnvHighlightBannerBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  arrow_icon {\n    ...CnvImage\n    __typename\n  }\n  background_color {\n    ...CnvColor\n    __typename\n  }\n  left_image {\n    ...CnvImage\n    __typename\n  }\n  right_image {\n    ...CnvImage\n    __typename\n  }\n  title {\n    ...CnvText\n    __typename\n  }\n  __typename\n}\n\nfragment CnvTopNavigationModuleSpecBody on CnvTopNavigationModuleSpecBody {\n  type\n  top_navigation {\n    type\n    ...CnvTopNavigationTitleBlockSpec\n    ...CnvTopNavigationDropdownBlockSpec\n    __typename\n  }\n  menu_list {\n    ...CnvTopNavigationMenuBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvTopNavigationTitleBlockSpec on CnvTopNavigationTitleBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  __typename\n}\n\nfragment CnvTopNavigationDropdownBlockSpec on CnvTopNavigationDropdownBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  option_list {\n    ...CnvCategoryItemBlockSpec\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  __typename\n}\n\nfragment CnvTopNavigationMenuBlockSpec on CnvTopNavigationMenuBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  menu_key\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  __typename\n}\n\nfragment CnvToolBarModuleSpecBody on CnvToolBarModuleSpecBody {\n  toolbar {\n    ...CnvToolBarBlockSpec\n    __typename\n  }\n  is_sticky\n  type\n  __typename\n}\n\nfragment CnvToolBarBlockSpec on CnvToolBarBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  ... on CnvTextToolBarBlockSpec {\n    text {\n      ...CnvText\n      __typename\n    }\n    text_icon {\n      ...CnvIconBlockSpec\n      __typename\n    }\n    bottom_sheet_item_list_1 {\n      ...CnvOptionItemBlockSpec\n      __typename\n    }\n    bottom_sheet_item_list_2 {\n      ...CnvOptionItemBlockSpec\n      __typename\n    }\n    view_icon {\n      ...CnvToggleIconBlockSpec\n      __typename\n    }\n    __typename\n  }\n  ... on CnvCheckboxToolBarBlockSpec {\n    checkbox_list {\n      ...CnvCheckboxBlockSpec\n      __typename\n    }\n    bottom_sheet_item_list_1 {\n      ...CnvOptionItemBlockSpec\n      __typename\n    }\n    bottom_sheet_item_list_2 {\n      ...CnvOptionItemBlockSpec\n      __typename\n    }\n    view_icon {\n      ...CnvToggleIconBlockSpec\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CnvOptionItemBlockSpec on CnvOptionItemBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  is_selected\n  info_icon {\n    ...CnvIconBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvCheckboxBlockSpec on CnvCheckboxBlockSpec {\n  type\n  action_list {\n    ...CnvAction\n    __typename\n  }\n  ubl {\n    ...CnvUbl\n    __typename\n  }\n  text {\n    ...CnvText\n    __typename\n  }\n  is_selected\n  __typename\n}\n\nfragment CnvButtonContainerModuleSpecBody on CnvButtonContainerModuleSpecBody {\n  type\n  style\n  container_button: button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  reset_button {\n    ...CnvButtonBlockSpec\n    __typename\n  }\n  __typename\n}\n\nfragment CnvEmptyViewModuleSpecBody on CnvEmptyViewModuleSpecBody {\n  type\n  title {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  subtitle {\n    ...CnvTitleBlockSpec\n    __typename\n  }\n  __typename\n}'


class ZigzagCnvError(RuntimeError):
    pass


class ZigzagCnvCollector:
    def __init__(
        self,
        *,
        min_delay: float = DEFAULT_MIN_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        timeout: int = 20,
        session: requests.Session | None = None,
    ):
        self.min_delay = float(min_delay)
        self.max_delay = float(max_delay)
        self.timeout = int(timeout)
        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://zigzag.kr",
                "Referer": "https://zigzag.kr/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/152.0.0.0 Safari/537.36"
                ),
            }
        )

    def close(self) -> None:
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ============================================================
    # HTTP
    # ============================================================

    def _post(
        self,
        payload: list[dict[str, Any]],
        *,
        max_retries: int = 4,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = self.session.post(
                    CNV_ENDPOINT,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")

                    if retry_after:
                        try:
                            wait_seconds = float(retry_after)
                        except ValueError:
                            wait_seconds = 0.0
                    else:
                        wait_seconds = 0.0

                    if wait_seconds <= 0:
                        wait_seconds = (
                            min(60.0, 2 ** attempt)
                            + random.uniform(0.5, 1.5)
                        )

                    if attempt >= max_retries:
                        raise ZigzagCnvError(
                            f"Zigzag HTTP 429 after retries: {response.text[:500]}"
                        )

                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()

                data = response.json()

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("errors"):
                            raise ZigzagCnvError(
                                f"GraphQL errors: {item['errors']}"
                            )

                return data

            except (requests.RequestException, ValueError, ZigzagCnvError) as exc:
                last_error = exc

                if attempt >= max_retries:
                    break

                time.sleep(
                    min(30.0, 2 ** attempt)
                    + random.uniform(0.3, 1.0)
                )

        raise ZigzagCnvError(
            f"Zigzag CNV request failed: {last_error}"
        ) from last_error

    # ============================================================
    # FILTER
    # ============================================================
    @staticmethod
    def _to_int(value):
        if value is None or isinstance(value, bool):
            return None

        try:
            return int(
                float(
                    str(value)
                    .replace(",", "")
                    .strip()
                )
            )
        except (TypeError, ValueError):
            return None


    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value

        if value is None:
            return None

        text = str(value).strip().lower()

        if text in {"true", "1", "yes", "y"}:
            return True

        if text in {"false", "0", "no", "n"}:
            return False

        return None
        
    @staticmethod
    def make_combined_tag(
        value: str,
        *,
        attribute: str,
        name: str,
    ) -> dict[str, Any]:
        return {
            "filter_type": "COMBINED_TAG",
            "value_list": [
                {
                    "label": value,
                    "value": value,
                    "attribute": attribute,
                    "name": name,
                    "rangeGte": None,
                    "rangeLte": None,
                    "campaignId": None,
                    "campaignTagType": None,
                }
            ],
        }

    @staticmethod
    def build_search_state(
        *,
        category_id: str,
        order: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        filter_list: list[dict[str, Any]] = [
            {
                "filter_type": "CATEGORY",
                "value_list": [
                    {
                        "label": None,
                        "value": str(category_id),
                        "attribute": None,
                        "name": None,
                        "rangeGte": None,
                        "rangeLte": None,
                        "campaignId": None,
                        "campaignTagType": None,
                    }
                ],
            }
        ]

        if filters:
            filter_list.extend(filters)

        return {
            "filter_list": filter_list,
            "order": order,
        }

    # ============================================================
    # REQUEST
    # ============================================================

    def fetch_category_page(
        self,
        *,
        category_id: str,
    ) -> Any:
        """
        Fetch the initial srp_clp_category page.

        Unlike fetch_initial(), which calls GetCnvPageAction for product
        refetching, this calls GetCnvPage itself. The initial page contains
        the CATEGORY_TAB module used to discover current Zigzag subcategories.
        """
        page_endpoint = CNV_ENDPOINT.replace(
            "GetCnvPageAction",
            "GetCnvPage",
        )

        payload = [
            {
                "operationName": "GetCnvPage",
                "variables": {
                    "input": {
                        "page_key": "srp_clp_category",
                        "render_param_list": [
                            {
                                "type": "DEEPLINK_ENTRY",
                                "option": {
                                    "category_id": str(category_id),
                                    "page_id": "srp_clp_category",
                                },
                            }
                        ],
                    }
                },
                "query": GET_CNV_PAGE_QUERY,
            }
        ]

        original_endpoint = CNV_ENDPOINT
        last_error: Exception | None = None

        for attempt in range(5):
            try:
                response = self.session.post(
                    page_endpoint,
                    json=payload,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait_seconds = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        wait_seconds = 0.0

                    if wait_seconds <= 0:
                        wait_seconds = (
                            min(60.0, 2 ** attempt)
                            + random.uniform(0.5, 1.5)
                        )

                    if attempt >= 4:
                        raise ZigzagCnvError(
                            "Zigzag category page HTTP 429 after retries: "
                            f"{response.text[:500]}"
                        )

                    time.sleep(wait_seconds)
                    continue

                response.raise_for_status()
                data = response.json()

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("errors"):
                            raise ZigzagCnvError(
                                f"GetCnvPage GraphQL errors: {item['errors']}"
                            )

                return data

            except (requests.RequestException, ValueError, ZigzagCnvError) as exc:
                last_error = exc

                if attempt >= 4:
                    break

                time.sleep(
                    min(30.0, 2 ** attempt)
                    + random.uniform(0.3, 1.0)
                )

        raise ZigzagCnvError(
            f"Zigzag category page request failed: {last_error}"
        ) from last_error

    def parse_detail_categories(
        self,
        data: Any,
        *,
        parent_category_id: str | int | None = None,
    ) -> list[dict[str, str]]:
        """
        Extract unique subcategories from CATEGORY_TAB.

        Source of truth is CATEGORY_ITEM.ubl.server_log:
        category_id, category_name, root_category_id,
        sub_category_id, sub_category_name.
        """
        expected_parent = (
            str(parent_category_id)
            if parent_category_id is not None
            else None
        )

        categories: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for node in self._walk(data):
            if not isinstance(node, dict):
                continue

            if str(node.get("type") or "").upper() != "CATEGORY_ITEM":
                continue

            ubl = node.get("ubl")
            if not isinstance(ubl, dict):
                continue

            server_log = ubl.get("server_log")
            if not isinstance(server_log, dict):
                continue

            parent_id = server_log.get("category_id")
            parent_name = server_log.get("category_name")
            root_id = server_log.get("root_category_id")
            detail_id = server_log.get("sub_category_id")
            detail_name = server_log.get("sub_category_name")

            if detail_id is None or not detail_name:
                continue

            parent_id = str(parent_id or root_id or "").strip()
            root_id = str(root_id or parent_id or "").strip()
            detail_id = str(detail_id).strip()
            detail_name = str(detail_name).strip()
            parent_name = str(parent_name or "").strip()

            if expected_parent and parent_id != expected_parent:
                continue

            key = (parent_id, detail_id)
            if key in seen:
                continue

            seen.add(key)
            categories.append(
                {
                    "parent_id": parent_id,
                    "parent_name": parent_name,
                    "root_id": root_id,
                    "category_id": detail_id,
                    "category_name": detail_name,
                }
            )

        return categories

    def discover_detail_categories(
        self,
        *,
        category_id: str | int,
    ) -> list[dict[str, str]]:
        response = self.fetch_category_page(
            category_id=str(category_id),
        )

        return self.parse_detail_categories(
            response,
            parent_category_id=str(category_id),
        )

    def fetch_initial(
        self,
        *,
        category_id: str,
        layout_id: str,
        action_id: str,
        module_slot_id: str,
        order: str,
        filters: list[dict[str, Any]] | None = None,
    ) -> Any:
        search_state = self.build_search_state(
            category_id=category_id,
            order=order,
            filters=filters,
        )

        payload = [
            {
                "operationName": "GetCnvPageAction",
                "variables": {
                    "layout_id": str(layout_id),
                    "input_list": [
                        {
                            "action_id": action_id,
                            "type": "MODULE_REFETCH",
                            "target": {
                                "module_slot_id": module_slot_id,
                            },
                            "option": {
                                "__typename": "CnvModuleRefetchActionOption",
                                "type": "MODULE_REFETCH",
                                "server_option": {
                                    "delay": 0,
                                    "tryCount": 1,
                                    "initial": True,
                                    "renderParams": [
                                        {
                                            "changedFilterType": None,
                                            "filterDetailUiHints": {
                                                "keywordsByFilterType": {},
                                                "rangeBoundsByType": {},
                                            },
                                            "search_query_state": search_state,
                                            "base_search_query_state": None,
                                            "type": "SEARCH_FILTER_CHANGE",
                                        }
                                    ],
                                    "includeSelfOnUnwrap": True,
                                    "type": "MODULE_REFETCH",
                                },
                                "delay": 0,
                            },
                        }
                    ],
                },
                "query": GET_CNV_PAGE_ACTION_QUERY,
            }
        ]

        return self._post(payload)

    def fetch_next(
        self,
        *,
        layout_id: str,
        action_id: str,
        module_slot_id: str,
        server_option: dict[str, Any],
    ) -> Any:
        payload = [
            {
                "operationName": "GetCnvPageAction",
                "variables": {
                    "layout_id": str(layout_id),
                    "input_list": [
                        {
                            "action_id": action_id,
                            "type": "PAGINATION",
                            "target": {
                                "module_slot_id": module_slot_id,
                            },
                            "option": {
                                "__typename": "CnvBaseActionOption",
                                "type": "PAGINATION",
                                "server_option": server_option,
                            },
                        }
                    ],
                },
                "query": GET_CNV_PAGE_ACTION_QUERY,
            }
        ]

        time.sleep(
            random.uniform(
                self.min_delay,
                self.max_delay,
            )
        )

        return self._post(payload)

    # ============================================================
    # RESPONSE WALKERS
    # ============================================================

    @staticmethod
    def _walk(value: Any):
        yield value

        if isinstance(value, dict):
            for child in value.values():
                yield from ZigzagCnvCollector._walk(child)

        elif isinstance(value, list):
            for child in value:
                yield from ZigzagCnvCollector._walk(child)

    @staticmethod
    def _get_result(data: Any) -> dict[str, Any]:
        if not isinstance(data, list) or not data:
            raise ZigzagCnvError(
                "CNV response top-level is not a non-empty list."
            )

        first = data[0]

        if not isinstance(first, dict):
            raise ZigzagCnvError(
                "CNV response first item is not an object."
            )

        result = (
            (first.get("data") or {}).get("result")
        )

        if not isinstance(result, dict):
            raise ZigzagCnvError(
                "CNV response data.result was not found."
            )

        return result

    def parse_products(
        self,
        data: Any,
    ) -> list[dict[str, Any]]:

        products: list[dict[str, Any]] = []

        for node in self._walk(data):

            if not isinstance(node, dict):
                continue

            # ========================================================
            # 실제 구조
            #
            # wrapper
            # {
            #     "product_card": {
            #         "product_id": ...,
            #         "product": {...},
            #         "price": {...},
            #         ...
            #     },
            #     "ubl": {
            #         "server_log": {...}
            #     }
            # }
            # ========================================================

            card = node.get("product_card")

            if not isinstance(card, dict):
                continue

            product_id = card.get("product_id")

            product = card.get("product")

            if (
                not product_id
                or not isinstance(product, dict)
            ):
                continue

            # --------------------------------------------------------
            # PRODUCT
            # --------------------------------------------------------

            image = (
                product.get("image")
                if isinstance(
                    product.get("image"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # PRICE
            # card.price 임
            # --------------------------------------------------------

            price = (
                card.get("price")
                if isinstance(
                    card.get("price"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # REVIEW
            # --------------------------------------------------------

            review = (
                card.get("review")
                if isinstance(
                    card.get("review"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # SHOP
            # --------------------------------------------------------

            shop = (
                card.get("shop")
                if isinstance(
                    card.get("shop"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # SHIPPING
            # --------------------------------------------------------

            shipping = (
                card.get("shipping")
                if isinstance(
                    card.get("shipping"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # ENGAGEMENT
            # --------------------------------------------------------

            engagement = (
                card.get("engagement")
                if isinstance(
                    card.get("engagement"),
                    dict,
                )
                else {}
            )

            fomo = (
                engagement.get("fomo")
                if isinstance(
                    engagement.get("fomo"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # META
            # --------------------------------------------------------

            meta = (
                card.get("meta")
                if isinstance(
                    card.get("meta"),
                    dict,
                )
                else {}
            )

            shop_meta = (
                meta.get("shop")
                if isinstance(
                    meta.get("shop"),
                    dict,
                )
                else {}
            )

            state = (
                meta.get("state")
                if isinstance(
                    meta.get("state"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # UBL
            #
            # 중요:
            # ubl은 card 안이 아니라
            # card를 감싸고 있는 wrapper(node)에 있음
            # --------------------------------------------------------

            ubl = (
                node.get("ubl")
                if isinstance(
                    node.get("ubl"),
                    dict,
                )
                else {}
            )

            server_log = (
                ubl.get("server_log")
                if isinstance(
                    ubl.get("server_log"),
                    dict,
                )
                else {}
            )

            # --------------------------------------------------------
            # OUTPUT
            # --------------------------------------------------------

            products.append(
                {
                    "product_id":
                        str(product_id),

                    "product_name":
                        product.get("title"),

                    "image_url":
                        image.get("normal"),

                    "shop_id":
                        shop_meta.get("shop_id"),

                    "shop_name":
                        shop.get("name"),

                    "final_price":
                        price.get("final_price"),

                    "max_price":
                        price.get("max_price"),

                    "discount_rate":
                        price.get(
                            "final_price_discount_rate"
                        ),

                    "review_count": self._to_int(
                        review.get("count")
                    ),

                    "review_score":
                        review.get("score"),

                    "sales_status":
                        state.get("sales_status"),

                    "shipping_type":
                        state.get("shipping_type"),

                    "arrival_text":
                        shipping.get(
                            "arrival_text"
                        ),

                    "is_saved_product":
                        engagement.get(
                            "is_saved_product"
                        ),

                    "fomo_text":
                        fomo.get("fomo_text"),

                    # --------------------------------------------
                    # server log
                    # --------------------------------------------

                    "social_proof_value":
                        server_log.get(
                            "social_proof_value"
                        ),

                    "organic_position":
                        server_log.get(
                            "organic_position"
                        ),

                    "display_category_id":
                        server_log.get(
                            "display_category_id"
                        ),

                    "is_new": self._to_bool(
                        server_log.get("is_new")
                    ),

                    "is_ad":
                        bool(
                            server_log.get("ad_key")
                        ),

                    "recommend_score":
                        server_log.get(
                            "recommend_score"
                        ),

                    "badge_list":
                        server_log.get(
                            "badge_list"
                        ),

                    "server_log":
                        server_log,
                }
            )

        return products

    def extract_result_count(
        self,
        data: Any,
    ) -> int | None:
        for node in self._walk(data):
            if not isinstance(node, dict):
                continue

            value = node.get("result_count")

            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                return int(value)

            if isinstance(value, str):
                try:
                    return int(
                        value.replace(",", "").strip()
                    )
                except ValueError:
                    pass

        return None

    def extract_pagination(
        self,
        data: Any,
    ) -> dict[str, Any] | None:
        for node in self._walk(data):
            if not isinstance(node, dict):
                continue

            if str(node.get("type") or "").upper() != "PAGINATION":
                continue

            option = node.get("option")

            if not isinstance(option, dict):
                continue

            server_option = option.get("server_option")

            if not isinstance(server_option, dict):
                continue
            return {
                "action": node,
                "server_option": server_option,
            }

        return None

    def get_next_request_info(
        self,
        data: Any,
    ) -> dict[str, Any] | None:
        pagination = self.extract_pagination(data)

        if not pagination:
            return None

        action = pagination["action"]
        server_option = pagination["server_option"]

        target = (
            action.get("target")
            if isinstance(action.get("target"), dict)
            else {}
        )

        module_slot_id = (
            target.get("module_slot_id")
            or server_option.get("moduleSlotId")
        )

        if not module_slot_id:
            return None

        return {
            "module_slot_id": module_slot_id,
            "server_option": server_option,
        }

    # ============================================================
    # SNAPSHOT
    # ============================================================

    def collect_snapshot(
        self,
        *,
        category_id: str,
        layout_id: str,
        action_id: str,
        module_slot_id: str,
        order: str = "SCORE_DESC",
        filters: list[dict[str, Any]] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit은 1 이상이어야 합니다.")

        first_response = self.fetch_initial(
            category_id=category_id,
            layout_id=layout_id,
            action_id=action_id,
            module_slot_id=module_slot_id,
            order=order,
            filters=filters,
        )

        result_count = self.extract_result_count(
            first_response
        )

        all_products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        response = first_response
        page_no = 1

        while True:
            products = self.parse_products(response)
            new_count = 0

            for product in products:
                product_id = product.get("product_id")

                if not product_id:
                    continue

                if product_id in seen_ids:
                    continue

                seen_ids.add(product_id)

                product["rank"] = len(all_products) + 1

                all_products.append(product)
                new_count += 1

                if len(all_products) >= limit:
                    break

            print(
                f"[ZIGZAG] page={page_no} "
                f"received={len(products)} "
                f"new={new_count} "
                f"total={len(all_products)}"
            )

            if len(all_products) >= limit:
                break

            next_info = self.get_next_request_info(
                response
            )

            if not next_info:
                break

            page_no += 1

            response = self.fetch_next(
                layout_id=layout_id,
                action_id=action_id,
                module_slot_id=(
                    next_info.get("module_slot_id")
                    or module_slot_id
                ),
                server_option=next_info[
                    "server_option"
                ],
            )

        return {
            "category_id": str(category_id),
            "order": order,
            "filters": filters or [],
            "result_count": result_count,
            "is_count_capped": (
                result_count is not None
                and result_count >= 10000
            ),
            "collected_count": len(all_products),
            "products": all_products[:limit],
        }
