import logging
import os
import re
from openai import OpenAI
from backend.core.config import settings
from backend.prompts.system_prompts import SYSTEM_RAG_PROMPT

logger = logging.getLogger(__name__)

class RAGGenerator:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("GEMINI_API_KEY"),
            base_url=(
                "https://generativelanguage.googleapis.com/"
                "v1beta/openai/"
            ),
        )

        self.model_name = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.1-flash-lite",
        )

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

    def _complete(
        self,
        user_content: str,
        system_prompt: str,
        max_tokens: int = 1800,
    ) -> str:
        """
        Non-streaming completion used by SRAG.

        The SRAG pipeline needs a complete answer before
        validation, therefore this method intentionally
        does not stream.
        """

        try:

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_content,
                    },
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            )

            raw_content = (
                response.choices[0].message.content
                or ""
            )

            return self._clean_response(
                raw_content
            )

        except Exception as exc:

            logger.error(
                "Gemini completion error: %s",
                exc,
            )

            raise

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

    def generate_chat_title(self, query: str) -> str:
        """
        Uses a strict Few-Shot prompt to guarantee a clean 3-5 word title based on the user's query.
        """
        try:
            # Truncate to prevent long queries from breaking the instruction
            short_query = query[:400].strip()
            
            prompt = (
                "You are an AI title generator. Extract the core subject of the user's query into a short 3 to 5 word title.\n"
                "Output ONLY the title words. No conversational text, no quotes, no 'Title:'.\n\n"
                "Example 1:\n"
                "Query: Explain how LiGas batteries work in extreme cold conditions.\n"
                "Title: LiGas Batteries In Cold\n\n"
                "Example 2:\n"
                "Query: Who is the current director of the STEM education department?\n"
                "Title: STEM Education Department Director\n\n"
                f"Query: {short_query}\n"
                "Title:"
            )
            
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,  # Low temperature for strict compliance
                max_tokens=10,
                timeout=8.0
            )
            
            raw_title = completion.choices[0].message.content or ""
            
            # Post-process to remove unwanted artifacts like "Title:" or quotes
            title = re.sub(r'^(title:|chat title:|\"|\')', '', raw_title, flags=re.IGNORECASE).strip()
            title = re.sub(r'(\"|\')$', '', title).strip()
            
            # Fallback constraint if the LLM hallucinates a long sentence anyway
            words = title.split()
            if not title or len(words) > 7:
                words = short_query.split()[:4]
                return " ".join(words).title()
                
            return title.title()
            
        except Exception as e:
            logger.error(f"Title generation failed: {str(e)}")
            words = query.split()[:4]
            return " ".join(words).title() if words else "New Conversation"

rag_generator = RAGGenerator()