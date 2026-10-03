from importlib import import_module


PIPELINE_REGISTRY = {
    "ABLY": "collection.ably.pipeline.AblyPipeline",
    "KREAM": "collection.kream.pipeline.KreamPipeline",
    "MUSINSA": "collection.musinsa.pipeline.MusinsaPipeline",
    "MUSINSA_USED": "collection.musinsa_used.pipeline.MusinsaUsedPipeline",
    "YOUTUBE": "collection.youtube.pipeline.""YoutubePipeline",
    "ZIGZAG": "collection.zigzag.pipeline.ZigzagPipeline",
}


def get_pipeline_class(
    source_code: str,
):
    key = source_code.upper()

    try:
        path = PIPELINE_REGISTRY[key]

    except KeyError as exc:
        raise ValueError(
            f"지원하지 않는 플랫폼입니다: "
            f"{source_code}"
        ) from exc

    module_path, class_name = (
        path.rsplit(".", 1)
    )

    module = import_module(
        module_path
    )

    return getattr(
        module,
        class_name,
    )
