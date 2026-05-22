"""
LLM-клиент: Ollama (локальный) → Google Gemini API → OpenRouter (fallback).

Приоритет:
1. Ollama на morgan (OLLAMA_URL) — бесплатно, локально
2. Google Gemini API (GEMINI_API_KEY) — бесплатный tier
3. OpenRouter (OPENROUTER_API_KEY) — платный fallback
"""

from __future__ import annotations

import logging
import os
import time

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(Exception):
    """Ошибка при работе с LLM API."""

    def __init__(self, message: str, original: Exception | None = None) -> None:
        super().__init__(message)
        self.original = original


class GeminiClient:
    """
    LLM-клиент: Ollama → Gemini API → OpenRouter.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "google/gemini-2.5-flash",
    ) -> None:
        self._openrouter_key = api_key
        self._openrouter_model = model

        self._gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self._gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

        self._ollama_url = os.environ.get("OLLAMA_URL", "").rstrip("/")
        self._ollama_model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

        self._openrouter_headers: dict | None = None
        if self._openrouter_key:
            self._openrouter_headers = {
                "Authorization": f"Bearer {self._openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/valencia-news-bot",
                "X-Title": "Valencia News Bot",
            }

        if self._ollama_url:
            logger.info("LLM клиент: Ollama %s, модель: %s", self._ollama_url, self._ollama_model)
        elif self._gemini_key:
            logger.info("LLM клиент: Google Gemini API, модель: %s", self._gemini_model)
        elif self._openrouter_headers:
            logger.info("LLM клиент: OpenRouter, модель: %s", model)
        else:
            raise GeminiError("Нет ни OLLAMA_URL, ни GEMINI_API_KEY, ни OPENROUTER_API_KEY")

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((requests.RequestException, GeminiError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _generate_via_ollama(self, prompt: str, max_tokens: int) -> str:
        url = f"{self._ollama_url}/v1/chat/completions"
        payload = {
            "model": self._ollama_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "stream": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=120)
        except requests.RequestException as exc:
            raise GeminiError(f"Ollama сетевая ошибка: {exc}", original=exc) from exc

        if resp.status_code != 200:
            raise GeminiError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")

        choices = resp.json().get("choices", [])
        if not choices:
            raise GeminiError("Ollama вернул пустой choices")

        text: str = choices[0].get("message", {}).get("content", "").strip()
        if not text:
            raise GeminiError("Ollama вернул пустой текст")

        return text

    # ------------------------------------------------------------------
    # Google Gemini API
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((requests.RequestException, GeminiError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _generate_via_gemini(self, prompt: str, max_tokens: int) -> str:
        url = GEMINI_API_URL.format(model=self._gemini_model)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.3,
            },
        }
        try:
            resp = requests.post(
                url,
                params={"key": self._gemini_key},
                json=payload,
                timeout=60,
            )
        except requests.RequestException as exc:
            raise GeminiError(f"Gemini API сетевая ошибка: {exc}", original=exc) from exc

        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 30))
            logger.warning("Gemini API 429, ждём %d сек...", retry_after)
            time.sleep(retry_after)
            raise GeminiError("Gemini API rate limit 429")

        if resp.status_code != 200:
            raise GeminiError(f"Gemini API HTTP {resp.status_code}: {resp.text[:200]}")

        candidates = resp.json().get("candidates", [])
        if not candidates:
            raise GeminiError("Gemini API вернул пустой candidates")

        text: str = (
            candidates[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
        )
        if not text:
            raise GeminiError("Gemini API вернул пустой текст")

        return text

    # ------------------------------------------------------------------
    # OpenRouter fallback
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((requests.RequestException, GeminiError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _generate_via_openrouter(self, prompt: str, max_tokens: int) -> str:
        if not self._openrouter_headers:
            raise GeminiError("OpenRouter API ключ не задан")

        payload = {
            "model": self._openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers=self._openrouter_headers,
                json=payload,
                timeout=60,
            )
        except requests.RequestException as exc:
            raise GeminiError(f"OpenRouter сетевая ошибка: {exc}", original=exc) from exc

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "")
            wait_secs = int(retry_after) if str(retry_after).isdigit() else 30
            logger.warning("OpenRouter 429, ждём %d сек...", wait_secs)
            time.sleep(wait_secs)
            raise GeminiError("OpenRouter rate limit 429")

        if resp.status_code != 200:
            raise GeminiError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}")

        choices = resp.json().get("choices", [])
        if not choices:
            raise GeminiError("OpenRouter вернул пустой choices")

        text: str = choices[0].get("message", {}).get("content", "").strip()
        if not text:
            raise GeminiError("OpenRouter вернул пустой текст")

        return text

    # ------------------------------------------------------------------
    # Публичный метод
    # ------------------------------------------------------------------

    def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Генерирует текст. Приоритет: Ollama → Gemini API → OpenRouter.
        """
        if self._ollama_url:
            try:
                result = self._generate_via_ollama(prompt, max_tokens)
                logger.debug("Ollama: ответ %d символов", len(result))
                return result
            except GeminiError as exc:
                logger.warning("Ollama недоступен (%s), пробуем Gemini API...", exc)

        if self._gemini_key:
            try:
                result = self._generate_via_gemini(prompt, max_tokens)
                logger.debug("Gemini API: ответ %d символов", len(result))
                return result
            except GeminiError as exc:
                logger.warning("Gemini API недоступен (%s), пробуем OpenRouter...", exc)

        return self._generate_via_openrouter(prompt, max_tokens)
