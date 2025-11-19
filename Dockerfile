# Dockerfile
FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем символическую ссылку, чтобы логи и БД сохранялись вне контейнера
# (но в volume они и так будут сохраняться)
RUN mkdir -p logs
RUN mkdir -p database

# Убедимся, что скрипт исполняемый
RUN chmod +x modules/tutorBot.py

# Запуск бота
CMD ["python", "modules/tutorBot.py"]