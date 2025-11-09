# PDF Outfit Generator Server

Сервер для генерации PDF файлов с каталогом товаров и отправки их на email.

## Описание

FastAPI сервер, который принимает данные об outfit с товарами, генерирует PDF из HTML шаблона с карточками товаров (4x2 на странице) и отправляет PDF на указанный email через Gmail SMTP.

## Установка

### Для Docker (рекомендуется)

Просто создайте файл `.env` в корне проекта (см. ниже) и используйте docker-compose.

### Для локальной установки

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` в корне проекта:
```
GMAIL_EMAIL=your-email@gmail.com
GMAIL_PASSWORD=your-app-password
```

**Важно:** Для Gmail необходимо использовать пароль приложения, а не обычный пароль аккаунта.

### Как получить пароль приложения Gmail:

1. Включите двухфакторную аутентификацию в настройках Google аккаунта
2. Перейдите в [Управление аккаунтом Google](https://myaccount.google.com/)
3. Выберите "Безопасность" → "Пароли приложений"
4. Создайте новый пароль приложения для "Почта"
5. Используйте этот пароль в `.env` файле

## Запуск

### Вариант 1: Docker (рекомендуется)

1. Создайте файл `.env` в корне проекта:
```
GMAIL_EMAIL=your-email@gmail.com
GMAIL_PASSWORD=your-app-password
```

2. Запустите через docker-compose:
```bash
docker-compose up --build
```

Или через Docker напрямую:
```bash
docker build -t pdf-generator .
docker run -p 8020:8020 --env-file .env pdf-generator
```

Сервер будет доступен по адресу: `http://localhost:8020`

### Вариант 2: Локальный запуск

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Запустите сервер:
```bash
uvicorn main:app --host 0.0.0.0 --port 8020 --reload
```

Сервер будет доступен по адресу: `http://localhost:8020`

## API

### POST /generate-pdf

Генерирует PDF с товарами и отправляет на указанный email.

**Тело запроса:**
```json
{
  "email": "user@example.com",
  "outfit": {
    "outfit_description": "Летний образ",
    "items": [
      {
        "id": 1,
        "name": "Футболка",
        "image_url": "https://example.com/image.jpg",
        "link": "https://example.com/product",
        "price": "1999 руб"
      }
    ]
  }
}
```

**Ответ:**
```json
{
  "status": "success",
  "message": "PDF успешно отправлен на user@example.com"
}
```

### GET /

Информация о сервере.

### GET /health

Проверка работоспособности сервера.

## Структура проекта

```
collage/
├── main.py              # FastAPI приложение
├── templates/
│   └── outfit.html      # HTML шаблон с карточками товаров
├── requirements.txt     # Зависимости Python
├── Dockerfile           # Docker образ
├── docker-compose.yml   # Docker Compose конфигурация
├── .dockerignore        # Исключения для Docker
├── .env                 # Переменные окружения (создать вручную)
└── README.md            # Документация
```

## Особенности

- 8 карточек товаров на одной странице (4 колонки × 2 ряда)
- Автоматическое разбиение на несколько страниц, если товаров больше 8
- Кликабельные изображения товаров (ссылки на товары)
- Отправка PDF на email через Gmail SMTP
- Валидация входных данных через Pydantic

