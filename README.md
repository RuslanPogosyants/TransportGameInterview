# Cargo Guild — interview backend

Небольшая экономическая игра: игрок принимает контракты, покупает перевозку, отправляет груз и получает награду. Данные хранятся локально в SQLite. Аутентификации нет: `player_id` передаётся явно — это намеренное упрощение задания.

## Запуск

```bash
docker compose up --build
```

API будет доступен на `http://localhost:8000`, интерактивная Swagger-документация — на `http://localhost:8000/docs`.

```bash
curl http://localhost:8000/health
curl http://localhost:8000/orders
curl -X POST http://localhost:8000/orders/1/quotes -H 'content-type: application/json' -d '{"player_id":1}'
```

Начальный игрок: `id=1`, баланс `500`. В Docker база находится в именованном томе `cargo_guild_data`; чтобы начать новую игру, выполните `docker compose down -v`.

## Проверка

```bash
docker compose run --rm api pytest -q
```

Основные правила: цена всегда считается сервером; активных заказов максимум три; отмена возвращает стоимость только для `ready`; доставка начисляет полное вознаграждение в срок либо половину при опоздании. Прибыль увеличивается на награду минус зафиксированную стоимость перевозки.
