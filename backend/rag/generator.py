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
        # Verified active OpenRouter free model
        self.model_name = "openai/gpt-oss-20b:free"

    def generate_grounded_answer(self, query: str, context_chunks: list[dict]) -> str:
        """Generates a grounded response with citations or returns explicit refusal (Non-streaming)."""
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
            return f"An error occurred while generating the answer: {str(e)}"

    def stream_grounded_answer(self, query: str, context_chunks: list[dict]):
        """Generates a grounded response and yields it token-by-token for UI streaming."""
        if not context_chunks:
            # Splits the fallback message to stream it word-by-word
            refusal_msg = "I cannot answer this question because no relevant documents or sections were found."
            for word in refusal_msg.split():
                yield word + " "
            return

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
            response_stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,
                max_tokens=1000,
                stream=True 
            )
            
            # Iterate through the chunks as they arrive from OpenRouter
            for chunk in response_stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"OpenRouter Streaming API error: {str(e)}")
            error_msg = f"\n\nAn error occurred while generating the answer: {str(e)}"
            for word in error_msg.split():
                yield word + " "

    def generate_chat_title(self, first_query: str) -> str:
        """Generates a concise 3-4 word title for a new conversation based on the first prompt."""
        try:
            prompt = f"Summarize the following user request into a concise 3-4 word title. Return ONLY the title text, with no quotes, markdown, or punctuation.\n\nQuery: {first_query}"
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=15
            )
            title = response.choices[0].message.content.strip()
            return title if title else "New Conversation"
        except Exception:
            # Fallback title if API call fails
            words = first_query.split()[:4]
            return " ".join(words).title() if words else "New Conversation"

rag_generator = RAGGenerator()