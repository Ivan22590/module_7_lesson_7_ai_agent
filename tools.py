"""
tools.py — инструменты для AI-агента.

Каждый инструмент реализован через декоратор @tool из langchain_core.tools.
Все HTTP-вызовы и файловые операции обернуты в try/except: при ошибке
инструмент возвращает понятную строку, а не бросает исключение.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import requests
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Пути
PROJECT_DIR = Path(__file__).resolve().parent
QRCODES_DIR = PROJECT_DIR / "qrcodes"

# ================================================================
# Утилита транслитерации (кириллица → латиница)
# ================================================================

_TRANSLIT_MAP = str.maketrans({
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh',
    'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
    'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
    'ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'Yo','Ж':'Zh',
    'З':'Z','И':'I','Й':'Y','К':'K','Л':'L','М':'M','Н':'N','О':'O',
    'П':'P','Р':'R','С':'S','Т':'T','У':'U','Ф':'F','Х':'Kh','Ц':'Ts',
    'Ч':'Ch','Ш':'Sh','Щ':'Shch','Ъ':'','Ы':'Y','Ь':'','Э':'E','Ю':'Yu','Я':'Ya',
})

def _translit(text: str) -> str:
    """Простая транслитерация кириллицы в латиницу."""
    return text.translate(_TRANSLIT_MAP)


# ================================================================
# 1. Web Search — поиск через DuckDuckGo
# ================================================================

@tool
def web_search(query: str) -> str:
    """Поиск актуальной информации через DuckDuckGo.

    Принимает поисковый запрос и возвращает сводку результатов.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return (
                "Ошибка: не установлена библиотека для поиска. "
                "Установите: pip install ddgs"
            )

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return "Ничего не найдено по вашему запросу."

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Без заголовка")
            url = r.get("href", "")
            snippet = r.get("body", "")
            parts.append(f"{i}. {title}\n   {snippet}\n   {url}")

        return "\n\n".join(parts)
    except Exception as exc:
        logger.error("Ошибка веб-поиска: %s", exc, exc_info=True)
        return f"Ошибка поиска: {exc}"


# ================================================================
# 2. Get Weather — погода по названию города (2 шага)
# ================================================================

@tool
def get_weather(city: str) -> str:
    """Получить текущую погоду в городе.

    Принимает название города и возвращает температуру, скорость ветра
    и код погоды. Использует бесплатный API Open-Meteo (2 шага: геокодинг + погода).
    """
    try:
        # Шаг 1: Геокодинг — название города → координаты
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"

        def _search_geo(name: str) -> dict:
            r = requests.get(geo_url, params={"name": name, "count": 1, "language": "en"}, timeout=30)
            r.raise_for_status()
            return r.json()

        geo_data = _search_geo(city)

        if "results" not in geo_data or not geo_data["results"]:
            # Повторная попытка с транслитерацией (кириллица → латиница)
            latin_city = _translit(city)
            if latin_city != city:
                logger.info("Повторный поиск города с транслитом: %s → %s", city, latin_city)
                geo_data = _search_geo(latin_city)

        if "results" not in geo_data or not geo_data["results"]:
            return (
                f"Город '{city}' не найден. "
                f"Попробуйте указать название латиницей (например, Moscow вместо Москва)."
            )

        location = geo_data["results"][0]
        lat = location["latitude"]
        lon = location["longitude"]
        name = location.get("name", city)
        country = location.get("country", "")

        # Шаг 2: Получение погоды по координатам
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
        }
        weather_resp = requests.get(weather_url, params=weather_params, timeout=30)
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()

        current = weather_data.get("current_weather", {})
        temp = current.get("temperature", "N/A")
        wind = current.get("windspeed", "N/A")
        code = current.get("weathercode", "N/A")

        return (
            f"Погода в {name}, {country}:\n"
            f"  Температура: {temp} °C\n"
            f"  Скорость ветра: {wind} км/ч\n"
            f"  Код погоды: {code}"
        )
    except requests.exceptions.Timeout:
        return "Ошибка: сервер погоды не отвечает. Попробуйте позже."
    except requests.exceptions.RequestException as exc:
        logger.error("Ошибка получения погоды: %s", exc, exc_info=True)
        return f"Ошибка получения погоды: {exc}"
    except Exception as exc:
        logger.error("Неожиданная ошибка get_weather: %s", exc, exc_info=True)
        return f"Неожиданная ошибка: {exc}"


# ================================================================
# 3. Get Crypto Price — курс криптовалюты через CoinGecko
# ================================================================

@tool
def get_crypto_price(coin: str, currency: str = "usd") -> str:
    """Получить текущую цену криптовалюты.

    Принимает идентификатор монеты (например, 'bitcoin', 'ethereum')
    и валюту (по умолчанию 'usd'). Возвращает цену через CoinGecko API.
    """
    try:
        currency = currency.lower().strip()
        coin = coin.lower().strip()
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin, "vs_currencies": currency}
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code == 429:
            return "Лимит запросов CoinGecko превышен. Попробуйте через минуту."
        resp.raise_for_status()

        data = resp.json()
        if not data or coin not in data:
            return (
                f"Криптовалюта '{coin}' не найдена. "
                f"Используйте идентификатор (например, 'bitcoin', 'ethereum')."
            )

        price = data[coin].get(currency, "N/A")
        return f"1 {coin} = {price} {currency.upper()}"
    except requests.exceptions.Timeout:
        return "Ошибка: CoinGecko не отвечает. Попробуйте позже."
    except requests.exceptions.RequestException as exc:
        logger.error("Ошибка получения цены крипто: %s", exc, exc_info=True)
        return f"Ошибка получения цены: {exc}"
    except Exception as exc:
        logger.error("Неожиданная ошибка get_crypto_price: %s", exc, exc_info=True)
        return f"Неожиданная ошибка: {exc}"


# ================================================================
# 4. Get Fiat Rate — курсы фиатных валют (USD → EUR, RUB, GEL)
# ================================================================

@tool
def get_fiat_rate(base: str = "USD", target: str = "EUR,RUB,GEL") -> str:
    """Получить курсы фиатных валют.

    Принимает базовую валюту (по умолчанию 'USD') и целевые валюты
    (по умолчанию 'EUR,RUB,GEL'). Возвращает курсы через бесплатный API.
    """
    try:
        base = base.upper().strip()
        targets = [t.strip().upper() for t in target.split(",")]
        symbols = ",".join(targets)

        url = f"https://open.er-api.com/v6/latest/{base}"
        resp = requests.get(url, timeout=10)

        if resp.status_code == 400:
            return f"Ошибка: валюта '{base}' не распознана. Используйте ISO-код (USD, EUR, RUB и т.д.)."
        resp.raise_for_status()

        data = resp.json()
        rates = data.get("conversion_rates", data.get("rates", {}))
        if not rates:
            return "Курсы не найдены."

        # Фильтруем только запрошенные валюты
        filtered = {k: v for k, v in rates.items() if k in targets}
        if not filtered:
            return f"Нет курсов для запрошенных валют: {symbols}"

        lines = [f"Курсы валют к {base}:"]
        for curr, rate in filtered.items():
            lines.append(f"  1 {base} = {rate:.4f} {curr}")

        return "\n".join(lines)
    except requests.exceptions.Timeout:
        return "Ошибка: сервер курсов валют не отвечает. Попробуйте позже."
    except requests.exceptions.RequestException as exc:
        logger.error("Ошибка получения курса: %s", exc, exc_info=True)
        return f"Ошибка получения курса: {exc}"
    except Exception as exc:
        logger.error("Неожиданная ошибка get_fiat_rate: %s", exc, exc_info=True)
        return f"Неожиданная ошибка: {exc}"


# ================================================================
# 5. Generate QR Code — генерация QR-кода
# ================================================================

@tool
def generate_qr_code(text: str) -> str:
    """Генерировать QR-код из текста/URL и сохранить в ./qrcodes/.

    Возвращает путь к сохранённому файлу.
    """
    try:
        import qrcode
    except ImportError:
        return "Ошибка: не установлена библиотека qrcode. Установите: pip install qrcode"

    try:
        QRCODES_DIR.mkdir(parents=True, exist_ok=True)

        # Генерируем QR-код
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img = img.convert("RGB")

        # Уникальное имя файла
        safe_name = re.sub(r"[^\w\-_.]", "_", text[:50])
        filename = f"qrcode_{safe_name}_{len(list(QRCODES_DIR.glob('qrcode_*'))) + 1}.png"
        filepath = QRCODES_DIR / filename

        img.save(str(filepath))
        return f"QR-код сохранён: {filepath}"
    except Exception as exc:
        logger.error("Ошибка генерации QR-кода: %s", exc, exc_info=True)
        return f"Ошибка генерации QR-кода: {exc}"


# ================================================================
# 6. Read / Write File — файловый ввод-вывод
# ================================================================

@tool
def read_file(filepath: str) -> str:
    """Прочитать текстовый файл и вернуть его содержимое.

    Работает с файлами в рабочей директории проекта.
    """
    try:
        file_path = Path(filepath)
        # Безопасность: разрешаем только файлы в проекте
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(PROJECT_DIR.resolve())):
            return f"Ошибка: доступ к файлам за пределами проекта запрещён."
        if not file_path.exists():
            return f"Файл не найден: {filepath}"
        if not file_path.is_file():
            return f"Путь не является файлом: {filepath}"

        content = file_path.read_text(encoding="utf-8")
        # Ограничение: возвращаем первые 4000 символов
        if len(content) > 4000:
            content = content[:4000] + "\n\n… (файл сокращён)"
        return content
    except PermissionError:
        return f"Ошибка: нет прав на чтение файла {filepath}"
    except UnicodeDecodeError:
        return f"Ошибка: файл {filepath} не является текстовым."
    except Exception as exc:
        logger.error("Ошибка чтения файла %s: %s", filepath, exc, exc_info=True)
        return f"Ошибка чтения файла: {exc}"


@tool
def write_file(filepath: str, content: str) -> str:
    """Записать текст в файл. Создаёт каталог, если его нет."""
    try:
        file_path = Path(filepath)
        # Безопасность: разрешаем только файлы в проекте
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(PROJECT_DIR.resolve())):
            return f"Ошибка: доступ к файлам за пределами проекта запрещён."

        # Создаём каталог, если нужно
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Успешно записано {len(content)} символов в {filepath}"
    except PermissionError:
        return f"Ошибка: нет прав на запись в файл {filepath}"
    except Exception as exc:
        logger.error("Ошибка записи файла %s: %s", filepath, exc, exc_info=True)
        return f"Ошибка записи файла: {exc}"


# ================================================================
# Список всех инструментов (для удобного импорта)
# ================================================================

ALL_TOOLS = [
    web_search,
    get_weather,
    get_crypto_price,
    get_fiat_rate,
    generate_qr_code,
    read_file,
    write_file,
]
