# ============================================
# ПАРСЕР MARKDOWN-ФАЙЛА С РОЛЯМИ (v3 — под твой Промпт 1)
# ============================================

import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ParsedRole:
    name: str
    group_name: str = "CORE"
    prompt_text: str = ""
    keywords: str = ""
    tier_access: str = "business"
    is_active: bool = True


@dataclass
class ParsedRule:
    number: int
    text: str
    is_active: bool = True


@dataclass
class ParsedCommand:
    cluster: str = "CORE"
    name: str = ""
    description: str = ""
    tier_access: str = "lite"


@dataclass
class ParsedPrompt:
    roles: List[ParsedRole] = field(default_factory=list)
    rules: List[ParsedRule] = field(default_factory=list)
    commands: List[ParsedCommand] = field(default_factory=list)
    
    def summary(self) -> str:
        return f"Ролей: {len(self.roles)}, Правил: {len(self.rules)}, Команд: {len(self.commands)}"


class PromptParser:
    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()
        self.result = ParsedPrompt()
        self.current_group = "CORE"
        self.current_cluster = "CORE"
    
    def parse(self) -> ParsedPrompt:
        logger.info("🔍 Начинаю парсинг Промпта 1...")
        
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            
            # --- ОПРЕДЕЛЕНИЕ ГРУППЫ РОЛЕЙ ---
            # "ЗАГРУЗИ В ПАМЯТЬ ГРУППУ 2 (...)" или "ЯДЕРНЫЕ РОЛИ (ГРУППА 1...)"
            group_match = re.search(r'ГРУПП[АУ]\s*(\d+)', line, re.IGNORECASE)
            if group_match and ('ЗАГРУЗИ' in line or 'РОЛИ' in line or 'ГРУППА' in line):
                self.current_group = f"GROUP_{group_match.group(1)}"
                i += 1
                continue
            
            # --- ПАРСИНГ ПРАВИЛ ---
            rule_match = re.match(r'^\*\*Правило\s+№(\d+)\s+—\s+(.+?)\*\*\s*$', line)
            if rule_match:
                number = int(rule_match.group(1))
                # Собираем текст правила до следующего правила/заголовка/разделителя
                rule_lines = []
                j = i + 1
                while j < len(self.lines):
                    nl = self.lines[j]
                    if (re.match(r'^\*\*Правило', nl) or 
                        re.match(r'^#{2,3}\s', nl) or
                        '[MULTIPART' in nl or
                        nl.strip() == '---'):
                        break
                    rule_lines.append(nl)
                    j += 1
                rule_text = ' '.join(rule_lines).strip()
                if rule_text:
                    self.result.rules.append(ParsedRule(number=number, text=rule_text))
                i = j
                continue
            
            # --- ПАРСИНГ РОЛЕЙ ---
            # Формат: "1. **Роль 1 — Название**" или "**Роль 1 — Название**"
            role_match = re.match(r'^(\d+)\.\s+\*\*Роль\s+(\d+)\s+—\s+(.+?)\*\*(?:\s+—\s+(.+?))?\s*$', line)
            if not role_match:
                role_match = re.match(r'^\s*\*\*Роль\s+(\d+)\s+—\s+(.+?)\*\*(?:\s+—\s+(.+?))?\s*$', line)
            
            if role_match:
                groups = role_match.groups()
                if len(groups) >= 4 and groups[0].isdigit() and groups[1].isdigit():
                    # Формат: "1. **Роль 1 — Название**"
                    role_num = groups[1]
                    role_name = groups[2].strip()
                else:
                    # Формат: "**Роль 1 — Название**"
                    role_num = groups[0]
                    role_name = groups[1].strip()
                
                full_name = f"Роль {role_num}: {role_name}"
                
                # Собираем текст роли
                prompt_lines = []
                j = i + 1
                while j < len(self.lines):
                    nl = self.lines[j]
                    if (re.match(r'^(\d+\.\s+)?\*\*Роль\s+\d+', nl) or 
                        re.match(r'^\*\*Правило', nl) or
                        re.match(r'^#{2,3}\s', nl) or
                        '[MULTIPART' in nl or
                        nl.strip() == '---'):
                        break
                    prompt_lines.append(nl)
                    j += 1
                
                prompt_text = '\n'.join(prompt_lines).strip()
                
                # Авто-генерация keywords
                keywords = self._generate_keywords(role_name, prompt_text)
                
                # Определяем тариф по пометкам в тексте
                tier = self._detect_tier(prompt_text)
                
                self.result.roles.append(ParsedRole(
                    name=full_name,
                    group_name=self.current_group,
                    prompt_text=prompt_text,
                    keywords=keywords,
                    tier_access=tier
                ))
                logger.debug(f"  🎭 {full_name} ({self.current_group}, {tier})")
                i = j
                continue
            
            # --- ПАРСИНГ КЛАСТЕРОВ КОМАНД ---
            cluster_match = re.match(r'^\*\*КЛАСТЕР\s+(\d+):\s+(.+?)\*\*', line)
            if cluster_match:
                self.current_cluster = f"CLUSTER_{cluster_match.group(1)}"
                i += 1
                continue
            
            # --- ПАРСИНГ КОМАНД ---
            # Формат: "1. `!ЖМИ` — описание" или "67. `!ПЕСОЧНИЦА [действие]`:"
            cmd_match = re.match(r'^\d+\.\s+\`!([A-Z_А-ЯЁ0-9\s]+)\`(?:\s+\[[^\]]+\])?\s*—\s*(.+)$', line)
            if cmd_match:
                name = "!" + cmd_match.group(1).strip()
                desc = cmd_match.group(2).strip()
                tier = self._detect_tier(desc)
                self.result.commands.append(ParsedCommand(
                    cluster=self.current_cluster,
                    name=name,
                    description=desc,
                    tier_access=tier
                ))
                i += 1
                continue
            
            i += 1
        
        logger.info(f"✅ Парсинг завершён: {self.result.summary()}")
        return self.result
    
    def _generate_keywords(self, role_name: str, prompt_text: str) -> str:
        """Авто-генерация keywords из названия и текста роли"""
        # Слова из названия (длиной > 3)
        name_words = re.findall(r'[А-Яа-яA-Za-z]{4,}', role_name)
        name_words = [w.lower() for w in name_words]
        
        # Значимые слова из начала текста роли (исключаем стоп-слова)
        text_words = re.findall(r'[А-Яа-яA-Za-z]{5,}', prompt_text[:600])
        stop_words = {
            'который', 'которая', 'которые', 'этот', 'эта', 'эти', 'такой', 'такая',
            'все', 'весь', 'каждый', 'любой', 'другой', 'самый', 'очень', 'только',
            'может', 'нужно', 'следует', 'является', 'входит', 'подчиняется', 'роль',
            'функции', 'ответственность', 'зона', 'помощь', 'помогает', 'проводит',
            'контроль', 'управление', 'анализ', 'проверка', 'работает', 'связке',
            'взаимодействие', 'обеспечение', 'поддержание', 'осуществление',
            'предоставление', 'выполнение', 'осуществляет', 'поддерживает',
            'предоставляет', 'выполняет', 'является', 'входит', 'состоит',
            'включает', 'содержит', 'имеет', 'позволяет', 'обеспечивает',
            'отвечает', 'следит', 'ведёт', 'готовит', 'помогает', 'проверяет',
            'контролирует', 'управляет', 'анализирует', 'разрабатывает', 'создаёт',
            'формирует', 'определяет', 'устанавливает', 'назначает', 'делегирует',
            'эскалирует', 'инициирует', 'запускает', 'останавливает', 'блокирует',
            'разрешает', 'запрещает', 'требует', 'разрешает', 'предлагает',
            'рекомендует', 'утверждает', 'отклоняет', 'принимает', 'передаёт',
            'получает', 'обрабатывает', 'фиксирует', 'логирует', 'уведомляет',
            'предупреждает', 'информирует', 'сообщает', 'докладывает', 'отчитывается'
        }
        text_words = [w.lower() for w in text_words if w.lower() not in stop_words]
        
        # Объединяем, убираем дубликаты, берём топ-12
        all_words = []
        seen = set()
        for w in name_words + text_words:
            if w not in seen and len(w) > 3:
                seen.add(w)
                all_words.append(w)
        
        return ', '.join(all_words[:12])
    
    def _detect_tier(self, text: str) -> str:
        """Определяет тариф по пометкам в тексте"""
        lower = text.lower()
        if any(x in lower for x in ['доступно в pro и бизнес', 'доступно в pro/бизнес', 'доступен только в pro', 'pro и бизнес', 'pro/бизнес']):
            return 'pro'
        if any(x in lower for x in ['доступно только в бизнес', 'доступен только в бизнес', 'только в бизнес-версии']):
            return 'business'
        return 'business'  # По умолчанию все роли = business (настраивается в /admin)


def parse_prompt_file(file_path: str) -> ParsedPrompt:
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    parser = PromptParser(text)
    return parser.parse()


def parse_prompt_text(text: str) -> ParsedPrompt:
    parser = PromptParser(text)
    return parser.parse()
