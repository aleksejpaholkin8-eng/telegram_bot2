# ============================================
# ВЕБ-ПОИСК ЧЕРЕЗ DUCKDUCKGO
# ============================================

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
    Возвращает: (список результатов, сообщение об ошибке)
    """
    if not DDGS_AVAILABLE:
        return [], "❌ Модуль duckduckgo-search не установлен."
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            
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
        logging.error(f"Ошибка поиска: {e}")
        return [], f"❌ Ошибка поиска: {str(e)[:200]}"
