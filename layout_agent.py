"""
Layout Agent - определение лейблов товаров для коллажа.

Использует Azure OpenAI для определения конкретного лейбла товара:
top_main, top_second, bottom, accessory_upper, accessory_lower, shoes
"""

import os
import logging
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from openai import AzureOpenAI

logger = logging.getLogger(__name__)

# Глобальный клиент Azure OpenAI (singleton)
_azure_openai_client_o4mini = None

def get_azure_openai_client_o4mini() -> Optional[AzureOpenAI]:
    """
    Creates and returns a cached Azure OpenAI client for o4-mini model.
    Used specifically for Layout Agent collage generation.
    Uses singleton pattern to avoid creating new clients on every call.
    
    Returns:
        AzureOpenAI: Cached Azure OpenAI client configured for o4-mini
        None: If environment variables are not set
    """
    global _azure_openai_client_o4mini
    
    if _azure_openai_client_o4mini is None:
        try:
            azure_endpoint = os.environ.get("AZURE_API_BASE_o4")
            api_key = os.environ.get("AZURE_API_KEY")
            api_version = os.environ.get("AZURE_API_VERSION", "2024-10-21")
            
            if not azure_endpoint or not api_key:
                logger.warning("Azure OpenAI credentials not found in environment variables. Layout Agent will use fallback.")
                return None
            
            _azure_openai_client_o4mini = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=api_key,
                api_version=api_version
            )
            logger.info("Azure OpenAI client initialized for Layout Agent")
        except Exception as e:
            logger.error(f"Failed to initialize Azure OpenAI client: {str(e)}")
            return None
    
    return _azure_openai_client_o4mini


class ItemLabel(BaseModel):
    """Лейбл товара для коллажа."""
    item_id: str = Field(..., description="ID товара")
    label: Literal["top_main", "top_second", "bottom", "accessory_upper", "accessory_lower", "shoes"] = Field(..., description="Лейбл товара для размещения в коллаже")


class LabelsResponse(BaseModel):
    """Ответ от Layout Agent с лейблами товаров."""
    items: List[ItemLabel] = Field(..., description="Список лейблов для товаров")
    reasoning: str = Field(..., min_length=20, description="Объяснение логики классификации")


def get_item_labels(items: List[dict]) -> Optional[dict]:
    """
    Определяет лейблы товаров используя Azure OpenAI Layout Agent.
    
    Args:
        items: Список словарей с данными товаров:
            - id: str - ID товара
            - name: str - название товара
    
    Returns:
        dict: Словарь {item_id: label} где label = "top_main"|"top_second"|"bottom"|"accessory_upper"|"accessory_lower"|"shoes"
        None: Если LLM недоступен или произошла ошибка
    """
    client = get_azure_openai_client_o4mini()
    
    if client is None:
        logger.warning("Azure OpenAI client not available, skipping Layout Agent")
        return None
    
    try:
        # Подготовить данные товаров для анализа
        items_data = []
        for item in items:
            item_data = {
                "id": str(item.get("id", "")),
                "name": item.get("name", "")
            }
            items_data.append(item_data)
        
        # System prompt для определения лейблов
        system_prompt = """Ты — Fashion Label Classifier AI для определения лейблов товаров в коллаже.

Твоя задача: проанализировать название товара и определить его конкретный лейбл для размещения в коллаже.

Лейблы:
- top_main: основной верх (джемпер, свитер, кофта, футболка, рубашка)
- top_second: второй верх (куртка, пиджак, блейзер, пальто)
- bottom: низ (джинсы, брюки, шорты)
- accessory_upper: верхний аксессуар (шарф, шапка, кепка)
- accessory_lower: нижний аксессуар (сумка, рюкзак, пояс)
- shoes: обувь (кроссовки, туфли, ботинки, сандалии)

ВАЖНО: Каждый товар должен получить ровно один лейбл. Выбирай наиболее подходящий лейбл на основе названия товара.

Верни лейбл для каждого товара."""
        
        # User prompt с данными товаров
        user_prompt = f"""Определи лейбл для каждого товара:

Товары:
{chr(10).join([f"- ID: {item['id']}, Название: {item['name']}" for item in items_data])}

Верни лейбл (top_main, top_second, bottom, accessory_upper, accessory_lower или shoes) для каждого товара."""
        
        deployment_name = os.environ.get("AZURE_DEPLOYMENT_NAME_o4", "o4-mini")
        
        logger.info(f"Calling Azure OpenAI Layout Agent (deployment: {deployment_name})...")
        
        response = client.beta.chat.completions.parse(
            model=deployment_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=LabelsResponse
        )
        
        labels_response = response.choices[0].message.parsed
        logger.info(f"Layout Agent response: {labels_response.reasoning[:100]}...")
        
        # Преобразуем в словарь {item_id: label}
        result = {}
        for item_label in labels_response.items:
            result[item_label.item_id] = item_label.label
        
        return result
        
    except Exception as e:
        logger.error(f"Error in Layout Agent: {str(e)}", exc_info=True)
        return None
