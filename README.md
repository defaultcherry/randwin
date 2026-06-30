# Telegram Giveaway Mini App

Кратко:
- `app/` - FastAPI backend + Telegram bot.
- `frontend/` - React Mini App, собирается через Vite/Node.js.
- `app/static/dist/` - результат сборки фронтенда.

## Что реализовано
- Создание розыгрыша в личном чате с ботом.
- Выбор канала через кнопку `request_chat`.
- Проверка прав администратора у пользователя и у бота в выбранном канале.
- Публикация поста в канал по времени старта.
- Участие через Telegram Mini App с проверкой `initData` и hCaptcha.
- Проверка подписки на канал перед добавлением в участники.
- Завершение розыгрыша, выбор победителей, редактирование оригинального поста.
- Экран результатов с именами, аватарами или заглушками.

## Цвет кнопки и время
- Цвет кнопки выбирается только из Telegram-style вариантов: `primary`, `success`, `danger` или `default`.
- Дата и время старта вводятся в МСК, внутри системы сохраняются в UTC.
- Время завершения всегда задаётся как длительность относительно старта.
- Если старт уже в прошлом, бот предупреждает об отправке поста сразу.

## Переменные окружения
Скопируйте `.env.example` и заполните:
- `BOT_TOKEN`
- `BASE_SITE`
- `ADMIN_ID`
- `HCAPTCHA_SITE_KEY`
- `HCAPTCHA_SECRET`

## Запуск backend
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Сборка frontend
```bash
npm install
npm run build
```

Сборка попадет в `app/static/dist/mini-app.js`.
Для hCaptcha добавьте `VITE_HCAPTCHA_SITE_KEY` в корневой `.env`.

## Локальная разработка фронтенда
```bash
npm run dev
```

Vite поднимется с прокси на `http://localhost:8000` для `/api`, `/webhook` и `/static`.

## Примечания
- Бот работает с любым каналом, который администратор выберет в чате с ботом.
- Для публикации и редактирования постов бот должен быть администратором канала.
- Проверка данных Telegram выполняется по `initData` на backend.
