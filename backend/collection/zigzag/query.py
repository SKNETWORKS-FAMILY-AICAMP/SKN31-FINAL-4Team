GET_CNV_PAGE_ACTION_QUERY = """
query GetCnvPageAction(
  $layout_id: ID!,
  $input_list: [CnvPageActionInput!]!
) {
  result: cnv_page_action(
    layout_id: $layout_id,
    input_list: $input_list
  ) {
    layout_id

    module_spec_update_list {
      action_id

      module_spec_list {
        meta {
          module_slot_id
          module_id
          module_spec_id

          action_list {
            type
            trigger_type

            target {
              module_slot_id
              module_id_list
            }

            option {
              type
              server_option
            }
          }

          share_log {
            server_log
          }

          ubl {
            server_log
          }
        }

        body {
          type

          ... on CnvProductCardModuleSpecBody {
            product_card {
              product_card {
                product_id

                product {
                  title

                  image {
                    normal
                  }
                }

                price {
                  final_price
                  final_price_discount_rate
                  max_price
                  final_price_suffix
                }

                review {
                  count
                  score
                }

                shop {
                  name
                }

                shipping {
                  arrival_text {
                    text
                  }
                }

                engagement {
                  is_saved_product

                  fomo {
                    fomo_text
                  }
                }

                meta {
                  shop {
                    shop_id
                    status
                    delete_action
                  }

                  state {
                    sales_status
                    shipping_type
                  }
                }
              }

              ubl {
                object {
                  id
                  idx
                  section
                  type
                  url
                }

                server_log
              }
            }
          }
        }
      }
    }
  }
}
"""