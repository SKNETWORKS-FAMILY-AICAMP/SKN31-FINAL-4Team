from collections.abc import Iterable, Iterator


def make_blog_queries(keyword: str, category: str) -> list[str]:
    if category == "STYLE":
        return [keyword, f"{keyword} 패션", f"{keyword} 코디"]
    if category in {"COLOR", "FIT"}:
        return [f"{keyword} 코디"]
    return [keyword]


def keyword_group(name: str, aliases: list[str]) -> dict[str, list[str] | str]:
    return {"groupName": name, "keywords": list(dict.fromkeys([name, *aliases]))[:20]}


def chunks(items: Iterable, size: int = 5) -> Iterator[list]:
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
