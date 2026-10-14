# Telegram AI-агент (LangChain + ProxyAPI)

Модульный Telegram-бот на базе **LangChain** и **aiogram 3.x**, который понимает
естественный язык, самостоятельно выбирает инструменты (поиск, погода, курсы валют,
крипта, QR-коды, файловый ввод-вывод) и выполняет задачи. LLM подключается через
OpenAI-совместимый провайдер **ProxyAPI**.

## Архитектура

```
Telegram ⇄ aiogram (run.py) ⇄ AgentExecutor (agent.py)
                                    │
                        ┌───────────┼───────────────┐
                     ChatOpenAI   tools.py      memory.py
                   (ProxyAPI)   (6 инструментов) (память по chat_id)
                        │             │               │
                   ProxyAPI API   внешние API   memory_{chat_id}.json
```

| Файл             | Назначение                                                        |
|------------------|------------------------------------------------------------------|
| `config.py`      | Загрузка и валидация переменных окружения (pydantic-settings)     |
| `tools.py`       | 6 инструментов агента на декораторе `@tool`                       |
| `memory.py`      | Изолированная по `chat_id` история диалогов в JSON                |
| `agent.py`       | Инициализация LLM, инструментов и `AgentExecutor`                 |
| `run.py`         | Точка входа: инициализация бота aiogram и роутеров                |

## Инструменты агента

- **web_search** — поиск актуальной информации через DuckDuckGo.
- **get_weather** — погода по названию города (геокодинг + Open-Meteo):
  температура (°C), скорость ветра (км/ч), код погоды.
- **get_crypto_price** — курс криптовалюты через CoinGecko.
- **get_fiat_rate** — курсы фиатных валют (USD → EUR, RUB, GEL).
- **generate_qr_code** — генерация QR-кода и сохранение в `./qrcodes/`.
- **read_file / write_file** — чтение и запись текстовых файлов в рабочей директории.

## Требования

- Python **3.10+**

## Установка

1. Клонируйте/скачайте проект и перейдите в его каталог.

2. Создайте виртуальное окружение:

   ```bash
   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate

   # Windows (PowerShell)
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   ```

3. Установите зависимости:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Создайте файл `.env` из шаблона и заполните значения:

   ```bash
   # Linux / macOS
   cp .env.example .env

   # Windows (PowerShell)
   Copy-Item .env.example .env
   ```

   Минимально необходимые значения:

   ```dotenv
   TG_BOT_API_KEY=<токен от @BotFather>
   PROXYAPI_API_KEY=<ключ с https://proxyapi.ru>
   ```

## Запуск

```bash
python run.py
```

После запуска откройте чат с ботом в Telegram и напишите сообщение, например:

- `Какая погода в Сочи?`
- `Курс биткоина в долларах`
- `Найди последние новости про LangChain`
- `Сделай QR-код для https://example.com`

Каждый пользователь общается в собственной изолированной сессии — история диалога
сохраняется в файле `memory_{chat_id}.json` и не пересекается с другими пользователями.

## Структура проекта

```text
agent_project/
├── .env.example          # Шаблон переменных окружения
├── .gitignore            # Исключения
├── requirements.txt      # Зависимости
├── README.md             # Эта инструкция
├── config.py             # Конфигурация
├── tools.py              # Инструменты агента
├── memory.py             # Память по chat_id
├── agent.py              # LLM + AgentExecutor
└── run.py                # Точка входа
```

## Примечания

- Weather и Crypto используют бесплатные API без ключей. Переменные `WEATHER_API_KEY`
  и `CURRENCY_API_KEY` оставлены в `.env` для будущей расширяемости.
- При ошибке внешнего API (город не найден, лимит запросов, отсутствующий файл)
  инструмент возвращает понятную строку ошибки, которую LLM передаст пользователю,
  вместо падения с исключением.
- Файлы памяти (`memory_*.json`), каталог `qrcodes/` и `.env` добавлены в `.gitignore`.
