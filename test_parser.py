# test_parser.py — тест парсера на твоём Промпте 1
import asyncio
from parsers.prompt_parser import parse_prompt_file
from db.database import init_db, async_session
from db.models import Role, Rule, Command
from sqlalchemy import select


async def test():
    print("🔍 Парсим prompt_full.txt...")
    parsed = parse_prompt_file("prompt_full.txt")
    print(f"✅ Найдено: {parsed.summary()}")
    
    print("\n--- ПЕРВЫЕ 5 РОЛЕЙ ---")
    for r in parsed.roles[:5]:
        print(f"\n🎭 {r.name}")
        print(f"   Группа: {r.group_name}")
        print(f"   Тариф: {r.tier_access}")
        print(f"   Keywords: {r.keywords}")
        print(f"   Промпт: {r.prompt_text[:80]}...")
    
    print(f"\n--- ПОСЛЕДНИЕ 3 РОЛИ ---")
    for r in parsed.roles[-3:]:
        print(f"\n🎭 {r.name} ({r.group_name}, {r.tier_access})")
        print(f"   Keywords: {r.keywords}")
    
    print(f"\n--- ПРАВИЛА (первые 5) ---")
    for rule in parsed.rules[:5]:
        print(f"  📜 {rule.number}. {rule.text[:100]}...")
    
    print(f"\n--- КОМАНДЫ (первые 10) ---")
    for cmd in parsed.commands[:10]:
        print(f"  ⌨️ {cmd.name} ({cmd.cluster}) — {cmd.description[:60]}...")
    
    print(f"\n💾 Загружаем в БД...")
    await init_db()
    
    async with async_session() as session:
        # Upsert ролей
        for role in parsed.roles:
            result = await session.execute(select(Role).where(Role.name == role.name))
            existing = result.scalar_one_or_none()
            if existing:
                existing.prompt_text = role.prompt_text
                existing.keywords = role.keywords
                existing.group_name = role.group_name
                existing.tier_access = role.tier_access
                existing.is_active = True
                print(f"  🔄 {role.name}")
            else:
                session.add(Role(
                    name=role.name,
                    group_name=role.group_name,
                    prompt_text=role.prompt_text,
                    keywords=role.keywords,
                    tier_access=role.tier_access
                ))
                print(f"  ➕ {role.name}")
        
        # Upsert правил
        for rule in parsed.rules:
            result = await session.execute(select(Rule).where(Rule.number == rule.number))
            existing = result.scalar_one_or_none()
            if existing:
                existing.text = rule.text
            else:
                session.add(Rule(number=rule.number, text=rule.text))
        
        # Upsert команд
        for cmd in parsed.commands:
            result = await session.execute(select(Command).where(Command.name == cmd.name))
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
        print(f"\n✅ Готово! Проверь /roles и /commands в боте.")


if __name__ == "__main__":
    asyncio.run(test())
