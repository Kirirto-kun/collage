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
    try:
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        return BytesIO(pdf_bytes)
    except Exception as e:
        logger.error(f"Ошибка генерации PDF: {str(e)}")
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
        
        # Отправка через SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gmail_email, gmail_password)
        text = msg.as_string()
        server.sendmail(gmail_email, email_to, text)
        server.quit()
        
        logger.info(f"PDF успешно отправлен на {email_to}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка отправки email: {str(e)}")

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
    try:
        # Валидация данных
        if not request.outfit.items:
            raise HTTPException(status_code=400, detail="Список товаров не может быть пустым")
        
        # Рендеринг HTML
        html_content = render_html_template(request.outfit)
        
        # Генерация PDF
        pdf_buffer = generate_pdf(html_content)
        
        # Отправка email
        send_email_with_pdf(
            email_to=request.email,
            pdf_buffer=pdf_buffer,
            outfit_description=request.outfit.outfit_description
        )
        
        return Response(
            status="success",
            message=f"PDF успешно отправлен на {request.email}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@app.get("/")
async def root():
    return {"message": "PDF Outfit Generator API"}

@app.get("/health")
async def health():
    return {"status": "ok"}

