# ============================================
# ПАРСЕР MARKDOWN-ФАЙЛА С РОЛЯМИ (v4 — фикс для твоего Промпта 1)
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
            group_match = re.search(r'ГРУПП[АУ]\s*(\d+)', line, re.IGNORECASE)
            if group_match and ('ЗАГРУЗИ' in line or 'РОЛИ' in line or 'ГРУППА' in line):
                self.current_group = f"GROUP_{group_match.group(1)}"
                i += 1
                continue
            
            # --- ПАРСИНГ ПРАВИЛ (мягкий regex) ---
            # Ловит: **Правило №1 — Название** и **Правило №9 — (УПРАЗДНЕНО...)**
            rule_match = re.match(r'^\*\*Правило\s+№(\d+)\s+—\s+(.+?)\*\*', line)
            if rule_match:
                number = int(rule_match.group(1))
                rule_lines = []
                j = i + 1
                while j < len(self.lines):
                    nl = self.lines[j]
                    if (re.match(r'^\*\*Правило', nl) or 
                        re.match(r'^#{2,3}\s', nl) or
                        '[MULTIPART' in nl or
                        'ЧАСТЬ' in nl and 'ГОТОВА' in nl or
                        nl.strip() == '---'):
                        break
                    rule_lines.append(nl)
                    j += 1
                rule_text = ' '.join(rule_lines).strip()
                if rule_text:
                    self.result.rules.append(ParsedRule(number=number, text=rule_text))
                i = j
                continue
            
            # --- ПАРСИНГ РОЛЕЙ (3 формата) ---
            role = None
            
            # Формат 1: "1. **Роль 1 — Название** (что-то)"
            m1 = re.match(r'^(\d+)\.\s+\*\*Роль\s+(\d+)\s+—\s+(.+?)\*\*(?:\s+—\s+(.+?))?(?:\s*\(.+?\))?\s*$', line)
            if m1:
                role_num = m1.group(2)
                role_name = m1.group(3).strip()
                role = self._parse_role_body(i, role_num, role_name)
            
            # Формат 2: "**38. Роль 38 — Название**" (двойная звёздочка в начале)
            if not role:
                m2 = re.match(r'^\*\*(\d+)\.\s+Роль\s+(\d+)\s+—\s+(.+?)\*\*(?:\s*\(.+?\))?\s*$', line)
                if m2:
                    role_num = m2.group(2)
                    role_name = m2.group(3).strip()
                    role = self._parse_role_body(i, role_num, role_name)
            
            # Формат 3: "**Роль 1 — Название**" (без номера строки)
            if not role:
                m3 = re.match(r'^\s*\*\*Роль\s+(\d+)\s+—\s+(.+?)\*\*(?:\s+—\s+(.+?))?(?:\s*\(.+?\))?\s*$', line)
                if m3:
                    role_num = m3.group(1)
                    role_name = m3.group(2).strip()
                    role = self._parse_role_body(i, role_num, role_name)
            
            if role:
                self.result.roles.append(role)
                logger.debug(f"  🎭 {role.name} ({role.group_name})")
                # Пропускаем строки тела роли
                j = i + 1
                while j < len(self.lines):
                    nl = self.lines[j]
                    if (re.match(r'^(\d+\.\s+)?\*\*Роль\s+\d+', nl) or 
                        re.match(r'^\*\*(\d+\.\s+)?Роль\s+\d+', nl) or
                        re.match(r'^\*\*Правило', nl) or
                        re.match(r'^#{2,3}\s', nl) or
                        '[MULTIPART' in nl or
                        nl.strip() == '---'):
                        break
                    j += 1
                i = j
                continue
            
            # --- ПАРСИНГ КЛАСТЕРОВ КОМАНД ---
            cluster_match = re.match(r'^\*\*КЛАСТЕР\s+(\d+):\s+(.+?)\*\*', line)
            if cluster_match:
                self.current_cluster = f"CLUSTER_{cluster_match.group(1)}"
                i += 1
                continue
            
            # --- ПАРСИНГ КОМАНД (упрощённый) ---
            # Ловит: `!КОМАНДА` — описание, `!КОМАНДА [arg]` — описание, `/команда` — описание
            cmd_match = re.match(r'^\d+\.\s+\`([!/]?[A-Z_А-ЯЁ0-9\s]+)\`(?:\s+\[[^\]]+\])?\s*—\s*(.+)$', line)
            if cmd_match:
                name = cmd_match.group(1).strip()
                if not name.startswith('!') and not name.startswith('/'):
                    name = '!' + name  # ОБУЧИ, ПЛАН → !ОБУЧИ, !ПЛАН
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
            
            # --- КОМАНДЫ С ДВОЕТОЧИЕМ (ШАБЛОН, ПЕСОЧНИЦА, ВЕРСИЯ, ПЕРЕНОС) ---
            cmd_colon = re.match(r'^\d+\.\s+\`([!/]?[A-Z_А-ЯЁ0-9\s]+(?:\s+\[[^\]]+\])*)\`\s*:\s*$', line)
            if cmd_colon:
                name = cmd_colon.group(1).strip()
                if not name.startswith('!') and not name.startswith('/'):
                    name = '!' + name
                # Собираем описание из следующих строк (подпункты)
                desc_lines = []
                j = i + 1
                while j < len(self.lines):
                    nl = self.lines[j]
                    if (re.match(r'^\d+\.', nl) or 
                        re.match(r'^\*\*КЛАСТЕР', nl) or
                        re.match(r'^#{2,3}\s', nl) or
                        '[MULTIPART' in nl or
                        nl.strip() == '---'):
                        break
                    desc_lines.append(nl.strip())
                    j += 1
                desc = ' '.join(desc_lines).strip() or name
                tier = self._detect_tier(desc)
                self.result.commands.append(ParsedCommand(
                    cluster=self.current_cluster,
                    name=name,
                    description=desc[:200],
                    tier_access=tier
                ))
                i = j
                continue
            
            i += 1
        
        logger.info(f"✅ Парсинг завершён: {self.result.summary()}")
        return self.result
    
    def _parse_role_body(self, start_idx: int, role_num: str, role_name: str) -> ParsedRole:
        """Собирает тело роли и возвращает объект ParsedRole"""
        full_name = f"Роль {role_num}: {role_name}"
        prompt_lines = []
        
        j = start_idx + 1
        while j < len(self.lines):
            nl = self.lines[j]
            if (re.match(r'^(\d+\.\s+)?\*\*Роль\s+\d+', nl) or 
                re.match(r'^\*\*(\d+\.\s+)?Роль\s+\d+', nl) or
                re.match(r'^\*\*Правило', nl) or
                re.match(r'^#{2,3}\s', nl) or
                '[MULTIPART' in nl or
                nl.strip() == '---'):
                break
            prompt_lines.append(nl)
            j += 1
        
        prompt_text = '\n'.join(prompt_lines).strip()
        keywords = self._generate_keywords(role_name, prompt_text)
        tier = self._detect_tier(prompt_text)
        
        return ParsedRole(
            name=full_name,
            group_name=self.current_group,
            prompt_text=prompt_text,
            keywords=keywords,
            tier_access=tier
        )
    
    def _generate_keywords(self, role_name: str, prompt_text: str) -> str:
        name_words = re.findall(r'[А-Яа-яA-Za-z]{4,}', role_name)
        name_words = [w.lower() for w in name_words]
        
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
            'разрешает', 'запрещает', 'требует', 'предлагает', 'рекомендует',
            'утверждает', 'отклоняет', 'принимает', 'передаёт', 'получает',
            'обрабатывает', 'фиксирует', 'логирует', 'уведомляет', 'предупреждает',
            'информирует', 'сообщает', 'докладывает', 'отчитывается', 'при', 'по',
            'для', 'через', 'после', 'перед', 'время', 'место', 'поручения',
            'вопросам', 'вопросах', 'вопросы', 'вопрос', 'вопросов'
        }
        text_words = [w.lower() for w in text_words if w.lower() not in stop_words]
        
        all_words = []
        seen = set()
        for w in name_words + text_words:
            if w not in seen and len(w) > 3:
                seen.add(w)
                all_words.append(w)
        
        return ', '.join(all_words[:12])
    
    def _detect_tier(self, text: str) -> str:
        lower = text.lower()
        if any(x in lower for x in ['доступно в pro и бизнес', 'pro и бизнес', 'pro/бизнес', 'доступен только в pro']):
            return 'pro'
        if any(x in lower for x in ['доступно только в бизнес', 'только в бизнес-версии', 'доступен только в бизнес']):
            return 'business'
        return 'business'


def parse_prompt_file(file_path: str) -> ParsedPrompt:
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    parser = PromptParser(text)
    return parser.parse()


def parse_prompt_text(text: str) -> ParsedPrompt:
    parser = PromptParser(text)
    return parser.parse()
