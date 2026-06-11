"""
Centralized LLM client for generating context summaries and answers.
Uses litellm to support multiple providers (Gemini, Groq, Ollama).
"""

from __future__ import annotations

import logging

import litellm

from app.config import settings

logger = logging.getLogger(__name__)

# Suppress litellm telemetry and excessive logging
litellm.telemetry = False
litellm.suppress_debug_info = True


async def generate_answer(system_prompt: str, user_prompt: str, model_name: str | None = None) -> str:
    """
    Generate an answer using the configured LLM.

    Args:
        system_prompt: Instructions for the LLM.
        user_prompt: The user query + context.
        model_name: Optional override for the model to use. Defaults to settings.llm_model.

    Returns:
        The synthesized response string.
    """
    model = model_name or settings.llm_model
    logger.info("Generating LLM response using model: %s", model)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        logger.info("LLM request — model=%s, prompt_len=%d chars", model, len(user_prompt))
        logger.debug("LLM system prompt: %s", system_prompt[:500])
        logger.debug("LLM user prompt (first 1000 chars): %s", user_prompt[:1000])

        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=0.0,  # low temperature for RAG to minimize hallucination
            max_tokens=4000,
        )
        answer = response.choices[0].message.content or ""
        logger.info("LLM response — model=%s, response_len=%d chars", model, len(answer))
        logger.debug("LLM response (first 1000 chars): %s", answer[:1000])
        return answer
    except Exception as e:
        logger.error("LLM Generation failed: %s", e)
        return f"Error: Failed to generate answer using {model}. Details: {str(e)}"
