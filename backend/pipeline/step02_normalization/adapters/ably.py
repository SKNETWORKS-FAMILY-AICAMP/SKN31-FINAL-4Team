class AblyNormalizationAdapter:

    source_code = "ably"

    def build(
        self,
        product_source,
    ) -> dict:

        return {
            "product_source_id": (
                product_source.id
            ),
            "source_code": self.source_code,
            "source_name": str(
                product_source.source_name
                or ""
            ).strip(),
        }