class PhraseExtractor:
    def extract(self, residual_text: str) -> list[str]:
        tokens = residual_text.split()

        candidates = set()

        for token in tokens:
            candidates.add(token)

        for i in range(len(tokens) - 1):
            candidates.add(
                f"{tokens[i]} {tokens[i + 1]}"
            )

        for i in range(len(tokens) - 2):
            candidates.add(
                f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}"
            )

        return sorted(candidates)