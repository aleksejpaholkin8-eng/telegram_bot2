# Это инструкция для Railway: как собрать и запустить бота
# Docker — это технология, которая упаковывает код в "контейнер"

# Берём готовый образ с Python 3.11
FROM python:3.11-slim

# Отключаем буферизацию логов (чтобы ошибки видны сразу)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Создаём рабочую папку внутри контейнера
WORKDIR /app

# Сначала копируем только файл с зависимостями (для кэширования)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Теперь копируем весь остальной код
COPY . .

# Команда, которую Railway выполнит для запуска бота
CMD ["python", "-m", "bot.main"]
