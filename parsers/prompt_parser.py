# ============================================
# ПАРСЕР MARKDOWN-ФАЙЛА С РОЛЯМИ
# ============================================

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ParsedRole:
    """Одна распарсенная роль"""
    name: str
    group_name: str = "CORE"
    prompt_text: str = ""
    keywords: str = ""
    tier_access: str = "lite"
    is_active: bool = True


@dataclass
class ParsedRule:
    """Одно распарсенное правило"""
    number: int
    text: str
    is_active: bool = True


@dataclass
class ParsedCommand:
    """Одна распарсенная команда"""
    cluster: str = "CORE"
    name: str = ""
    description: str = ""
    tier_access: str = "lite"


@dataclass
class ParsedPrompt:
    """Результат парсинга всего файла"""
    roles: List[ParsedRole] = field(default_factory=list)
    rules: List[ParsedRule] = field(default_factory=list)
    commands: List[ParsedCommand] = field(default_factory=list)
    
    def summary(self) -> str:
        """Краткая сводка для логов"""
        return (
            f"Ролей: {len(self.roles)}, "
            f"Правил: {len(self.rules)}, "
            f"Команд: {len(self.commands)}"
        )


class PromptParser:
    """
    Универсальный парсер markdown-файла с ролями.
    Работает с несколькими форматами разметки.
    """
    
    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()
        self.result = ParsedPrompt()
    
    def parse(self) -> ParsedPrompt:
        """Главный метод — запускает все парсеры"""
        logger.info("🔍 Начинаю парсинг markdown...")
        
        self._parse_constitution()
        self._parse_roles()
        self._parse_commands_table()
        self._parse_commands_inline()
        
        logger.info(f"✅ Парсинг завершён: {self.result.summary()}")
        return self.result
    
    # ---------- ПАРСИНГ КОНСТИТУЦИИ ----------
    
    def _parse_constitution(self):
        """Ищет нумерованный список правил (1. Текст)"""
        # Ищем секцию "КОНСТИТУЦИЯ" или "ПРАВИЛА"
        in_constitution = False
        constitution_lines = []
        
        for i, line in enumerate(self.lines):
            lower = line.lower().strip()
            
            # Начало секции
            if any(marker in lower for marker in [
                "## конституция", "## правила", "# конституция", "# правила"
            ]):
                in_constitution = True
                continue
            
            # Конец секции (новый ## заголовок)
            if in_constitution and line.startswith("## ") and "конституция" not in lower:
                break
            
            if in_constitution:
                constitution_lines.append(line)
        
        # Парсим нумерованные пункты: "1. Текст правила"
        rule_pattern = re.compile(r'^(\d+)[\.\)]\s+(.+)$')
        
        for line in constitution_lines:
            line = line.strip()
            if not line:
                continue
            
            match = rule_pattern.match(line)
            if match:
                number = int(match.group(1))
                text = match.group(2).strip()
                self.result.rules.append(ParsedRule(number=number, text=text))
                logger.debug(f"  📜 Правило {number}: {text[:50]}...")
    
    # ---------- ПАРСИНГ РОЛЕЙ ----------
    
    def _parse_roles(self):
        """Ищет роли по заголовкам ### Роль X: Название"""
        role_pattern = re.compile(
            r'^#{2,3}\s*Роль\s*(\d+)[:：]\s*(.+)$',
            re.IGNORECASE
        )
        
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            match = role_pattern.match(line)
            
            if match:
                role_num = match.group(1)
                role_name = match.group(2).strip()
                full_name = f"Роль {role_num}: {role_name}"
                
                # Собираем блок роли до следующей роли или конца файла
                block_lines = []
                j = i + 1
                while j < len(self.lines):
                    next_line = self.lines[j]
                    # Следующая роль или новый ## заголовок = конец блока
                    if role_pattern.match(next_line) or (
                        next_line.startswith("## ") and not next_line.startswith("###")
                    ):
                        break
                    block_lines.append(next_line)
                    j += 1
                
                # Парсим блок роли
                role = self._parse_role_block(full_name, block_lines)
                self.result.roles.append(role)
                logger.debug(f"  🎭 {role.name} (группа: {role.group_name}, тариф: {role.tier_access})")
                
                i = j
            else:
                i += 1
    
    def _parse_role_block(self, name: str, lines: List[str]) -> ParsedRole:
        """Разбирает текстовый блок одной роли"""
        role = ParsedRole(name=name)
        
        # Собираем весь текст блока
        block_text = "\n".join(lines)
        
        # --- Ищем метаданные ---
        
        # Группа: **Группа:** CODE или Группа: CODE
        group_match = re.search(r'(?:\*\*)?Группа(?:\*\*)?\s*[:：]\s*(\w+)', block_text, re.IGNORECASE)
        if group_match:
            role.group_name = group_match.group(1).upper()
        
        # Тариф: **Тариф:** pro или Тариф: pro
        tier_match = re.search(r'(?:\*\*)?Тариф(?:\*\*)?\s*[:：]\s*(lite|pro|business)', block_text, re.IGNORECASE)
        if tier_match:
            role.tier_access = tier_match.group(1).lower()
        
        # Ключевые слова: **Ключевые слова:** слово1, слово2
        kw_match = re.search(
            r'(?:\*\*)?Ключевые\s*слова(?:\*\*)?\s*[:：]\s*(.+?)(?:\n|$)',
            block_text, re.IGNORECASE | re.DOTALL
        )
        if kw_match:
            role.keywords = kw_match.group(1).strip()
        
        # --- Ищем текст промпта ---
        # Убираем метаданные из текста, оставляем только "тело" промпта
        prompt_lines = []
        in_prompt = False
        
        for line in lines:
            stripped = line.strip()
            
            # Пропускаем пустые и метаданные
            if not stripped:
                if in_prompt:
                    prompt_lines.append(line)
                continue
            
            # Пропускаем строки с метаданными
            if re.match(r'^(?:\*\*)?(?:Группа|Тариф|Ключевые\s*слова)(?:\*\*)?\s*[:：]', stripped, re.IGNORECASE):
                continue
            
            # Пропускаем разделители (---)
            if stripped == '---':
                continue
            
            in_prompt = True
            prompt_lines.append(line)
        
        role.prompt_text = "\n".join(prompt_lines).strip()
        
        # Если keywords не найдены в метаданных — попробуем извлечь из текста
        if not role.keywords:
            # Ищем строки типа "Keywords: ..." или просто список через запятую в начале
            kw_alt = re.search(r'(?:keywords|ключи)\s*[:：]\s*(.+?)(?:\n|$)', block_text, re.IGNORECASE)
            if kw_alt:
                role.keywords = kw_alt.group(1).strip()
        
        return role
    
    # ---------- ПАРСИНГ КОМАНД (ТАБЛИЦА) ----------
    
    def _parse_commands_table(self):
        """Ищет markdown-таблицы с командами"""
        # Ищем строки, похожие на таблицы (начинаются с |)
        table_lines = []
        in_table = False
        
        for line in self.lines:
            stripped = line.strip()
            
            # Начало таблицы
            if stripped.startswith('|') and ('команда' in stripped.lower() or 'кластер' in stripped.lower()):
                in_table = True
            
            if in_table:
                if stripped.startswith('|'):
                    table_lines.append(stripped)
                else:
                    # Конец таблицы
                    break
        
        # Пропускаем заголовок и разделитель (первые 2 строки)
        for line in table_lines[2:]:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) >= 3:
                cluster = cells[0] if cells[0] else "CORE"
                name = cells[1]
                description = cells[2] if len(cells) > 2 else ""
                tier = cells[3].lower() if len(cells) > 3 and cells[3] else "lite"
                
                if name and name.startswith('!'):
                    self.result.commands.append(ParsedCommand(
                        cluster=cluster.upper(),
                        name=name,
                        description=description,
                        tier_access=tier
                    ))
                    logger.debug(f"  ⌨️ Команда {name} ({cluster}, {tier})")
    
    # ---------- ПАРСИНГ КОМАНД (INLINE) ----------
    
    def _parse_commands_inline(self):
        """Ищет команды в формате списка: !КОМАНДА — описание"""
        cmd_pattern = re.compile(r'^[!！]([А-ЯA-Z\s\d]+)\s*[—–-]\s*(.+)$')
        
        for line in self.lines:
            match = cmd_pattern.match(line.strip())
            if match:
                name = "!" + match.group(1).strip()
                desc = match.group(2).strip()
                
                # Проверяем, не добавили ли уже
                if not any(c.name == name for c in self.result.commands):
                    self.result.commands.append(ParsedCommand(
                        name=name,
                        description=desc
                    ))
                    logger.debug(f"  ⌨️ Команда {name} (inline)")


# ---------- УДОБНАЯ ФУНКЦИЯ-ОБЁРТКА ----------

def parse_prompt_file(file_path: str) -> ParsedPrompt:
    """Читает файл и парсит его"""
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    
    parser = PromptParser(text)
    return parser.parse()


def parse_prompt_text(text: str) -> ParsedPrompt:
    """Парсит текст напрямую (для загрузки из Telegram)"""
    parser = PromptParser(text)
    return parser.parse()
