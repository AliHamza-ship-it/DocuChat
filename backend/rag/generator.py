import logging
import re
from openai import OpenAI
from backend.core.config import settings
from backend.prompts.system_prompts import SYSTEM_RAG_PROMPT

logger = logging.getLogger(__name__)

class RAGGenerator:
    def __init__(self):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "DocuChat",
            }
        )
        self.model_name = "nvidia/nemotron-3-super-120b-a12b:free"

    def _clean_response(self, text: str) -> str:
        if not text:
            return ""

        answer_match = re.search(r'<answer>(.*?)(?:</answer>|$)', text, flags=re.DOTALL | re.IGNORECASE)
        if answer_match:
            text = answer_match.group(1)

        text = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<reasoning>.*?(?:</reasoning>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'</?(?:think|answer|reasoning)>', '', text, flags=re.IGNORECASE)

        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if len(lines) >= 2 and lines[0].startswith("```"):
                if lines[-1].strip() == "```":
                    cleaned = "\n".join(lines[1:-1])
                else:
                    cleaned = "\n".join(lines[1:])

        return cleaned.strip()

    def _format_context(self, context_chunks: list[dict]) -> str:
        if not context_chunks:
            return "No document context available for this query."
            
        formatted_parts = []
        for idx, chunk in enumerate(context_chunks, 1):
            meta = chunk.get("metadata", {})
            source_file = meta.get("source", "Unknown Document")
            page_num = meta.get("page", 1)
            content = chunk.get("content", "").strip()
            formatted_parts.append(
                f"[DOCUMENT CHUNK {idx}]\nSource File: {source_file}\nPage Number: {page_num}\nContent:\n{content}"
            )
        return "\n\n----------------------------------------\n\n".join(formatted_parts)

    def generate_grounded_answer(self, query: str, context_chunks: list[dict]) -> str:
        context_block = self._format_context(context_chunks)
        system_prompt = SYSTEM_RAG_PROMPT.format(context_block=context_block)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,
                frequency_penalty=0.2,
                max_tokens=3000,
                timeout=30.0
            )
            raw_content = response.choices[0].message.content or ""
            return self._clean_response(raw_content)
        except Exception as e:
            logger.error(f"OpenRouter API error: {str(e)}")
            return f"An error occurred while generating the answer: {str(e)}"

    def stream_grounded_answer(self, query: str, context_chunks: list[dict]):
        context_block = self._format_context(context_chunks)
        system_prompt = SYSTEM_RAG_PROMPT.format(context_block=context_block)

        try:
            response_stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,
                frequency_penalty=0.2,
                max_tokens=3000,
                stream=True,
                timeout=30.0
            )

            full_buffer = ""
            yielded_len = 0

            for chunk in response_stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_buffer += delta

                    cleaned = self._clean_response(full_buffer)
                    tail_match = re.search(r'(<[^>]*$|```[a-z]*$)', cleaned, flags=re.IGNORECASE)
                    safe_len = tail_match.start() if tail_match else len(cleaned)

                    if safe_len > yielded_len:
                        to_yield = cleaned[yielded_len:safe_len]
                        yielded_len = safe_len
                        yield to_yield

            final_cleaned = self._clean_response(full_buffer)
            if len(final_cleaned) > yielded_len:
                yield final_cleaned[yielded_len:]

        except Exception as e:
            logger.error(f"OpenRouter Streaming API error: {str(e)}")
            yield f"\n\n[Error generating answer: {str(e)}]"

    def generate_chat_title(self, first_query: str) -> str:
        try:
            prompt = f"Summarize the following query into a concise 3-4 word chat title. Return ONLY the title text without quotes or preamble.\n\nQuery: {first_query}"
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=15,
                timeout=10.0
            )
            raw_title = response.choices[0].message.content or ""
            title = self._clean_response(raw_title).strip()
            return title if title else "New Conversation"
        except Exception:
            words = first_query.split()[:4]
            return " ".join(words).title() if words else "New Conversation"

rag_generator = RAGGenerator()