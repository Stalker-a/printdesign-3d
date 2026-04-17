# 3d_design

Готовый сайт студии 3D-печати с:

- реальным AI-чатом через OpenAI API
- отправкой обращений из чата в Telegram
- отправкой заявок из формы в Telegram
- Python-сервером без внешних зависимостей

## Что внутри

- `index.html` — главная страница
- `css/style.css` — стили
- `js/main.js` — логика интерфейса, чата и формы
- `server.py` — сервер, OpenAI proxy и отправка в Telegram
- `.env.example` — шаблон конфигурации

## Быстрый запуск

2. Заполните:
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Запустите сервер:

```powershell
python server.py
```

4. Откройте:

```text
http://127.0.0.1:8000
```

## Важно про Telegram


Рекомендуемый путь:

1. Создайте бота через `@BotFather`
2. Напишите этому боту из аккаунта, в который должны приходить заявки
3. Получите numeric `chat_id`
4. Запишите его в `.env` как `TELEGRAM_CHAT_ID`

Можно использовать helper:

```powershell
python get_telegram_chat_id.py
```

Поле `TELEGRAM_TARGET=@SHAKOTAN2` оставлено как запасной вариант, но для личной переписки Telegram может этого не принять.

## Что отправляется в Telegram

- каждое обращение из AI-чата
- каждая заявка из контактной формы

## OpenAI

Сервер использует endpoint `POST /v1/responses`.
Модель задается через `OPENAI_MODEL`.

По умолчанию:

```text
OPENAI_MODEL=gpt-5.4-mini
```
