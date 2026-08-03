# ============================================
# ВЕБ-ПОИСК ЧЕРЕЗ DUCKDUCKGO (с retry и fallback)
# ============================================

import asyncio
import logging
from typing import List, Tuple

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logging.warning("duckduckgo-search не установлен. Веб-поиск недоступен.")


async def web_search(query: str, max_results: int = 5) -> Tuple[List[dict], str]:
    """
    Ищет в интернете через DuckDuckGo.
    С retry, заголовками и fallback на lite-режим.
    """
    if not DDGS_AVAILABLE:
        return [], "❌ Модуль duckduckgo-search не установлен."
    
    # Пробуем несколько раз с задержкой (DuckDuckGo иногда банит по IP)
    for attempt in range(3):
        try:
            # headers помогают обойти базовую блокировку ботов
            with DDGS(headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0"
            }) as ddgs:
                
                # Пробуем lite-режим (меньше защиты от ботов)
                results = list(ddgs.text(
                    query, 
                    max_results=max_results,
                    backend="lite"  # ← lite-режим, проще для обхода блокировок
                ))
                
                if not results:
                    return [], "🔍 Ничего не найдено."
                
                formatted = []
                for r in results:
                    formatted.append({
                        "title": r.get("title", "Без названия"),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
                
                return formatted, ""
                
        except Exception as e:
            error_text = str(e)
            logging.warning(f"Попытка {attempt+1}/3 поиска не удалась: {error_text[:100]}")
            
            if "202" in error_text or "Ratelimit" in error_text or "ratelimit" in error_text:
                if attempt < 2:
                    await asyncio.sleep(2 + attempt * 2)  # Ждём 2с, потом 4с
                    continue
            
            # Если это не rate limit или последняя попытка — возвращаем ошибку
            return [], (
                "❌ <b>DuckDuckGo временно недоступен</b>\n\n"
                "Возможные причины:\n"
                "• Слишком много запросов с этого сервера\n"
                "• DuckDuckGo блокирует облачные IP (Railway, AWS и т.д.)\n\n"
                "💡 <b>Решение:</b> попробуй позже или используй веб-поиск "
                "через другой сервис (например, SerpAPI — платный, но стабильный)."
            )
    
    return [], "❌ Не удалось выполнить поиск после 3 попыток."
