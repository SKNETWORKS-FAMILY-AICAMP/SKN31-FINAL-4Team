from __future__ import annotations

METRIC_VERSION = "feedit-step04-v1"
SEARCH_METRIC_VERSION = "feedit-search-v1"
NORMALIZATION_WINDOW_DAYS = 28
HISTORICAL_START_DATE = "2019-04-11"

# Meaning weights only. These DO NOT compensate for platform data volume.
LEVEL_WEIGHTS = {
    "presence": 0.35,
    "attention": 0.30,
    "engagement": 0.20,
    "intent": 0.15,
}

TEMPERATURE_WEIGHTS = {
    "level": 0.60,
    "momentum": 0.40,
}

# Empirical-Bayes reaction shrinkage strength.
REACTION_PRIOR_STRENGTH = 5.0

# Metrics whose zero is a real observed zero only when the source/date cohort
# contains at least one positive observation. An all-zero cohort is treated as
# unavailable (NULL), not as weak popularity.
COUNT_SIGNAL_PATHS = {
    "product_count": ("commerce", "product_count"),
    "ranked_product_count": ("commerce", "ranked_product_count"),
    "review_count": ("commerce", "max_review_count"),
    "commerce_like_count": ("commerce", "max_like_count"),
    "commerce_view_count": ("commerce", "max_view_count"),
    "sales_count": ("commerce", "max_sales_count"),
    "trade_count": ("commerce", "max_trade_count"),
    "wish_count": ("commerce", "max_wish_count"),
    "buy_count": ("commerce", "max_buy_count"),
    "content_count": ("content", "content_count"),
    "creator_count": ("content", "creator_count"),
    "content_view_count": ("content", "max_view_count"),
    "content_like_count": ("content", "max_like_count"),
    "comment_count": ("content", "max_comment_count"),
}

AXIS_SIGNAL_WEIGHTS = {
    "presence": {
        "product_count": 1.0,
        "ranked_product_count": 1.0,
        "content_count": 1.0,
        "creator_count": 0.8,
        "mention_count": 1.0,
    },
    "attention": {
        "commerce_view_count": 0.8,
        "content_view_count": 1.0,
        "review_count": 0.7,
        "mention_count": 0.8,
        "search_volume": 1.0,
    },
    "engagement": {
        "commerce_like_count": 0.7,
        "content_like_count": 0.8,
        "comment_count": 0.9,
        "review_count": 0.8,
        "positive_rate_adjusted": 0.5,
        "praise_rate_adjusted": 0.5,
    },
    "intent": {
        "purchase_rate_adjusted": 1.0,
        "question_rate_adjusted": 0.6,
        "wish_count": 0.8,
        "buy_count": 1.0,
        "sales_count": 0.8,
        "search_volume": 0.7,
    },
}
