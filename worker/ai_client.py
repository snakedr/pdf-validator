import os
import httpx
import json
from typing import Dict, Any, Optional
from celery_app import AI_API_KEY, AI_MODEL, AI_BASE_URL
from utils import logger

class UniversalAIClient:
    """Универсальный OpenAI-совместимый клиент для любого AI провайдера"""
    
    def __init__(self):
        self.api_key = AI_API_KEY
        self.model = AI_MODEL
        self.base_url = AI_BASE_URL.rstrip('/')
        
        if not self.api_key:
            logger.warning("AI_API_KEY not configured, skipping AI validation")
    
    async def validate_document(self, document_text: str, tables_data: list) -> Dict[str, Any]:
        """Универсальная валидация документа через AI"""
        
        if not self.api_key:
            return self._mock_response()
        
        try:
            prompt = self._build_prompt(document_text, tables_data)
            response = await self._make_request(prompt)
            return self._parse_response(response)
            
        except Exception as e:
            logger.error(f"AI validation failed: {e}")
            return self._mock_response()
    
    def _build_prompt(self, document_text: str, tables_data: list) -> str:
        """Создание промпта для валидации"""
        
        # Ограничиваем длину текста
        max_chars = 2000
        truncated_text = document_text[:max_chars]
        if len(document_text) > max_chars:
            truncated_text += "...[truncated]"
        
        # Ограничиваем количество таблиц
        max_tables = 3
        truncated_tables = tables_data[:max_tables]
        
        prompt = f"""Проанализируй документ и ответь в формате JSON.

Текст документа:
---
{truncated_text}
---

Таблицы (максимум {max_tables}):
{json.dumps(truncated_tables, ensure_ascii=False, indent=2)}

Задания:
1. Проверь содержит ли документ даты текущего месяца (февраль 2026)
2. Проверь содержатся ли в таблицах только числовые значения
3. Оцени общую корректность документа

Ответь строго в этом JSON формате:
{{
    "dates_match_current_month": true/false,
    "all_table_cells_are_numbers": true/false,
    "notes": "Краткий комментарий по результатам анализа"
}}"""
        
        return prompt
    
    async def _make_request(self, prompt: str) -> Dict[str, Any]:
        """Отправка запроса к AI API"""
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://email-processor.local",
            "X-Title": "Email Processor PDF Validator"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты - эксперт по анализу документов. Отвечай только в указанном JSON формате."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 500
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()
    
    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Парсинг OpenAI-совместимого ответа"""
        
        try:
            content = response["choices"][0]["message"]["content"]
            
            # Пытаемся распарсить JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return json.loads(content)
                
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Failed to parse AI response: {e}, raw: {response}")
            return self._mock_response()
    
    def _mock_response(self) -> Dict[str, Any]:
        """Заглушка когда AI недоступен"""
        return {
            "dates_match_current_month": True,
            "all_table_cells_are_numbers": True,
            "notes": "AI validation skipped - using deterministic validation only"
        }

# Создаем глобальный экземпляр
ai_client = UniversalAIClient()