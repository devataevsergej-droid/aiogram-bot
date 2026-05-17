# Деплой «Работа Лисаковск»

## 1. GitHub

Новый репозиторий: `https://github.com/lisakovsk-dev/lisakovsk-job-bot`.

```bash
git remote add github https://github.com/lisakovsk-dev/lisakovsk-job-bot.git
git branch -M main
git push -u github main
```

Если GitHub запросит пароль, нужен Personal Access Token с правом `contents:write`.

## 2. Render env vars

В Render → сервис `lisakovsk-job-bot` → Environment добавьте переменные из `.env.example`.

Обязательные значения:

- `BOT_TOKEN` — токен `@LisakovskJobBot` из BotFather.
- `BOT_USERNAME=LisakovskJobBot`
- `SUPABASE_URL=https://kmjrccppuykjsjycygzy.supabase.co`
- `SUPABASE_KEY` — Supabase anon или service role key из Settings → Data API.
- `ADMIN_ID=8614783423`
- `ADMIN_CHAT_ID=-1003908379906`
- `CHANNEL_ID=-1003985989395`
- `WEBHOOK_URL=https://lisakovsk-job-bot.onrender.com/webhook`
- `WEBHOOK_PATH=/webhook`

Не коммитьте реальные токены и ключи в GitHub.

## 3. Supabase SQL

Откройте Supabase → SQL Editor → вставьте и выполните `db/schema.sql`.

Скрипт создаёт:

- `job_seekers`
- `job_vacancies`
- `job_notifications`
- `payments`
- `usage_limits`
- `referrals`
- `scheduled_unpins`
- `scheduled_tasks`

Также включает RLS и server-side политики для роли `anon`, чтобы бот мог работать с ключом из Render env.

## 4. Render deploy

После push Render должен сделать auto-deploy. Если нет: Manual Deploy → Deploy latest commit.

Проверка:

```bash
curl https://lisakovsk-job-bot.onrender.com/health
```

Ответ должен быть:

```text
OK
```

## 5. Telegram webhook

Приложение само вызывает `set_webhook`, если задан `WEBHOOK_URL`.

Для ручной проверки/установки:

```bash
curl "https://api.telegram.org/bot$BOT_TOKEN/setwebhook?url=https://lisakovsk-job-bot.onrender.com/webhook"
```

Ожидаемый ответ: `{"ok":true,...}`.

## 6. Telegram Stars

В BotFather:

1. `/mybots`
2. `@LisakovskJobBot`
3. Payments
4. Подключить Stars
5. Пройти тест оплаты в боте

## 7. Cron-job / UptimeRobot

URL для пинга каждые 10 минут:

```text
https://lisakovsk-job-bot.onrender.com/health
```
