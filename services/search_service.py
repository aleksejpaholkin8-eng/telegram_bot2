import asyncio
import logging
from typing import List, Tuple

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)


async def _search_duckduckgo(query: str, max_results: int = 5) -> Tuple[List[dict], str]:
    """Пробуем DuckDuckGo (часто банит облачные IP)"""
    if not DDGS_AVAILABLE:
        return [], "DDGS не установлен"
    
    for attempt in range(2):
        try:
            with DDGS(headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            }) as ddgs:
                results = list(ddgs.text(query, max_results=max_results, backend="lite"))
                
                if not results:
                    return [], "Ничего не найдено"
                
                return [{
                    "title": r.get("title", "Без названия"),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                } for r in results], ""
                
        except Exception as e:
            logger.warning(f"DuckDuckGo попытка {attempt+1} не удалась: {e}")
            if attempt == 0:
                await asyncio.sleep(2)
    
    return [], "DuckDuckGo недоступен"


async def _search_searxng(query: str, max_results: int = 5) -> Tuple[List[dict], str]:
    """
    Fallback через публичные SearXNG инстансы.
    SearXNG — это метапоисковик, который агрегирует Google, Bing, DuckDuckGo.
    """
    if not AIOHTTP_AVAILABLE:
        return [], "aiohttp не установлен"
    
    # Список публичных SearXNG инстансов (проверены на работоспособность)
    instances = [
        "https://search.sapti.me",
        "https://search.bus-hit.me",
        "https://search.projectsegfault.com",
    ]
    
    for instance in instances:
        try:
            url = f"{instance}/search"
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "ru-RU"
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }) as response:
                    
                    if response.status != 200:
                        continue
                    
                    data = await response.json()
                    results = data.get("results", [])[:max_results]
                    
                    if not results:
                        continue
                    
                    return [{
                        "title": r.get("title", "Без названия"),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "")
                    } for r in results], ""
                    
        except Exception as e:
            logger.warning(f"SearXNG {instance} не сработал: {e}")
            continue
    
    return [], "Все SearXNG инстансы недоступны"


async def web_search(query: str, max_results: int = 5) -> Tuple[List[dict], str]:
    """
    Универсальный поиск: сначала DuckDuckGo, потом SearXNG fallback.
    """
    # Попытка 1: DuckDuckGo
    results, error = await _search_duckduckgo(query, max_results)
    if results:
        return results, ""
    
    logger.info("DuckDuckGo не сработал, пробуем SearXNG...")
    
    # Попытка 2: SearXNG
    results, error2 = await _search_searxng(query, max_results)
    if results:
        return results, ""
    
    # Ничего не сработало
    return [], (
        "❌ <b>Веб-поиск временно недоступен</b>\n\n"
        "DuckDuckGo и SearXNG не отвечают с этого сервера.\n\n"
        "💡 <b>Решения:</b>\n"
        "1. Попробуй позже (возможно, временный бан IP)\n"
        "2. Добавь SerpAPI ключ в переменные окружения (стабильно, но платно)\n"
        "3. Используй поиск через AI-модели с веб-доступом (Gemini, Perplexity)"
    )
