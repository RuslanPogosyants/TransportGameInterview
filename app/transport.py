"""Небольшая коллекция несовместимых адаптеров перевозчиков.

Файл специально содержит и модели, и расчёт, и преобразование ответов провайдеров:
так его удобно разбирать на собеседовании и постепенно рефакторить.
"""
from dataclasses import dataclass
from typing import Any

ROUTES = {
    frozenset(("stone", "port")): 100,
    frozenset(("stone", "ice")): 200,
    frozenset(("port", "ice")): 300,
}

@dataclass
class CargoRequest:
    origin: str
    destination: str
    cargo: str
    weight_kg: int
    priority: str = "normal"
    temperature: str = "ambient"
    fragile: bool = False
    hazardous: bool = False

@dataclass
class NormalizedQuote:
    carrier: str
    price_coins: int
    delivery_days: int
    accepted: bool
    reason: str | None = None
    source_payload: dict[str, Any] | None = None

class CarrierAdapter:
    code = "base"
    def can_take(self, request: CargoRequest) -> tuple[bool, str | None]:
        return True, None
    def raw_quote(self, request: CargoRequest) -> dict[str, Any]:
        raise NotImplementedError
    def normalize(self, payload: dict[str, Any]) -> NormalizedQuote:
        raise NotImplementedError

class CaravanAdapter(CarrierAdapter):
    code = "caravan"
    def can_take(self, request):
        if request.weight_kg > 100: return False, "maximum weight is 100 kg"
        if request.hazardous: return False, "hazardous cargo requires a special license"
        return True, None
    def raw_quote(self, request):
        distance = ROUTES[frozenset((request.origin, request.destination))]
        price = 10 + 2 * request.weight_kg + distance // 10
        if request.priority == "urgent": price += 35
        return {"vendor": "old-caravan", "total": price, "days": 3, "currency": "coin"}
    def normalize(self, payload):
        return NormalizedQuote(self.code, int(payload["total"]), int(payload["days"]), True, source_payload=payload)

class AirshipAdapter(CarrierAdapter):
    code = "airship"
    def can_take(self, request):
        if request.weight_kg > 20: return False, "maximum weight is 20 kg"
        if request.cargo not in {"food", "artifacts"}: return False, f"does not carry {request.cargo}"
        if request.temperature == "frozen": return False, "no frozen storage"
        return True, None
    def raw_quote(self, request):
        distance = ROUTES[frozenset((request.origin, request.destination))]
        coins = 40 + 3 * request.weight_kg + distance // 5
        return {"provider": "sky-corp", "cost_cents": coins * 100, "eta_hours": 48, "weight_grams": request.weight_kg * 1000}
    def normalize(self, payload):
        return NormalizedQuote(self.code, int(payload["cost_cents"]) // 100, (int(payload["eta_hours"]) + 23) // 24, True, source_payload=payload)

class PortalAdapter(CarrierAdapter):
    code = "portal"
    def can_take(self, request):
        if {request.origin, request.destination} != {"stone", "ice"}: return False, "does not operate on this route"
        if request.cargo != "artifacts": return False, "does not carry this cargo"
        if request.weight_kg > 50: return False, "maximum weight is 50 kg"
        if request.fragile: return False, "portal transit is unsafe for fragile cargo"
        return True, None
    def raw_quote(self, request):
        return {"provider": "portal-labs", "amount": 100 + 5 * request.weight_kg, "duration": "PT24H", "distance_m": ROUTES[frozenset((request.origin, request.destination))] * 1000}
    def normalize(self, payload):
        duration = payload.get("duration", "PT24H")
        hours = int(duration.replace("PT", "").replace("H", "") or 24)
        return NormalizedQuote(self.code, int(payload["amount"]), (hours + 23) // 24, True, source_payload=payload)

ADAPTERS = [CaravanAdapter(), AirshipAdapter(), PortalAdapter()]

def build_request(row, priority="normal", temperature="ambient", fragile=False, hazardous=False):
    return CargoRequest(row["origin"], row["destination"], row["cargo"], row["weight"], priority, temperature, fragile, hazardous)

def calculate_quotes(row, today, deadline_days=None, **kwargs):
    request = build_request(row, **kwargs)
    result = []
    unavailable = []
    for adapter in ADAPTERS:
        allowed, reason = adapter.can_take(request)
        if not allowed:
            unavailable.append({"carrier": adapter.code, "reason": reason})
            continue
        quote = adapter.normalize(adapter.raw_quote(request))
        late = deadline_days is not None and quote.delivery_days > deadline_days
        result.append({"carrier": quote.carrier, "price_coins": quote.price_coins, "delivery_days": quote.delivery_days,
                       "estimated_arrival_day": today + quote.delivery_days, "expected_reward_coins": row["reward"],
                       "expected_profit_coins": row["reward"] - quote.price_coins, "will_be_late": late,
                       "source_payload": quote.source_payload})
    result.sort(key=lambda x: (-x["expected_profit_coins"], x["delivery_days"], x["carrier"]))
    return {"available": result, "unavailable": unavailable}

def carrier_health(day):
    return [{"carrier": x.code, "available": not (x.code == "airship" and day % 5 == 0), "checked_day": day} for x in ADAPTERS]

def disruption(day, carrier):
    if carrier == "airship" and day % 5 == 0: return {"delay_days": 2, "reason": "airport closure"}
    if carrier == "caravan" and day % 7 == 0: return {"delay_days": 1, "reason": "roadworks"}
    if carrier == "portal" and day % 11 == 0: return {"delay_days": 3, "reason": "portal calibration"}
    return {"delay_days": 0, "reason": None}

def normalize_external_status(provider, payload):
    value = str(payload.get("status", "unknown")).lower()
    mapping = {"ok": "delivered", "done": "delivered", "delivered": "delivered", "failed": "broken", "lost": "lost", "delay": "delayed"}
    return {"provider": provider, "status": mapping.get(value, "unknown"), "raw": payload}

def shipment_label(row):
    return f"{row['carrier']} #{row['id']} {row['status']} {row['price']} coins"

def route_code(origin, destination):
    return f"{origin[:2].upper()}-{destination[:2].upper()}"

def route_distance(origin, destination):
    return ROUTES.get(frozenset((origin, destination)), 0)

def compare_quotes(quotes):
    return sorted(quotes, key=lambda x: (x.get("price_coins", 10**9), x.get("delivery_days", 10**9)))

# Старые helper-функции оставлены рядом с новыми адаптерами: часть кода проекта
# продолжает использовать их напрямую.
def is_city(value): return value in {"stone", "port", "ice"}
def is_cargo(value): return value in {"ore", "food", "artifacts"}
def is_route(origin, destination): return frozenset((origin, destination)) in ROUTES
def has_distance(origin, destination): return route_distance(origin, destination) > 0
def kilos_to_grams(value): return int(value) * 1000
def grams_to_kilos(value): return int(value) // 1000
def coins_to_cents(value): return int(value) * 100
def cents_to_coins(value): return int(value) // 100
def hours_to_days(value): return (int(value) + 23) // 24
def priority_multiplier(priority): return {"normal": 1, "urgent": 2, "express": 3}.get(priority, 1)
def cargo_multiplier(cargo): return {"ore": 1, "food": 2, "artifacts": 4}.get(cargo, 1)
def weather_multiplier(weather): return {"clear": 1, "wind": 2, "fog": 3, "storm": 5}.get(weather, 1)
def route_risk(origin, destination): return {100: 10, 200: 25, 300: 40}.get(route_distance(origin, destination), 80)
def route_name(origin, destination): return f"{origin.title()} - {destination.title()}"
def route_reverse(code):
    parts = code.split("-")
    return "-".join(reversed(parts)) if len(parts) == 2 else code
def provider_name(carrier): return {"caravan": "Old Caravan", "airship": "Sky Corp", "portal": "Portal Labs"}.get(carrier, "Unknown")
def provider_currency(carrier): return "cents" if carrier == "airship" else "coins"
def provider_weight_unit(carrier): return "grams" if carrier == "airship" else "kg"
def provider_eta(carrier): return {"caravan": 72, "airship": 48, "portal": 24}.get(carrier, 999)
def provider_supports_fragile(carrier): return carrier == "caravan"
def provider_supports_hazardous(carrier): return carrier == "caravan"
def provider_supports_temperature(carrier, temperature): return not (carrier == "airship" and temperature == "frozen")
def provider_max_weight(carrier): return {"caravan": 100, "airship": 20, "portal": 50}.get(carrier, 0)
def provider_cargoes(carrier): return {"caravan": ["ore", "food", "artifacts"], "airship": ["food", "artifacts"], "portal": ["artifacts"]}.get(carrier, [])
def provider_routes(carrier): return {"caravan": list(ROUTES), "airship": list(ROUTES), "portal": [frozenset(("stone", "ice"))]}.get(carrier, [])
def provider_is_open(carrier, day): return not (carrier == "airship" and day % 5 == 0)
def provider_message(carrier, status): return f"{provider_name(carrier)} says: {status}"
def quote_is_profitable(quote): return quote.get("expected_profit_coins", -1) > 0
def quote_is_fast(quote): return quote.get("delivery_days", 999) <= 2
def quote_is_late(quote): return bool(quote.get("will_be_late"))
def quote_score(quote): return quote.get("expected_profit_coins", 0) * 10 - quote.get("delivery_days", 0) * 3
def quote_rank(quote, index=0): return {"rank": index + 1, "carrier": quote.get("carrier"), "score": quote_score(quote)}
def rank_quotes(quotes): return [quote_rank(x, i) for i, x in enumerate(sorted(quotes, key=quote_score, reverse=True))]
def choose_cheapest(quotes): return min(quotes, key=lambda x: x.get("price_coins", 10**9), default=None)
def choose_fastest(quotes): return min(quotes, key=lambda x: x.get("delivery_days", 10**9), default=None)
def choose_profit(quotes): return max(quotes, key=lambda x: x.get("expected_profit_coins", -10**9), default=None)
def choose_safe(quotes): return min(quotes, key=lambda x: x.get("risk", 100), default=None)
def add_weather_delay(days, weather): return days + weather_multiplier(weather) // 3
def add_priority_delay(days, priority): return max(1, days - priority_multiplier(priority) + 1)
def apply_disruption_to_quote(quote, day):
    item = dict(quote)
    event = disruption(day, item.get("carrier"))
    item["delivery_days"] = item.get("delivery_days", 0) + event["delay_days"]
    item["disruption"] = event["reason"]
    return item
def validate_request(request):
    errors = []
    if not is_city(request.origin): errors.append("unknown origin")
    if not is_city(request.destination): errors.append("unknown destination")
    if request.origin == request.destination: errors.append("same city")
    if not is_cargo(request.cargo): errors.append("unknown cargo")
    if request.weight_kg < 1: errors.append("weight must be positive")
    return errors
def request_as_dict(request): return request.__dict__.copy()
def request_from_dict(value): return CargoRequest(**value)
def quote_as_dict(quote): return quote.__dict__.copy() if hasattr(quote, "__dict__") else dict(quote)
def quote_from_dict(value): return NormalizedQuote(**value)
def raw_payload_size(payload): return len(str(payload))
def raw_payload_has(payload, key): return key in payload and payload[key] is not None
def raw_status(payload): return str(payload.get("status", "unknown")).lower()
def raw_error(payload): return payload.get("error") or payload.get("message")
def raw_success(payload): return not raw_error(payload) and raw_status(payload) not in {"failed", "error"}
def fallback_quote(carrier, request):
    return {"carrier": carrier, "price_coins": provider_max_weight(carrier) + request.weight_kg, "delivery_days": provider_eta(carrier) // 24, "fallback": True}
def make_failure(carrier, reason): return {"carrier": carrier, "accepted": False, "reason": reason}
def make_success(carrier, price, days): return {"carrier": carrier, "accepted": True, "price_coins": price, "delivery_days": days}
def batch_quote(rows, today): return [calculate_quotes(row, today) for row in rows]
def flatten_quotes(items): return [quote for result in items for quote in result.get("available", [])]
def unavailable_carriers(result): return [x["carrier"] for x in result.get("unavailable", [])]
def available_carriers(result): return [x["carrier"] for x in result.get("available", [])]
def quote_summary(result): return {"available": len(result.get("available", [])), "unavailable": len(result.get("unavailable", []))}
def route_matrix(): return {f"{a}-{b}": route_distance(a, b) for a in ("stone", "port", "ice") for b in ("stone", "port", "ice") if a != b}
def carrier_matrix(day): return {x.code: {"open": provider_is_open(x.code, day), "max_weight": provider_max_weight(x.code)} for x in ADAPTERS}
def audit_adapters(): return [{"code": x.code, "has_quote": callable(getattr(x, "raw_quote", None)), "has_normalizer": callable(getattr(x, "normalize", None))} for x in ADAPTERS]

