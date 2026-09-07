from __future__ import annotations

from openai import OpenAI


class TermEmbeddingService:

    MODEL = "text-embedding-3-small"

    def __init__(self):
        self.client = OpenAI()

    def embed(self, text: str) -> list[float]:
        text = text.strip()

        if not text:
            raise ValueError("Embedding text is empty.")

        response = self.client.embeddings.create(
            model=self.MODEL,
            input=text,
        )

        return response.data[0].embedding

    def build_candidate_text(self, candidate) -> str:

        observations = (
            candidate.observations
            .order_by("-detected_at")[:5]
        )

        contexts = [
            obs.raw_text
            for obs in observations
        ]

        context_text = "\n".join(
            f"- {context}"
            for context in contexts
        )

        return (
            f"패션 용어: {candidate.raw_term}\n"
            f"추천 유형: {candidate.suggested_type or 'UNKNOWN'}\n"
            f"사용 문맥:\n"
            f"{context_text}"
        )

    def build_dictionary_term_text(self, term) -> str:

        parts = [
            f"패션 용어: {term.canonical_name}",
            f"유형: {term.term_type}",
        ]

        if term.english_name:
            parts.append(
                f"영문명: {term.english_name}"
            )

        if term.description:
            parts.append(
                f"설명: {term.description}"
            )

        return "\n".join(parts)