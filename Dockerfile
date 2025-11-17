FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей для weasyprint и rembg
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

    # Установка Python зависимостей с увеличенным таймаутом и retry
    RUN pip install --no-cache-dir --default-timeout=300 --retries=5 -r requirements.txt

# Предзагрузка модели rembg isnet-general-use для ускорения запуска
RUN mkdir -p /root/.u2net && \
    python -c "from rembg import new_session; new_session('isnet-general-use')" && \
    echo "✅ rembg model preloaded"

# Копирование приложения
COPY . .

# Создание директории для шаблонов (если не существует)
RUN mkdir -p templates

# Открытие порта
EXPOSE 8020

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]

