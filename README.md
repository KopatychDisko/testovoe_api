# testovoe_api

Мини-синхронизатор заявок: забирает заявки с `https://test.ooobs.ru/api/orders`, нормализует телефоны к `+7XXXXXXXXXX`, дедуплицирует по телефону (максимальный `amount`, при равенстве более поздний `created_at`) и отдаёт JSON `{clients, stats}`.

Живой URL: https://testjob-three.vercel.app/

## Секреты

Секретов нет: источник заявок публичный. Если появятся, они хранятся в `.env` (в `.gitignore`, в репозитории только `.env.example`), а на Vercel задаются через Environment Variables.
