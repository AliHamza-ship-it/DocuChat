from openai import OpenAI
from backend.core.config import settings
from backend.prompts.system_prompts import SYSTEM_RAG_PROMPT
import logging

logger = logging.getLogger(__name__)

class RAGGenerator:
    def __init__(self):
        # OpenRouter provides an OpenAI-compatible interface
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
        )
        # Using a reliable free model on OpenRouter
        self.model_name = "meta-llama/llama-3.3-70b-instruct:free"

    def generate_grounded_answer(self, query: str, context_chunks: list[dict]) -> str:
        """Generates a grounded response with citations or returns explicit refusal."""
        if not context_chunks:
            return "I cannot answer this question because no relevant documents or sections were found."

        # Format context into formatted block for the prompt
        formatted_context_parts = []
        for idx, chunk in enumerate(context_chunks, 1):
            meta = chunk.get("metadata", {})
            source_file = meta.get("source", "Unknown Document")
            page_num = meta.get("page", 1)
            content = chunk.get("content", "")
            formatted_context_parts.append(
                f"--- Chunk {idx} | Source: {source_file} | Page: {page_num} ---\n{content}"
            )

        context_block = "\n\n".join(formatted_context_parts)
        system_prompt = SYSTEM_RAG_PROMPT.format(context_block=context_block)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,  # Low temperature for factual precision
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenRouter API error: {str(e)}")
            # Fallback model attempt if primary free model is busy
            try:
                response = self.client.chat.completions.create(
                    model="openrouter/free",  
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query}
                    ],
                    temperature=0.1,
                    max_tokens=1000
                )
                return response.choices[0].message.content.strip()
            except Exception as fallback_err:
                return f"An error occurred while generating the answer: {str(fallback_err)}"

rag_generator = RAGGenerator()