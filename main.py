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
import urllib.request
import base64
from PIL import Image
from background_remover import cutout_rgba
from layout_agent import get_item_labels
from firebase_storage import upload_image_to_firebase
import time

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
    category: Optional[str] = None

class Outfit(BaseModel):
    outfit_description: str
    items: List[Item]

class OutfitRequest(BaseModel):
    email: EmailStr
    outfit: Outfit

class Response(BaseModel):
    status: str
    message: str


def generate_collage_pdf(html_content: str) -> BytesIO:
    """Генерирует PDF коллажа с квадратным размером страницы 2500×2500px"""
    import threading
    import time
    
    try:
        # Настройки для оптимизации скорости генерации PDF
        # Используем url_fetcher для контроля загрузки изображений с таймаутом
        def url_fetcher(url):
            import urllib.request
            import socket
            from PIL import Image
            socket.setdefaulttimeout(10)  # Увеличенный таймаут для коллажа
            try:
                logger.info(f"Загрузка изображения для коллажа: {url[:80]}...")
                response = urllib.request.urlopen(url, timeout=10)
                image_data = response.read()
                content_type = response.headers.get('Content-Type', '')
                logger.info(f"Изображение загружено: {len(image_data)} bytes, тип: {content_type}")
                
                # Для коллажа НЕ уменьшаем изображения - используем полный размер
                # Важно: сохраняем прозрачность для изображений без фона
                try:
                    img = Image.open(BytesIO(image_data))
                    
                    # Если изображение RGBA (с прозрачностью), сохраняем как есть
                    if img.mode == 'RGBA':
                        # Сохраняем как PNG с прозрачностью
                        output = BytesIO()
                        img.save(output, format='PNG', optimize=True)
                        image_data = output.getvalue()
                        content_type = 'image/png'
                        logger.info(f"Изображение RGBA обработано для коллажа (с прозрачностью): {len(image_data)} bytes")
                    elif img.mode in ('LA', 'P'):
                        # Конвертируем в RGBA для сохранения прозрачности
                        img = img.convert('RGBA')
                        output = BytesIO()
                        img.save(output, format='PNG', optimize=True)
                        image_data = output.getvalue()
                        content_type = 'image/png'
                        logger.info(f"Изображение конвертировано в RGBA для коллажа: {len(image_data)} bytes")
                    else:
                        # RGB изображения конвертируем в RGBA (без прозрачности, но формат правильный)
                        img = img.convert('RGBA')
                        output = BytesIO()
                        img.save(output, format='PNG', optimize=True)
                        image_data = output.getvalue()
                        content_type = 'image/png'
                        logger.info(f"Изображение обработано для коллажа: {len(image_data)} bytes")
                except Exception as conv_error:
                    logger.warning(f"Не удалось обработать изображение: {str(conv_error)}, используем оригинал")
                
                return {
                    'string': image_data,
                    'mime_type': content_type or 'image/png'
                }
            except Exception as e:
                logger.warning(f"Не удалось загрузить изображение {url}: {str(e)}")
                # Возвращаем пустое изображение если не удалось загрузить
                return {
                    'string': b'',
                    'mime_type': 'image/png'
                }
        
        logger.info("Начало генерации PDF коллажа...")
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
                logger.info("Вызов html.write_pdf() для коллажа...")
                pdf_bytes = html.write_pdf()
                elapsed = time.time() - start_time
                logger.info(f"PDF коллажа сгенерирован за {elapsed:.2f} сек, размер: {len(pdf_bytes)} bytes")
            except Exception as e:
                error_message[0] = str(e)
                error_occurred.set()
                logger.error(f"Ошибка в потоке генерации коллажа: {str(e)}", exc_info=True)
        
        # Запускаем генерацию в отдельном потоке
        thread = threading.Thread(target=generate)
        thread.daemon = True
        thread.start()
        thread.join(timeout=180)  # Увеличенный таймаут для коллажа
        
        elapsed = time.time() - start_time
        logger.info(f"Поток генерации коллажа завершен, прошло {elapsed:.2f} секунд")
        
        if thread.is_alive():
            logger.error(f"Таймаут генерации PDF коллажа (180 секунд), прошло {elapsed:.2f} сек")
            raise TimeoutError("Генерация PDF коллажа превысила лимит времени (180 секунд)")
        
        if error_occurred.is_set():
            raise Exception(error_message[0] or "Неизвестная ошибка генерации PDF коллажа")
        
        if pdf_bytes is None:
            raise Exception("PDF коллажа не был сгенерирован")
        
        return BytesIO(pdf_bytes)
    except TimeoutError as e:
        logger.error(f"Таймаут генерации PDF коллажа: {str(e)}")
        raise HTTPException(status_code=500, detail="Генерация PDF коллажа заняла слишком много времени")
    except Exception as e:
        logger.error(f"Ошибка генерации PDF коллажа: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка генерации PDF коллажа: {str(e)}")


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
                # Обработка data URI
                if url.startswith('data:image/'):
                    logger.info(f"Обработка data URI изображения...")
                    # Извлекаем base64 данные из data URI
                    header, data = url.split(',', 1)
                    # Определяем тип изображения из заголовка
                    if 'png' in header.lower():
                        content_type = 'image/png'
                    elif 'jpeg' in header.lower() or 'jpg' in header.lower():
                        content_type = 'image/jpeg'
                    else:
                        content_type = 'image/png'
                    
                    # Декодируем base64
                    image_data = base64.b64decode(data)
                    logger.info(f"Data URI декодирован: {len(image_data)} bytes, тип: {content_type}")
                    return {
                        'string': image_data,
                        'mime_type': content_type
                    }
                
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

def send_email_with_pdf(email_to: str, catalog_pdf: BytesIO, collage_pdf: BytesIO, outfit_description: str):
    """Отправляет email с двумя PDF вложениями (каталог и коллаж) через Gmail SMTP"""
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
        body = f"Здравствуйте!\n\nВаш outfit '{outfit_description}' готов. К письму прикреплены два PDF файла:\n- Каталог товаров (outfit_catalog.pdf)\n- Коллаж образа (outfit_collage.pdf)"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Прикрепление PDF каталога
        catalog_pdf.seek(0)
        catalog_data = catalog_pdf.read()
        logger.info(f"Прикрепление каталога: {len(catalog_data)} bytes")
        part_catalog = MIMEBase('application', 'octet-stream')
        part_catalog.set_payload(catalog_data)
        encoders.encode_base64(part_catalog)
        part_catalog.add_header(
            'Content-Disposition',
            f'attachment; filename="outfit_catalog.pdf"'
        )
        msg.attach(part_catalog)
        logger.info("Каталог прикреплен к письму")
        
        # Прикрепление PDF коллажа
        collage_pdf.seek(0)
        collage_data = collage_pdf.read()
        logger.info(f"Прикрепление коллажа: {len(collage_data)} bytes")
        part_collage = MIMEBase('application', 'octet-stream')
        part_collage.set_payload(collage_data)
        encoders.encode_base64(part_collage)
        part_collage.add_header(
            'Content-Disposition',
            f'attachment; filename="outfit_collage.pdf"'
        )
        msg.attach(part_collage)
        logger.info("Коллаж прикреплен к письму")
        
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

def optimize_image_for_html(img: Image.Image, max_size: tuple = (400, 400)) -> str:
    """
    Оптимизирует изображение для встраивания в HTML через base64 data URI.
    
    Args:
        img: PIL Image для оптимизации
        max_size: Максимальный размер (width, height)
        
    Returns:
        Base64 data URI строка (data:image/png;base64,...)
    """
    # Убеждаемся что изображение в RGBA формате для сохранения прозрачности
    if img.mode == 'P':  # Convert paletted images to RGBA
        img = img.convert('RGBA')
    elif img.mode == 'L':  # Convert grayscale to RGBA
        img = img.convert('RGBA')
    elif img.mode == 'RGB':  # Convert RGB to RGBA to preserve transparency
        img = img.convert('RGBA')
    elif img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Ресайзим если нужно
    if img.width > max_size[0] or img.height > max_size[1]:
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        logger.info(f"Изображение уменьшено до {img.width}x{img.height}")
    
    # Сохраняем как PNG для сохранения прозрачности
    buffer = BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return f"data:image/png;base64,{img_base64}"

def process_collage_images(items: List[Item]) -> dict:
    """
    Обрабатывает изображения для коллажа: загружает, удаляет фон и загружает в Firebase Storage.
    
    Примечание: Тени не добавляются к изображениям для коллажа - используется только удаление фона.
    
    Args:
        items: Список первых 8 товаров для коллажа
        
    Returns:
        Словарь с обработанными изображениями в формате Firebase URL
        {item_index: firebase_url}
    """
    processed_images = {}
    
    for i, item in enumerate(items[:8]):
        try:
            logger.info(f"Обработка изображения {i+1}/8: {item.name[:50]}...")
            
            # Загружаем изображение
            response = urllib.request.urlopen(item.image_url, timeout=10)
            image_data = response.read()
            
            # Открываем как PIL Image
            img = Image.open(BytesIO(image_data))
            original_size = img.size
            logger.info(f"Original image size: {original_size}")
            
            # Удаляем фон с помощью rembg
            # cutout_rgba() также автоматически обрезает все прозрачные области после удаления фона
            try:
                processed_img = cutout_rgba(img)
                size_after_bg_removal = processed_img.size
                logger.info(f"Image size after background removal and crop: {size_after_bg_removal} (was {original_size})")
                
                # Валидация: проверяем, что фон действительно удален
                if processed_img.mode == 'RGBA':
                    alpha = processed_img.split()[-1]
                    alpha_extrema = alpha.getextrema()
                    has_transparency = alpha_extrema[0] < 255
                    
                    if has_transparency:
                        logger.info(f"✅ Фон удален для {item.name[:50]} - прозрачность: {alpha_extrema}")
                    else:
                        logger.warning(f"⚠️ Фон может быть не удален для {item.name[:50]} - нет прозрачности (alpha: {alpha_extrema})")
                else:
                    logger.warning(f"⚠️ Изображение не в формате RGBA после удаления фона: {processed_img.mode}")
                    
            except Exception as bg_error:
                logger.error(f"❌ Не удалось удалить фон для {item.name[:50]}: {str(bg_error)}", exc_info=True)
                processed_img = img.convert("RGBA")
                logger.warning(f"Используем оригинал без удаления фона")
            
            # Убеждаемся, что изображение в формате RGBA для сохранения прозрачности
            if processed_img.mode != 'RGBA':
                processed_img = processed_img.convert('RGBA')
                logger.info(f"Изображение конвертировано в RGBA для сохранения прозрачности")
            
            # Оптимизируем изображение (уменьшаем размер если нужно, но сохраняем пропорции)
            # ВАЖНО: resize происходит ПОСЛЕ обрезки прозрачных областей (которая уже выполнена в cutout_rgba())
            # Это гарантирует, что изображение будет оптимального размера без лишних прозрачных областей
            # Для коллажа используем больший размер, чтобы сохранить качество
            size_before_resize = processed_img.size
            max_size = (1200, 1200)  # Увеличенный размер для лучшего качества коллажа
            if processed_img.width > max_size[0] or processed_img.height > max_size[1]:
                # Сохраняем пропорции при уменьшении
                processed_img.thumbnail(max_size, Image.Resampling.LANCZOS)
                size_after_resize = processed_img.size
                logger.info(f"Изображение уменьшено до {size_after_resize} (было {size_before_resize}, с сохранением прозрачности)")
            else:
                logger.info(f"Изображение не требует уменьшения: {size_before_resize} (максимум {max_size})")
            
            final_size = processed_img.size
            logger.info(f"Final image size: {final_size} (original: {original_size}, reduction: {((original_size[0] * original_size[1] - final_size[0] * final_size[1]) / (original_size[0] * original_size[1]) * 100):.1f}%)")
            
            # Сохраняем как PNG с прозрачностью для загрузки в Firebase
            buffer = BytesIO()
            # Важно: сохраняем с прозрачностью (RGBA)
            processed_img.save(buffer, format='PNG', optimize=True)
            image_bytes = buffer.getvalue()
            logger.info(f"Изображение сохранено в PNG с прозрачностью: {len(image_bytes)} bytes")
            
            # Генерируем уникальное имя файла
            item_id = str(item.id) if item.id else f"item-{i}"
            timestamp = int(time.time() * 1000)  # миллисекунды для уникальности
            file_name = f"collage_{item_id}_{timestamp}.png"
            
            # Загружаем в Firebase Storage
            try:
                firebase_url = upload_image_to_firebase(image_bytes, file_name, content_type="image/png")
                processed_images[i] = firebase_url
                logger.info(f"Изображение {i+1} загружено в Firebase: {firebase_url[:80]}...")
            except Exception as firebase_error:
                logger.error(f"Ошибка загрузки в Firebase для {item.name[:50]}: {str(firebase_error)}")
                # Fallback: используем оригинальное изображение
                processed_images[i] = item.image_url
            
        except Exception as e:
            logger.error(f"Ошибка обработки изображения для {item.name[:50]}: {str(e)}")
            # Fallback: используем оригинальное изображение
            processed_images[i] = item.image_url
    
    return processed_images

def parse_title_and_brand(item_name: str) -> tuple[str, str]:
    """
    Парсит название товара на title и brand.
    
    Args:
        item_name: Название товара, например "Джемпер из вискозы VETEMENTS"
        
    Returns:
        tuple: (title, brand) например ("Джемпер из вискозы", "VETEMENTS")
    """
    # Простая логика: ищем последнее слово или слова в верхнем регистре как brand
    words = item_name.split()
    if not words:
        return item_name, ""
    
    # Ищем brand с конца - слова в верхнем регистре или содержащие заглавные буквы
    brand_words = []
    title_words = []
    found_brand = False
    
    for word in reversed(words):
        # Если слово полностью в верхнем регистре или содержит много заглавных букв
        if word.isupper() or (len(word) > 1 and sum(1 for c in word if c.isupper()) > len(word) * 0.5):
            if not found_brand:
                brand_words.insert(0, word)
                found_brand = True
            else:
                # Если уже нашли brand, но следующее слово тоже в верхнем регистре - добавляем к brand
                brand_words.insert(0, word)
        else:
            if found_brand:
                # Если уже нашли brand, остальное идет в title
                title_words.insert(0, word)
            else:
                # Пока не нашли brand, все идет в title
                title_words.insert(0, word)
    
    # Если не нашли brand, берем последнее слово как brand
    if not brand_words:
        if words:
            brand_words = [words[-1]]
            title_words = words[:-1]
    
    title = " ".join(title_words) if title_words else item_name
    brand = " ".join(brand_words) if brand_words else ""
    
    return title, brand


def distribute_items_for_collage(items: List[Item], processed_images: dict = None) -> dict:
    """
    Распределяет товары по лейблам коллажа с обработанными изображениями.
    Использует Layout Agent для определения конкретных лейблов (top_main, top_second, bottom, etc.).
    
    Args:
        items: Список товаров
        processed_images: Словарь с обработанными Firebase URL {index: firebase_url}
        
    Returns:
        dict: Словарь {label: item_data} где label = top_main/top_second/bottom/accessory_upper/accessory_lower/shoes
    """
    # Определяем доступные лейблы
    available_labels = ['top_main', 'top_second', 'bottom', 'accessory_upper', 'accessory_lower', 'shoes']
    
    # Создаем словарь для маппинга ID -> индекс товара
    items_data_for_layout = []
    
    for i, item in enumerate(items[:8]):
        item_id = str(item.id) if item.id else f"item-{i}"
        items_data_for_layout.append({
            'id': item_id,
            'name': item.name
        })
    
    # Получаем лейблы товаров от Layout Agent
    item_labels = None
    if items_data_for_layout:
        item_labels = get_item_labels(items_data_for_layout)
    
    # Создаем словарь распределения по лейблам
    collage_items = {}
    used_indices = set()
    
    # Распределяем товары по лейблам
    for i, item in enumerate(items[:8]):
        if i in used_indices:
            continue
        
        # Определяем лейбл товара
        item_id = str(item.id) if item.id else f"item-{i}"
        if item_labels and item_id in item_labels:
            label = item_labels[item_id]
            logger.info(f"Товар {item.name[:30]}: лейбл {label}")
        else:
            # Fallback: определяем лейбл по названию
            name_lower = item.name.lower()
            if any(word in name_lower for word in ['брюки', 'джинсы', 'шорты', 'trousers', 'jeans', 'pants']):
                label = 'bottom'
            elif any(word in name_lower for word in ['туфли', 'ботинки', 'кроссовки', 'shoes', 'boots', 'sneakers']):
                label = 'shoes'
            elif any(word in name_lower for word in ['куртка', 'пиджак', 'блейзер', 'пальто', 'jacket', 'blazer', 'coat']):
                label = 'top_second'
            elif any(word in name_lower for word in ['шарф', 'шапка', 'кепка', 'scarf', 'hat', 'cap']):
                label = 'accessory_upper'
            elif any(word in name_lower for word in ['сумка', 'рюкзак', 'bag', 'backpack', 'пояс', 'belt']):
                label = 'accessory_lower'
            elif any(word in name_lower for word in ['рубашка', 'футболка', 'свитер', 'джемпер', 'кофта', 'shirt', 'jumper', 'sweater', 't-shirt']):
                label = 'top_main'
            else:
                # По умолчанию используем accessory_lower
                label = 'accessory_lower'
            logger.info(f"Товар {item.name[:30]}: лейбл {label} (fallback)")
        
        # Проверяем, что лейбл валидный
        if label not in available_labels:
            logger.warning(f"Неизвестный лейбл {label} для товара {item.name[:30]}, используем accessory_lower")
            label = 'accessory_lower'
        
        # Если лейбл уже занят, ищем свободный
        if label in collage_items and collage_items[label] is not None:
            # Ищем свободный лейбл
            available = [l for l in available_labels if collage_items.get(l) is None]
            if available:
                label = available[0]
                logger.info(f"Лейбл {label} уже занят, используем {label}")
            else:
                # Если все лейблы заняты, перезаписываем текущий
                logger.warning(f"Все лейблы заняты, перезаписываем {label}")
        
        # Парсим title и brand из названия
        title, brand = parse_title_and_brand(item.name)
        
        # Получаем URL изображения (Firebase URL или оригинальный)
        image_url = processed_images.get(i) if processed_images and i in processed_images else item.image_url
        
        # Создаем словарь с данными товара
        item_dict = {
            'title': title,
            'brand': brand,
            'name': item.name,  # Оставляем полное название для совместимости
            'image_url': image_url,
            'link': item.link,
            'price': item.price,
            'category': item.category
        }
        
        collage_items[label] = item_dict
        used_indices.add(i)
        logger.info(f"Товар {item.name[:30]} размещен в лейбл {label}")
    
    # Заполняем пустые лейблы None
    for label in available_labels:
        if label not in collage_items:
            collage_items[label] = None
    
    return collage_items

def render_collage_html(outfit: Outfit) -> str:
    """Рендерит HTML шаблон только для коллажа"""
    try:
        # Обрабатываем изображения для коллажа (первые 8 товаров)
        logger.info("Начало обработки изображений для коллажа...")
        processed_images = process_collage_images(outfit.items)
        logger.info(f"Обработано {len(processed_images)} изображений для коллажа")
        
        # Логируем информацию о processed_images для отладки
        for idx, img_url in processed_images.items():
            if img_url:
                logger.info(f"Изображение {idx}: Firebase URL: {img_url[:80]}...")
            else:
                logger.warning(f"Изображение {idx}: processed_image is None")
        
        # Рендерим коллаж с обработанными изображениями
        collage_template = env.get_template('collage_2.html')
        collage_items = distribute_items_for_collage(outfit.items, processed_images)
        
        # Логируем информацию о collage_items для отладки
        for label, item_data in collage_items.items():
            if item_data:
                logger.info(f"Коллаж лейбл {label}: title={item_data.get('title', 'N/A')[:30]}, brand={item_data.get('brand', 'N/A')[:30]}, image_url={'есть' if item_data.get('image_url') else 'нет'}")
            else:
                logger.info(f"Коллаж лейбл {label}: пусто")
        
        collage_html = collage_template.render(
            collage_items=collage_items
        )
        
        # Обертываем коллаж в полный HTML документ с правильным размером страницы
        # Размер страницы коллажа: 2500×2500px = 26.04in × 26.04in (при 96 DPI)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(collage_html, 'html.parser')
        collage_body = soup.find('body')
        collage_head = soup.find('head')
        
        collage_styles = ''
        if collage_head:
            style_tags = collage_head.find_all('style')
            collage_styles = '\n'.join(tag.string if tag.string else '' for tag in style_tags)
        
        collage_body_content = ''
        if collage_body:
            collage_body_content = ''.join(str(child) for child in collage_body.children)
        else:
            collage_body_content = collage_html
        
        # Создаем полный HTML документ для коллажа с квадратным размером страницы
        # Размер: 2500px × 2500px = 26.04in × 26.04in (при 96 DPI)
        # Используем точный размер в дюймах для WeasyPrint
        # Убеждаемся, что все элементы правильно позиционированы
        full_collage_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: 26.04in 26.04in;
            margin: 0;
            padding: 0;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        html {{
            margin: 0;
            padding: 0;
            width: 2500px;
            height: 2500px;
        }}
        body {{
            margin: 0;
            padding: 0;
            width: 2500px;
            height: 2500px;
            overflow: hidden;
            position: relative;
            background: #111;
        }}
        /* Стили коллажа */
        {collage_styles}
    </style>
</head>
<body>
    {collage_body_content}
</body>
</html>"""
        
        return full_collage_html
    except Exception as e:
        logger.error(f"Ошибка рендеринга коллажа: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка рендеринга коллажа: {str(e)}")


def render_catalog_html(outfit: Outfit) -> str:
    """Рендерит HTML шаблон только для каталога"""
    try:
        # Рендерим каталог товаров
        catalog_template = env.get_template('outfit.html')
        
        # Разбиваем товары на страницы по 8 штук
        items_per_page = 8
        pages = []
        for i in range(0, len(outfit.items), items_per_page):
            page_items = outfit.items[i:i + items_per_page]
            pages.append(page_items)
        
        catalog_html = catalog_template.render(
            outfit_description=outfit.outfit_description,
            pages=pages
        )
        
        return catalog_html
    except Exception as e:
        logger.error(f"Ошибка рендеринга каталога: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка рендеринга каталога: {str(e)}")


def render_html_template(outfit: Outfit) -> str:
    """Рендерит HTML шаблон с данными outfit (каталог + коллаж)"""
    try:
        # Рендерим каталог товаров
        catalog_template = env.get_template('outfit.html')
        
        # Разбиваем товары на страницы по 8 штук
        items_per_page = 8
        pages = []
        for i in range(0, len(outfit.items), items_per_page):
            page_items = outfit.items[i:i + items_per_page]
            pages.append(page_items)
        
        catalog_html = catalog_template.render(
            outfit_description=outfit.outfit_description,
            pages=pages
        )
        
        # Обрабатываем изображения для коллажа (первые 8 товаров)
        logger.info("Начало обработки изображений для коллажа...")
        processed_images = process_collage_images(outfit.items)
        logger.info(f"Обработано {len(processed_images)} изображений для коллажа")
        
        # Логируем информацию о processed_images для отладки
        for idx, img_url in processed_images.items():
            if img_url:
                logger.info(f"Изображение {idx}: Firebase URL: {img_url[:80]}...")
            else:
                logger.warning(f"Изображение {idx}: processed_image is None")
        
        # Рендерим коллаж с обработанными изображениями
        collage_template = env.get_template('collage_2.html')
        collage_items = distribute_items_for_collage(outfit.items, processed_images)
        
        # Логируем информацию о collage_items для отладки
        for label, item_data in collage_items.items():
            if item_data:
                logger.info(f"Коллаж лейбл {label}: title={item_data.get('title', 'N/A')[:30]}, brand={item_data.get('brand', 'N/A')[:30]}, image_url={'есть' if item_data.get('image_url') else 'нет'}")
            else:
                logger.info(f"Коллаж лейбл {label}: пусто")
        
        collage_html = collage_template.render(
            collage_items=collage_items
        )
        
        # Извлекаем содержимое body и стили из каждого шаблона для правильного объединения
        from bs4 import BeautifulSoup
        
        try:
            # Парсим коллаж HTML
            soup_collage = BeautifulSoup(collage_html, 'html.parser')
            collage_body = soup_collage.find('body')
            collage_head = soup_collage.find('head')
            
            # Извлекаем стили из head коллажа и адаптируем для изоляции
            collage_styles = ''
            if collage_head:
                style_tags = collage_head.find_all('style')
                raw_styles = '\n'.join(tag.string if tag.string else '' for tag in style_tags)
                # Обертываем стили коллажа в селектор .collage-section для изоляции
                # Это предотвращает конфликты со стилями каталога
                import re
                # Заменяем селекторы body и html на .collage-section
                collage_styles = re.sub(r'(\s|^)body\s*{', r'\1.collage-section {', raw_styles)
                collage_styles = re.sub(r'(\s|^)html\s*{', r'\1.collage-section {', collage_styles)
                collage_styles = re.sub(r'(\s|^)html,\s*body\s*{', r'\1.collage-section {', collage_styles)
            
            # Извлекаем содержимое body коллажа
            if collage_body:
                collage_body_content = ''.join(str(child) for child in collage_body.children)
            else:
                collage_body_content = collage_html
            
            # Парсим каталог HTML
            soup_catalog = BeautifulSoup(catalog_html, 'html.parser')
            catalog_body = soup_catalog.find('body')
            catalog_head = soup_catalog.find('head')
            
            # Извлекаем стили из head каталога
            catalog_styles = ''
            if catalog_head:
                style_tags = catalog_head.find_all('style')
                catalog_styles = '\n'.join(tag.string if tag.string else '' for tag in style_tags)
            
            # Извлекаем содержимое body каталога
            if catalog_body:
                catalog_body_content = ''.join(str(child) for child in catalog_body.children)
            else:
                catalog_body_content = catalog_html
            
            # Объединяем оба шаблона в один HTML документ со всеми стилями
            # Изолируем стили коллажа, чтобы они применялись только к секции коллажа
            # Размер страницы коллажа: 2500×2500px = 26.04in × 26.04in (при 96 DPI)
            # WeasyPrint лучше работает с дюймами для кастомных размеров
            combined_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 20mm;
        }}
        @page collage-page {{
            size: 26.04in 26.04in;
            margin: 0;
        }}
        .catalog-section {{
            page-break-after: always;
        }}
        .collage-section {{
            page-break-before: always;
            page: collage-page;
            width: 2500px;
            height: 2500px;
            margin: 0;
            padding: 0;
            overflow: hidden;
            box-sizing: border-box;
        }}
        /* Стили каталога */
        {catalog_styles}
        /* Стили коллажа - уже изолированы через замену body/html на .collage-section */
        {collage_styles}
    </style>
</head>
<body>
    <div class="catalog-section">
        {catalog_body_content}
    </div>
    <div class="collage-section">
        {collage_body_content}
    </div>
</body>
</html>"""
        except Exception as parse_error:
            logger.warning(f"Не удалось распарсить HTML для объединения: {str(parse_error)}, используем простое объединение")
            # Простое объединение без парсинга - вставляем полные HTML документы
            # Размер страницы коллажа: 2500×2500px = 26.04in × 26.04in (при 96 DPI)
            # WeasyPrint лучше работает с дюймами для кастомных размеров
            combined_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            size: A4;
            margin: 20mm;
        }}
        @page collage-page {{
            size: 26.04in 26.04in;
            margin: 0;
        }}
        .catalog-section {{
            page-break-after: always;
        }}
        .collage-section {{
            page-break-before: always;
            page: collage-page;
            width: 2500px;
            height: 2500px;
            margin: 0;
            padding: 0;
            overflow: hidden;
            box-sizing: border-box;
        }}
    </style>
</head>
<body>
    <div class="catalog-section">
        {catalog_html}
    </div>
    <div class="collage-section">
        {collage_html}
    </div>
</body>
</html>"""
        
        return combined_html
    except Exception as e:
        logger.error(f"Ошибка рендеринга шаблона: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка рендеринга шаблона: {str(e)}")

@app.post("/generate-pdf", response_model=Response)
async def generate_pdf_endpoint(request: OutfitRequest):
    """
    Генерирует два отдельных PDF (каталог и коллаж) и отправляет на указанный email
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    try:
        # Валидация данных
        if not request.outfit.items:
            raise HTTPException(status_code=400, detail="Список товаров не может быть пустым")
        
        logger.info(f"Начало обработки запроса для {request.email}, товаров: {len(request.outfit.items)}")
        
        # Рендеринг HTML для каталога и коллажа отдельно
        catalog_html = render_catalog_html(request.outfit)
        collage_html = render_collage_html(request.outfit)
        logger.info("HTML шаблоны отрендерены")
        
        # Генерация PDF в отдельном потоке для неблокирующей работы
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Генерируем оба PDF параллельно
            # Для коллажа используем специальную функцию с правильными настройками
            catalog_pdf_future = loop.run_in_executor(executor, generate_pdf, catalog_html)
            collage_pdf_future = loop.run_in_executor(executor, generate_collage_pdf, collage_html)
            
            catalog_pdf_buffer = await catalog_pdf_future
            collage_pdf_buffer = await collage_pdf_future
        
        logger.info("PDF файлы сгенерированы")
        logger.info(f"Размер PDF каталога: {len(catalog_pdf_buffer.getvalue())} bytes")
        logger.info(f"Размер PDF коллажа: {len(collage_pdf_buffer.getvalue())} bytes")
        
        # Копируем данные из буферов для отправки в фоне
        catalog_pdf_buffer.seek(0)
        catalog_pdf_data = catalog_pdf_buffer.read()
        catalog_pdf_copy = BytesIO(catalog_pdf_data)
        logger.info(f"Каталог скопирован: {len(catalog_pdf_data)} bytes")
        
        collage_pdf_buffer.seek(0)
        collage_pdf_data = collage_pdf_buffer.read()
        collage_pdf_copy = BytesIO(collage_pdf_data)
        logger.info(f"Коллаж скопирован: {len(collage_pdf_data)} bytes")
        
        # Отправка email в отдельном потоке (не блокируем ответ)
        async def send_email_async():
            try:
                with ThreadPoolExecutor() as executor:
                    await loop.run_in_executor(
                        executor,
                        send_email_with_pdf,
                        request.email,
                        catalog_pdf_copy,
                        collage_pdf_copy,
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
            message=f"PDF файлы генерируются и будут отправлены на {request.email}"
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

