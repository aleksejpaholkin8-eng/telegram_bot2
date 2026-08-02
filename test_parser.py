# test_parser.py — временный скрипт для проверки парсера
import asyncio
from parsers.prompt_parser import parse_prompt_file
from db.database import init_db, async_session
from db.models import Role, Rule, Command
from sqlalchemy import select


async def test():
    # 1. Парсим файл
    print("🔍 Парсим test_prompt.md...")
    parsed = parse_prompt_file("test_prompt.md")
    print(f"✅ Найдено: {parsed.summary()}")
    
    # 2. Показываем детали
    print("\n--- РОЛИ ---")
    for r in parsed.roles:
        print(f"  🎭 {r.name}")
        print(f"     Группа: {r.group_name}")
        print(f"     Тариф: {r.tier_access}")
        print(f"     Keywords: {r.keywords}")
        print(f"     Промпт: {r.prompt_text[:60]}...")
        print()
    
    print("--- ПРАВИЛА ---")
    for rule in parsed.rules:
        print(f"  📜 {rule.number}. {rule.text}")
    
    print("\n--- КОМАНДЫ ---")
    for cmd in parsed.commands:
        print(f"  ⌨️ {cmd.name} ({cmd.cluster}, {cmd.tier_access}) — {cmd.description}")
    
    # 3. Загружаем в БД (upsert)
    print("\n💾 Загружаем в БД...")
    await init_db()
    
    async with async_session() as session:
        for role in parsed.roles:
            result = await session.execute(
                select(Role).where(Role.name == role.name)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.prompt_text = role.prompt_text
                existing.keywords = role.keywords
                existing.group_name = role.group_name
                existing.tier_access = role.tier_access
                print(f"  🔄 Обновлена: {role.name}")
            else:
                new = Role(
                    name=role.name,
                    group_name=role.group_name,
                    prompt_text=role.prompt_text,
                    keywords=role.keywords,
                    tier_access=role.tier_access
                )
                session.add(new)
                print(f"  ➕ Добавлена: {role.name}")
        
        for rule in parsed.rules:
            result = await session.execute(
                select(Rule).where(Rule.number == rule.number)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.text = rule.text
            else:
                session.add(Rule(number=rule.number, text=rule.text))
        
        for cmd in parsed.commands:
            result = await session.execute(
                select(Command).where(Command.name == cmd.name)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.description = cmd.description
                existing.cluster = cmd.cluster
                existing.tier_access = cmd.tier_access
            else:
                session.add(Command(
                    cluster=cmd.cluster,
                    name=cmd.name,
                    description=cmd.description,
                    tier_access=cmd.tier_access
                ))
        
        await session.commit()
        print("✅ Готово! Проверь /roles и /commands в боте.")


if __name__ == "__main__":
    asyncio.run(test())
