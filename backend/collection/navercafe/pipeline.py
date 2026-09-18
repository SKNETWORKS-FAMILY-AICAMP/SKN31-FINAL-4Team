from .client import NaverCafeClient
from .collector import NaverCafeCollector
from .parser import NaverCafeParser


def run():

    with NaverCafeClient() as client:

        collector = NaverCafeCollector(client)
        parser = NaverCafeParser()

        for board_type in [
            "OUTFIT",
            "SHOES",
            "ACCESSORY",
            "LOOKBOOK",
            "QUESTION",
            "GENERAL",
            "DEAL",
        ]:

            raw = collector.collect_articles(
                board_type=board_type,
                page=1,
            )

            articles = parser.parse_articles(
                raw,
                board_type=board_type,
            )

            # S3 저장
            # ...