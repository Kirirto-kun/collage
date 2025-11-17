
"""
Background Removal Module - Автоматическое удаление фона и добавление теней.

Использует rembg для удаления фона с изображений товаров и добавляет
мягкие тени для создания профессиональных коллажей.
"""

from PIL import Image, ImageFilter, ImageOps
from io import BytesIO
from functools import lru_cache
import asyncio
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Глобальная сессия rembg (создается один раз для оптимизации)
_REMBG_SESSION = None

def get_rembg_session():
    """
    Получает глобальную сессию rembg.
    Создается один раз при первом использовании.
    """
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        try:
            from rembg import new_session
            _REMBG_SESSION = new_session("isnet-general-use")
            logger.info("✅ rembg session initialized (isnet-general-use)")
        except ImportError:
            logger.warning("⚠️ rembg not installed, background removal disabled")
            _REMBG_SESSION = None
        except Exception as e:
            logger.error(f"❌ Error initializing rembg session: {e}")
            _REMBG_SESSION = None
    return _REMBG_SESSION


def _detect_background_color(img: Image.Image, alpha: Image.Image) -> Optional[tuple]:
    """
    Определяет цвет фона по углам и краям изображения.
    
    Returns:
        (r, g, b) цвет фона или None если не удалось определить
    """
    w, h = img.size
    # Проверяем углы и края изображения (где обычно находится фон)
    corners = [
        (0, 0), (w-1, 0), (0, h-1), (w-1, h-1),  # Углы
        (w//2, 0), (w//2, h-1), (0, h//2), (w-1, h//2)  # Края
    ]
    
    bg_colors = []
    for x, y in corners:
        if x < w and y < h:
            pixel = img.getpixel((x, y))
            alpha_val = alpha.getpixel((x, y)) if alpha else 255
            # Если пиксель прозрачный или почти прозрачный, пропускаем
            if alpha_val < 50:
                continue
            if len(pixel) >= 3:
                bg_colors.append(pixel[:3])
    
    if not bg_colors:
        return None
    
    # Берем наиболее частый цвет
    from collections import Counter
    color_counts = Counter(bg_colors)
    most_common = color_counts.most_common(1)[0][0]
    return most_common


def _create_transparency_from_mask(img: Image.Image, alpha: Image.Image) -> Image.Image:
    """
    Создает прозрачность на основе альфа-канала.
    Использует альфа-канал как маску для создания прозрачного фона.
    """
    r, g, b, a = img.split()
    
    # Создаем маску: где альфа > 0, там предмет
    mask = alpha.point(lambda x: 255 if x > 0 else 0, mode='L')
    
    # Применяем маску к RGB каналам для создания прозрачности
    transparent_r = Image.composite(r, Image.new('L', r.size, 0), mask)
    transparent_g = Image.composite(g, Image.new('L', g.size, 0), mask)
    transparent_b = Image.composite(b, Image.new('L', b.size, 0), mask)
    
    # Создаем новое изображение с прозрачным фоном
    return Image.merge('RGBA', (transparent_r, transparent_g, transparent_b, mask))


def cutout_rgba(img: Image.Image) -> Image.Image:
    """
    Удаляет фон с изображения с помощью rembg.
    
    Args:
        img: PIL Image (RGB/RGBA)
        
    Returns:
        PIL Image (RGBA) с прозрачным фоном
    """
    session = get_rembg_session()
    if session is None:
        logger.warning("rembg session not available, returning original image")
        return img.convert("RGBA")
    
    try:
        logger.info(f"Starting background removal for image {img.size}, mode: {img.mode}")
        
        # Конвертируем в bytes для rembg
        img_bytes = BytesIO()
        # Конвертируем в RGB если нужно (rembg работает лучше с RGB)
        if img.mode != 'RGB':
            img_for_rembg = img.convert('RGB')
        else:
            img_for_rembg = img
        img_for_rembg.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # Удаляем фон
        from rembg import remove
        logger.info("Calling rembg.remove()...")
        out_bytes = remove(img_bytes.read(), session=session)
        out = Image.open(BytesIO(out_bytes)).convert("RGBA")
        logger.info(f"rembg returned image {out.size}, mode: {out.mode}")
        
        # ВАЖНО: Проверяем, что фон действительно прозрачный
        if out.mode == 'RGBA':
            # Получаем альфа-канал
            alpha = out.split()[-1]
            
            # Проверяем, есть ли прозрачные пиксели
            alpha_extrema = alpha.getextrema()
            logger.info(f"Alpha channel extrema: {alpha_extrema}")
            
            # Проверяем, есть ли черные/белые пиксели в RGB (возможный фон)
            r, g, b, a = out.split()
            r_extrema = r.getextrema()
            g_extrema = g.getextrema()
            b_extrema = b.getextrema()
            logger.info(f"RGB extrema - R: {r_extrema}, G: {g_extrema}, B: {b_extrema}")
            
            # Проверяем, есть ли прозрачные области
            has_transparency = alpha_extrema[0] < 255
            
            if not has_transparency:
                # Все пиксели непрозрачные - rembg не удалил фон
                logger.warning("rembg returned opaque image (no transparency), attempting to create transparency...")
                
                # Пытаемся определить цвет фона
                bg_color = _detect_background_color(out, alpha)
                if bg_color:
                    logger.info(f"Detected background color: {bg_color}")
                    # Создаем маску: где цвет близок к фону, делаем прозрачным
                    # Используем альфа-канал как основу для маски
                    mask = alpha.copy()
                    # Улучшаем маску на основе цвета фона (оптимизированная версия)
                    threshold = 30  # Порог для определения фона
                    # Конвертируем в numpy для быстрой обработки (если доступен)
                    try:
                        import numpy as np
                        img_array = np.array(out)
                        r, g, b, a = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2], img_array[:, :, 3]
                        # Вычисляем расстояние от цвета фона
                        dist = np.sqrt((r - bg_color[0])**2 + (g - bg_color[1])**2 + (b - bg_color[2])**2)
                        # Где расстояние меньше порога, делаем прозрачным
                        mask_array = np.array(mask)
                        mask_array[dist < threshold] = 0
                        mask = Image.fromarray(mask_array, mode='L')
                        logger.info("Mask created using numpy optimization")
                    except ImportError:
                        # Fallback: используем PIL (медленнее, но работает всегда)
                        logger.warning("numpy not available, using slower PIL method")
                        threshold = 30
                        pixels = mask.load()
                        img_pixels = out.load()
                        for y in range(out.height):
                            for x in range(out.width):
                                pixel = img_pixels[x, y]
                                if len(pixel) >= 3:
                                    r_val, g_val, b_val = pixel[:3]
                                    # Если цвет близок к фону, делаем прозрачным
                                    if (abs(r_val - bg_color[0]) < threshold and
                                        abs(g_val - bg_color[1]) < threshold and
                                        abs(b_val - bg_color[2]) < threshold):
                                        pixels[x, y] = 0
                
                # Создаем прозрачность на основе маски
                out = _create_transparency_from_mask(out, mask)
                logger.info("Transparency created from mask")
            else:
                # Есть прозрачность, но проверяем, нет ли черного/белого фона
                # Проверяем углы изображения на черный/белый фон
                w, h = out.size
                corner_pixels = [
                    out.getpixel((0, 0)),
                    out.getpixel((w-1, 0)),
                    out.getpixel((0, h-1)),
                    out.getpixel((w-1, h-1))
                ]
                
                # Проверяем, есть ли черный (0,0,0) или белый (255,255,255) фон
                has_black_bg = any(len(p) >= 3 and p[0] < 10 and p[1] < 10 and p[2] < 10 and (len(p) < 4 or p[3] > 200) for p in corner_pixels)
                has_white_bg = any(len(p) >= 3 and p[0] > 245 and p[1] > 245 and p[2] > 245 and (len(p) < 4 or p[3] > 200) for p in corner_pixels)
                
                if has_black_bg or has_white_bg:
                    logger.warning(f"Detected {'black' if has_black_bg else 'white'} background, creating transparency...")
                    # Создаем маску на основе альфа-канала
                    mask = alpha.copy()
                    # Улучшаем маску: где цвет близок к черному/белому и альфа высокая, делаем прозрачным
                    threshold = 20
                    try:
                        import numpy as np
                        img_array = np.array(out)
                        r, g, b, a = img_array[:, :, 0], img_array[:, :, 1], img_array[:, :, 2], img_array[:, :, 3]
                        mask_array = np.array(mask)
                        
                        if has_black_bg:
                            # Черный фон: где все каналы < threshold и альфа высокая
                            black_mask = (r < threshold) & (g < threshold) & (b < threshold) & (a > 200)
                            mask_array[black_mask] = 0
                        elif has_white_bg:
                            # Белый фон: где все каналы > 255-threshold и альфа высокая
                            white_mask = (r > 255-threshold) & (g > 255-threshold) & (b > 255-threshold) & (a > 200)
                            mask_array[white_mask] = 0
                        
                        mask = Image.fromarray(mask_array, mode='L')
                        logger.info("Mask created using numpy optimization")
                    except ImportError:
                        # Fallback: используем PIL (медленнее, но работает всегда)
                        logger.warning("numpy not available, using slower PIL method")
                        pixels = mask.load()
                        img_pixels = out.load()
                        alpha_pixels = alpha.load()
                        for y in range(h):
                            for x in range(w):
                                pixel = img_pixels[x, y]
                                alpha_val = alpha_pixels[x, y]
                                if len(pixel) >= 3 and alpha_val > 200:
                                    r_val, g_val, b_val = pixel[:3]
                                    # Черный фон
                                    if has_black_bg and r_val < threshold and g_val < threshold and b_val < threshold:
                                        pixels[x, y] = 0
                                    # Белый фон
                                    elif has_white_bg and r_val > 255-threshold and g_val > 255-threshold and b_val > 255-threshold:
                                        pixels[x, y] = 0
                    
                    out = _create_transparency_from_mask(out, mask)
                    logger.info("Transparency created from black/white background detection")
        
        # Валидация: проверяем, что есть прозрачные области
        final_alpha = out.split()[-1]
        final_alpha_extrema = final_alpha.getextrema()
        has_final_transparency = final_alpha_extrema[0] < 255
        
        if not has_final_transparency:
            logger.warning("⚠️ Final image has no transparency - background may not be removed")
        else:
            logger.info(f"✅ Background removed successfully - transparency range: {final_alpha_extrema}")
        
        # Автокроп прозрачных полей - обрезаем все прозрачные пиксели
        # Делаем ДО сглаживания краев, чтобы обрезать полностью прозрачные области
        size_before_crop = out.size
        logger.info(f"Size before crop: {size_before_crop}")
        
        # Используем getbbox() для нахождения bounding box непрозрачных пикселей (alpha > 0)
        bbox = out.getbbox()
        
        if bbox:
            bbox_width = bbox[2] - bbox[0]
            bbox_height = bbox[3] - bbox[1]
            logger.info(f"Bounding box found: {bbox} (left, top, right, bottom), size: {bbox_width}x{bbox_height}")
            
            # Проверяем, что bbox действительно меньше исходного размера
            if bbox_width < size_before_crop[0] or bbox_height < size_before_crop[1]:
                # Обрезаем изображение по bounding box
                out = out.crop(bbox)
                size_after_crop = out.size
                pixels_saved = (size_before_crop[0] * size_before_crop[1]) - (size_after_crop[0] * size_after_crop[1])
                reduction_percent = (pixels_saved / (size_before_crop[0] * size_before_crop[1])) * 100 if size_before_crop[0] * size_before_crop[1] > 0 else 0
                logger.info(f"✅ Cropped transparent areas: size after {size_after_crop} (saved {pixels_saved} pixels, {reduction_percent:.1f}% reduction)")
            else:
                logger.warning(f"⚠️ Bounding box is same size as original! bbox: {bbox}, original: {size_before_crop}")
                # Пробуем более агрессивную обрезку с порогом
                alpha = out.split()[-1]
                threshold = 10
                mask = alpha.point(lambda x: 255 if x > threshold else 0, mode='L')
                bbox_aggressive = mask.getbbox()
                if bbox_aggressive:
                    bbox_aggressive_width = bbox_aggressive[2] - bbox_aggressive[0]
                    bbox_aggressive_height = bbox_aggressive[3] - bbox_aggressive[1]
                    if bbox_aggressive_width < size_before_crop[0] or bbox_aggressive_height < size_before_crop[1]:
                        logger.info(f"Trying aggressive crop with threshold {threshold}: bbox={bbox_aggressive}, size: {bbox_aggressive_width}x{bbox_aggressive_height}")
                        out = out.crop(bbox_aggressive)
                        size_after_crop = out.size
                        logger.info(f"✅ Aggressive crop result: size after {size_after_crop}")
        else:
            logger.warning("⚠️ No bounding box found - image may be fully transparent")
        
        # Сглаживание краев для более аккуратного вида (делаем ПОСЛЕ обрезки)
        # Это гарантирует, что сглаживание применяется только к обрезанному изображению
        alpha = out.split()[-1].filter(ImageFilter.GaussianBlur(0.7))
        out.putalpha(alpha)
        
        logger.info(f"✅ Background removal completed: final size {out.size}, mode: {out.mode}")
        return out
        
    except Exception as e:
        logger.error(f"❌ Error removing background: {e}", exc_info=True)
        # Fallback: возвращаем оригинал с прозрачностью
        return img.convert("RGBA")


def add_drop_shadow(rgba: Image.Image, 
                   offset=(6, 8), 
                   blur=10, 
                   opacity=70) -> Image.Image:
    """
    Добавляет мягкую падающую тень к изображению.
    
    Args:
        rgba: PIL Image (RGBA) с прозрачным фоном
        offset: (x, y) смещение тени в пикселях
        blur: радиус размытия тени
        opacity: прозрачность тени (0-255)
        
    Returns:
        PIL Image (RGBA) с тенью
    """
    w, h = rgba.size
    logger.info(f"Adding shadow to image {w}x{h}, offset={offset}, blur={blur}, opacity={opacity}")
    
    # Проверяем входное изображение
    if rgba.mode != 'RGBA':
        logger.warning(f"Input image mode: {rgba.mode}, converting to RGBA")
        rgba = rgba.convert('RGBA')
    
    # Проверяем альфа-канал входного изображения
    alpha = rgba.split()[-1]
    alpha_extrema = alpha.getextrema()
    logger.info(f"Input alpha extrema: {alpha_extrema}")
    
    # Создаем холст для тени (больше оригинала)
    shadow_canvas = Image.new("RGBA", 
                              (w + abs(offset[0]) + blur*2, 
                               h + abs(offset[1]) + blur*2), 
                              (0,0,0,0))
    
    # Создаем тень из альфа-канала оригинала
    base_alpha = rgba.split()[-1]
    shadow_alpha = base_alpha.copy().filter(ImageFilter.GaussianBlur(blur))
    
    # Создаем черную тень с правильными размерами
    shadow_layer = Image.new("RGBA", shadow_canvas.size, (0,0,0,0))
    
    # Размещаем тень с учетом offset
    shadow_x = blur + max(0, offset[0])
    shadow_y = blur + max(0, offset[1])
    
    # Создаем черный слой с правильными размерами для тени
    shadow_color = Image.new("RGBA", (w, h), (0,0,0,opacity))
    
    # Вставляем тень с маской (проверяем размеры)
    try:
        shadow_layer.paste(shadow_color, (shadow_x, shadow_y), shadow_alpha)
        logger.info(f"Shadow pasted successfully at ({shadow_x}, {shadow_y})")
    except Exception as e:
        logger.error(f"Error in shadow paste: {e}")
        logger.error(f"Shadow layer size: {shadow_layer.size}")
        logger.error(f"Shadow color size: {shadow_color.size}")
        logger.error(f"Shadow alpha size: {shadow_alpha.size}")
        logger.error(f"Paste position: ({shadow_x}, {shadow_y})")
        # Fallback: возвращаем оригинал без тени
        return rgba
    
    # Композитим тень + предмет
    result = Image.new("RGBA", shadow_canvas.size, (0,0,0,0))
    result.alpha_composite(shadow_layer)
    result.alpha_composite(rgba, (blur, blur))
    
    # Проверяем результат
    result_alpha = result.split()[-1]
    result_alpha_extrema = result_alpha.getextrema()
    logger.info(f"Result alpha extrema: {result_alpha_extrema}")
    
    return result


async def process_image_async(img: Image.Image, 
                             remove_bg: bool = True,
                             add_shadow: bool = True,
                             shadow_intensity: int = 70) -> Image.Image:
    """
    Асинхронно обрабатывает изображение: удаляет фон и добавляет тень.
    
    Args:
        img: PIL Image для обработки
        remove_bg: Удалять ли фон
        add_shadow: Добавлять ли тень
        shadow_intensity: Интенсивность тени (0-255)
        
    Returns:
        Обработанное PIL Image (RGBA)
    """
    if not remove_bg and not add_shadow:
        return img.convert("RGBA")
    
    # Выполняем обработку в thread pool для неблокирующей работы
    loop = asyncio.get_event_loop()
    
    if remove_bg:
        logger.info("Removing background...")
        img = await loop.run_in_executor(None, cutout_rgba, img)
        logger.info(f"After background removal: {img.size}, mode: {img.mode}")
    
    if add_shadow and remove_bg:  # Тень только если удалили фон
        logger.info(f"Adding drop shadow (intensity: {shadow_intensity})...")
        img = await loop.run_in_executor(
            None, 
            add_drop_shadow, 
            img, 
            (6, 8),  # offset
            10,      # blur
            shadow_intensity  # opacity
        )
        logger.info(f"After shadow addition: {img.size}, mode: {img.mode}")
    
    return img


@lru_cache(maxsize=50)
def _cached_process_image(image_hash: str, 
                         remove_bg: bool, 
                         add_shadow: bool, 
                         shadow_intensity: int) -> bytes:
    """
    Кэшированная обработка изображения по хэшу.
    Используется для оптимизации повторных запросов.
    """
    # Эта функция будет использоваться для кэширования
    # В реальной реализации нужно будет сохранять обработанные изображения
    pass


def create_placeholder_with_shadow(width: int, height: int, text: str = "Error") -> Image.Image:
    """
    Создает placeholder изображение с тенью при ошибке обработки.
    
    Args:
        width: Ширина placeholder
        height: Высота placeholder
        text: Текст для отображения
        
    Returns:
        PIL Image с тенью
    """
    # Создаем базовое изображение
    img = Image.new('RGBA', (width, height), (240, 240, 240, 255))
    
    # Добавляем тень
    img_with_shadow = add_drop_shadow(img, offset=(4, 4), blur=8, opacity=50)
    
    return img_with_shadow


# Экспорты
__all__ = [
    'cutout_rgba',
    'add_drop_shadow', 
    'process_image_async',
    'get_rembg_session',
    'create_placeholder_with_shadow'
]
