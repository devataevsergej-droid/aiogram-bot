# Запуск локально

cd "C:\Users\Lenovo\SaaS Bot\lisakovsk-job-bot\src"

$env:PYTHONPATH="."

python -m job_lisakovsk_bot.main

# Полезно

Ctrl+C — остановка бота

РЕНДЕР
вход xерез гугл lisakovsk.job.bot@gmail.com
https://lisakovsk-job-bot.onrender.com

второй рендер на еленаФеликс64 надо перевести попробовать на работаЛисаковск


# DEV_NOTES_JOB_LSK.md

STATUS: ACTIVE DEVELOPMENT

PROJECT: Lisakovsk Job Bot

LAST REVIEW: 2026-06-13

---

# Быстрый запуск локально

```powershell

cd "C:\Users\Lenovo\SaaS Bot\lisakovsk-job-bot\src"

$env:PYTHONPATH="."

python -m job_lisakovsk_bot.main

```

Остановка:

```text
Ctrl + C
```

---

# Текущее состояние проекта

PHASE:

```text
PRE-LAUNCH
```

Проект ещё не деплоился для пользователей.

Работает только в тестовом режиме.

Запуск производится локально через VS Code.

---

# Главная цель сейчас

Подготовить Job Bot к первому публичному запуску.

Текущий приоритет:

```text
Employer UX
↓
Продвижение вакансий
↓
Платные функции
↓
Публикация
```

---

# Что уже работает

## Employer Flow

```text
Компания
↓
Создание вакансии
↓
Модерация
↓
Публикация
↓
Отклики
↓
Просмотр кандидатов
```

---

## Реализовано

```text
✅ Компании

✅ Создание вакансий

✅ Модерация

✅ Публикация в канал

✅ Отклики

✅ Карточки кандидатов

✅ Просмотр работодателем анкет
```

---

# В работе

```text
🟡 Редактирование вакансий

🟡 Продвижение вакансий

🟡 Платные функции
```

---

# Следующие задачи

## Высокий приоритет

```text
1. Завершить Employer UX

2. Продвижение вакансий

3. Монетизация работодателей

4. Push уведомления

5. Первый публичный запуск
```

---

# Важные правила

## MVP First

Не строить сложную архитектуру раньше времени.

Сначала:

```text
Рабочий продукт
↓
Первые пользователи
↓
Обратная связь
↓
Улучшения
```

---

## Knowledge Before Refactor

Запрещены крупные рефакторинги без ревизии знаний.

---

## Evolution Instead Of Renaming

Существующие таблицы не переименовываются без необходимости.

Legacy считается допустимым.

---

## Source Of Truth Over Conversation

Решение считается принятым только после фиксации в документации.

---

# Текущие сущности

## Companies

```text
companies
```

---

## Job Seekers

```text
job_seekers
```

---

## Vacancies

```text
job_vacancies
```

---

## Notifications

```text
job_notifications
```

---

# Render

Основной Render:

```text
https://lisakovsk-job-bot.onrender.com
```

Вход:

```text
Google Account

lisakovsk.job.bot@gmail.com
```

---

# Что нельзя ломать

```text
Рабочий Employer Flow

Модерацию

Публикацию в канал

Отклики

Карточки кандидатов
```

---

# Перед любым изменением

Проверить:

```text
Что изменяем?

Какой сценарий затрагиваем?

Не ломаем ли Employer Flow?

Не создаём ли дублирующую логику?
```

---

# Контекст для новых AI-агентов

Если агент подключился впервые:

Главная задача проекта сейчас:

```text
Запустить первый рабочий Job Bot
и получить первых работодателей.
```

Не предлагать:

```text
массовые рефакторинги
миграции БД
переименование таблиц
полный переход на микросервисы
```

до появления реальных пользователей.

---

# Полезные ссылки

Render:
https://lisakovsk-job-bot.onrender.com


Notion:
Lisakovsk Hub Knowledge Base


GitHub:
(добавить ссылку после подключения репозитория)


Проверка лимитов Джипити и Кодекс:
https://chatgpt.com/codex/cloud/settings/analytics?utm_source=chatgpt.com#usage


ПРОМПТЫ НЕЙРОМАРКЕТИНГ И ПРОЧЕЕ:

