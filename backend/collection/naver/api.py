from .client import NaverApiClient


def get_blog(client: NaverApiClient, query: str) -> list[dict]:
    return client.request("GET", "/search/v1/blog", params={"query": query, "display": 100, "sort": "date"}).get("items", [])


def get_search_trend(client: NaverApiClient, payload: dict) -> list[dict]:
    return client.request("POST", "/search-trend/v1/search", json=payload).get("results", [])


def get_shopping_trend(client: NaverApiClient, payload: dict) -> list[dict]:
    return client.request("POST", "/shopping/v1/category/keywords", json=payload).get("results", [])
