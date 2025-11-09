from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import os
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import weasyprint
from io import BytesIO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import logging

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF Outfit Generator")

# Загрузка Jinja2 шаблонов
env = Environment(loader=FileSystemLoader('templates'))

# Pydantic модели для валидации
class Item(BaseModel):
    id: Optional[int] = None
    name: str
    image_url: str
    link: str
    price: str

class Outfit(BaseModel):
    outfit_description: str
    items: List[Item]

class OutfitRequest(BaseModel):
    email: EmailStr
    outfit: Outfit

class Response(BaseModel):
    status: str
    message: str

def generate_pdf(html_content: str) -> BytesIO:
    """Генерирует PDF из HTML контента"""
    import threading
    import time
    
    try:
        # Настройки для оптимизации скорости генерации PDF
        # Используем url_fetcher для контроля загрузки изображений с таймаутом
        def url_fetcher(url):
            import urllib.request
            import socket
            from PIL import Image
            socket.setdefaulttimeout(3)  # Таймаут 3 секунды на загрузку каждого изображения
            try:
                logger.info(f"Загрузка изображения: {url[:80]}...")
                response = urllib.request.urlopen(url, timeout=3)
                image_data = response.read()
                content_type = response.headers.get('Content-Type', '')
                logger.info(f"Изображение загружено: {len(image_data)} bytes, тип: {content_type}")
                
                # Конвертируем и оптимизируем изображения
                try:
                    img = Image.open(BytesIO(image_data))
                    # Конвертируем RGBA/LA/P в RGB
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    # Уменьшаем размер изображения для ускорения PDF генерации
                    # Максимальный размер 400x400 для карточек товаров
                    max_size = 400
                    if img.width > max_size or img.height > max_size:
                        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                        logger.info(f"Изображение уменьшено до {img.width}x{img.height}")
                    # Сохраняем как JPEG с оптимизацией
                    output = BytesIO()
                    img.save(output, format='JPEG', quality=75, optimize=True)
                    image_data = output.getvalue()
                    content_type = 'image/jpeg'
                    logger.info(f"Изображение оптимизировано: {len(image_data)} bytes")
                except Exception as conv_error:
                    logger.warning(f"Не удалось обработать изображение: {str(conv_error)}, используем оригинал")
                
                return {
                    'string': image_data,
                    'mime_type': content_type or 'image/jpeg'
                }
            except Exception as e:
                logger.warning(f"Не удалось загрузить изображение {url}: {str(e)}")
                # Возвращаем пустое изображение если не удалось загрузить
                return {
                    'string': b'',
                    'mime_type': 'image/jpeg'
                }
        
        logger.info("Начало генерации PDF...")
        html = weasyprint.HTML(
            string=html_content,
            url_fetcher=url_fetcher
        )
        
        # Генерация PDF с таймаутом
        pdf_bytes = None
        error_occurred = threading.Event()
        error_message = [None]
        start_time = time.time()
        
        def generate():
            nonlocal pdf_bytes
            try:
                logger.info("Вызов html.write_pdf()...")
                pdf_bytes = html.write_pdf()
                elapsed = time.time() - start_time
                logger.info(f"PDF сгенерирован за {elapsed:.2f} сек, размер: {len(pdf_bytes)} bytes")
            except Exception as e:
                error_message[0] = str(e)
                error_occurred.set()
                logger.error(f"Ошибка в потоке генерации: {str(e)}", exc_info=True)
        
        # Запускаем генерацию в отдельном потоке
        thread = threading.Thread(target=generate)
        thread.daemon = True
        thread.start()
        thread.join(timeout=120)  # Увеличиваем таймаут до 120 секунд
        
        elapsed = time.time() - start_time
        logger.info(f"Поток завершен, прошло {elapsed:.2f} секунд")
        
        if thread.is_alive():
            logger.error(f"Таймаут генерации PDF (120 секунд), прошло {elapsed:.2f} сек")
            raise TimeoutError("Генерация PDF превысила лимит времени (120 секунд)")
        
        if error_occurred.is_set():
            raise Exception(error_message[0] or "Неизвестная ошибка генерации PDF")
        
        if pdf_bytes is None:
            raise Exception("PDF не был сгенерирован")
        
        return BytesIO(pdf_bytes)
    except TimeoutError as e:
        logger.error(f"Таймаут генерации PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Генерация PDF заняла слишком много времени")
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка генерации PDF: {str(e)}")

def send_email_with_pdf(email_to: str, pdf_buffer: BytesIO, outfit_description: str):
    """Отправляет email с PDF вложением через Gmail SMTP"""
    try:
        gmail_email = os.getenv("GMAIL_EMAIL")
        gmail_password = os.getenv("GMAIL_PASSWORD")
        
        if not gmail_email or not gmail_password:
            raise ValueError("GMAIL_EMAIL и GMAIL_PASSWORD должны быть установлены в переменных окружения")
        
        # Создание сообщения
        msg = MIMEMultipart()
        msg['From'] = gmail_email
        msg['To'] = email_to
        msg['Subject'] = f"Ваш outfit: {outfit_description}"
        
        # Текст письма
        body = f"Здравствуйте!\n\nВаш outfit '{outfit_description}' готов. PDF файл с товарами прикреплен к письму."
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Прикрепление PDF
        pdf_buffer.seek(0)
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_buffer.read())
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename=outfit.pdf'
        )
        msg.attach(part)
        
        # Диагностика сети перед отправкой
        import socket
        try:
            logger.info("Проверка DNS резолвинга smtp.gmail.com...")
            socket.gethostbyname('smtp.gmail.com')
            logger.info("DNS резолвинг успешен")
        except socket.gaierror as e:
            logger.error(f"Ошибка DNS резолвинга: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Не удалось разрешить имя smtp.gmail.com. Проверьте DNS настройки Docker. Ошибка: {str(e)}"
            )
        
        # Отправка через SMTP с таймаутом и обработкой ошибок
        # Пробуем разные порты и методы подключения
        smtp_configs = [
            ('smtp.gmail.com', 587, 'TLS'),
            ('smtp.gmail.com', 465, 'SSL'),
        ]
        
        server = None
        last_error = None
        
        for host, port, method in smtp_configs:
            try:
                logger.info(f"Попытка подключения к {host}:{port} ({method})...")
                if method == 'SSL':
                    import ssl
                    server = smtplib.SMTP_SSL(host, port, timeout=30)
                else:
                    server = smtplib.SMTP(host, port, timeout=30)
                logger.info(f"Соединение с {host}:{port} установлено")
                break
            except (OSError, smtplib.SMTPException) as e:
                logger.warning(f"Не удалось подключиться к {host}:{port}: {str(e)}")
                last_error = e
                continue
        
        if server is None:
            raise OSError(f"Не удалось подключиться ни к одному SMTP серверу. Последняя ошибка: {last_error}")
        
        try:
            # TLS нужен только для порта 587, для 465 уже используется SSL
            if hasattr(server, 'starttls'):
                logger.info("Запуск TLS...")
                server.starttls()
                logger.info("TLS установлен")
            logger.info("Выполнение входа...")
            server.login(gmail_email, gmail_password)
            logger.info("Вход выполнен, отправка письма...")
            text = msg.as_string()
            server.sendmail(gmail_email, email_to, text)
            server.quit()
            logger.info(f"Письмо успешно отправлено на {email_to}")
        except OSError as e:
            logger.error(f"Ошибка сети при отправке email: {str(e)}")
            # Не поднимаем исключение, так как это выполняется в фоне
            # Просто логируем ошибку
            logger.error(f"Детали ошибки сети: {type(e).__name__}: {str(e)}")
            logger.error(f"PDF НЕ был отправлен на {email_to} из-за сетевой ошибки")
            return  # Выходим, не логируя успех
        except smtplib.SMTPException as e:
            logger.error(f"Ошибка SMTP: {str(e)}")
            logger.error(f"Детали ошибки SMTP: {type(e).__name__}: {str(e)}")
            logger.error(f"PDF НЕ был отправлен на {email_to} из-за ошибки SMTP")
            return  # Выходим, не логируя успех
        
        logger.info(f"PDF успешно отправлен на {email_to}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки email: {str(e)}", exc_info=True)
        # Не поднимаем исключение, так как это выполняется в фоне
        # PDF уже сгенерирован и ответ отправлен клиенту

def render_html_template(outfit: Outfit) -> str:
    """Рендерит HTML шаблон с данными outfit"""
    try:
        template = env.get_template('outfit.html')
        
        # Разбиваем товары на страницы по 8 штук
        items_per_page = 8
        pages = []
        for i in range(0, len(outfit.items), items_per_page):
            page_items = outfit.items[i:i + items_per_page]
            pages.append(page_items)
        
        html_content = template.render(
            outfit_description=outfit.outfit_description,
            pages=pages
        )
        return html_content
    except Exception as e:
        logger.error(f"Ошибка рендеринга шаблона: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка рендеринга шаблона: {str(e)}")

@app.post("/generate-pdf", response_model=Response)
async def generate_pdf_endpoint(request: OutfitRequest):
    """
    Генерирует PDF с товарами и отправляет на указанный email
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    try:
        # Валидация данных
        if not request.outfit.items:
            raise HTTPException(status_code=400, detail="Список товаров не может быть пустым")
        
        logger.info(f"Начало обработки запроса для {request.email}, товаров: {len(request.outfit.items)}")
        
        # Рендеринг HTML (быстрая операция)
        html_content = render_html_template(request.outfit)
        logger.info("HTML шаблон отрендерен")
        
        # Генерация PDF в отдельном потоке для неблокирующей работы
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=2) as executor:
            pdf_buffer = await loop.run_in_executor(executor, generate_pdf, html_content)
        logger.info("PDF сгенерирован")
        
        # Копируем данные из буфера для отправки в фоне
        pdf_buffer.seek(0)
        pdf_data = pdf_buffer.read()
        pdf_buffer_copy = BytesIO(pdf_data)
        
        # Отправка email в отдельном потоке (не блокируем ответ)
        async def send_email_async():
            try:
                with ThreadPoolExecutor() as executor:
                    await loop.run_in_executor(
                        executor,
                        send_email_with_pdf,
                        request.email,
                        pdf_buffer_copy,
                        request.outfit.outfit_description
                    )
                logger.info("Email отправлен")
            except Exception as e:
                logger.error(f"Ошибка при отправке email в фоне: {str(e)}")
        
        # Запускаем отправку email в фоне, не ждем завершения
        asyncio.create_task(send_email_async())
        
        # Возвращаем ответ сразу после генерации PDF
        return Response(
            status="success",
            message=f"PDF генерируется и будет отправлен на {request.email}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@app.get("/")
async def root():
    return {"message": "PDF Outfit Generator API"}

@app.get("/health")
async def health():
    return {"status": "ok"}

