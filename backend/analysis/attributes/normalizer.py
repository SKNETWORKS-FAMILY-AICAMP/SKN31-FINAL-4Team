# backend/analysis/attributes/normalizer.py


class AttributeNormalizer:

    def normalize(
        self,
        predictions: dict,
    ) -> dict:

        normalized = {}

        attributes = predictions.get(
            "attributes",
            {},
        )

        for attribute, values in (
            attributes.items()
        ):

            normalized[attribute] = [
                {
                    "model_label": value["label"],
                    "score": value["score"],
                }
                for value in values
            ]

        return normalized