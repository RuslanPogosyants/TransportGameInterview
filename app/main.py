import os
import sqlite3
import json
import random
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, Response
from pydantic import BaseModel, Field
from . import transport, finance

DB_PATH = os.getenv("DATABASE_PATH", "cargo_guild.db")
app = FastAPI(title="Cargo Guild", version="1.0.0", description="Backend test assignment. Swagger: /docs")

CITIES = {"stone", "port", "ice"}
GOODS = {"ore", "food", "artifacts"}
DISTANCES = {frozenset(("stone", "port")): 100, frozenset(("stone", "ice")): 200, frozenset(("port", "ice")): 300}
CARRIERS = {
    "caravan": {"max_weight": 100, "goods": GOODS, "routes": None, "days": 3},
    "airship": {"max_weight": 20, "goods": {"food", "artifacts"}, "routes": None, "days": 2},
    "portal": {"max_weight": 50, "goods": {"artifacts"}, "routes": {frozenset(("stone", "ice"))}, "days": 1},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS game (id INTEGER PRIMARY KEY CHECK(id=1), day INTEGER NOT NULL, generation INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY, name TEXT NOT NULL, balance INTEGER NOT NULL, profit INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, origin TEXT NOT NULL, destination TEXT NOT NULL, cargo TEXT NOT NULL,
 weight INTEGER NOT NULL, reward INTEGER NOT NULL, accept_until_day INTEGER NOT NULL, delivery_days INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'available', player_id INTEGER, created_day INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS shipments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE, player_id INTEGER NOT NULL, carrier TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'ready', price INTEGER NOT NULL, carrier_days INTEGER NOT NULL, reward INTEGER NOT NULL,
 due_day INTEGER NOT NULL, dispatched_day INTEGER, arrival_day INTEGER, delivered_day INTEGER,
 FOREIGN KEY(order_id) REFERENCES orders(id), FOREIGN KEY(player_id) REFERENCES players(id)
);
CREATE TABLE IF NOT EXISTS wallet_operations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL,
 shipment_id INTEGER, game_day INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS shipment_events (id INTEGER PRIMARY KEY AUTOINCREMENT, shipment_id INTEGER, player_id INTEGER, event_type TEXT NOT NULL, details TEXT, game_day INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS game_events (id INTEGER PRIMARY KEY AUTOINCREMENT, game_day INTEGER NOT NULL, event_type TEXT NOT NULL, title TEXT NOT NULL, effect TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS player_upgrades (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, upgrade TEXT NOT NULL, level INTEGER NOT NULL DEFAULT 1, UNIQUE(player_id, upgrade));
CREATE TABLE IF NOT EXISTS licenses (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, license TEXT NOT NULL, expires_day INTEGER NOT NULL, UNIQUE(player_id, license));
CREATE TABLE IF NOT EXISTS auctions (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, player_id INTEGER NOT NULL, bid_coins INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open', created_day INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS carrier_webhooks (id INTEGER PRIMARY KEY AUTOINCREMENT, shipment_id INTEGER, provider TEXT NOT NULL, provider_status TEXT NOT NULL, payload TEXT NOT NULL, created_day INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS taxes (id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL, game_day INTEGER NOT NULL);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def row_dict(row):
    return dict(row) if row else None


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)
        for table, column, definition in [
            ("players", "reputation", "INTEGER NOT NULL DEFAULT 0"),
            ("players", "loan_principal", "INTEGER NOT NULL DEFAULT 0"),
            ("players", "loan_rate", "INTEGER NOT NULL DEFAULT 5"),
            ("game", "weather", "TEXT NOT NULL DEFAULT 'clear'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError:
                pass
        if not conn.execute("SELECT 1 FROM game WHERE id=1").fetchone():
            conn.execute("INSERT INTO game(id, day, generation) VALUES(1, 1, 0)")
            conn.execute("INSERT INTO players(id, name, balance) VALUES(1, 'Guildmaster', 500)")
            generate_orders(conn, 1, 0, initial=True)


def game_day(conn):
    return conn.execute("SELECT day FROM game WHERE id=1").fetchone()["day"]


def add_event(conn, shipment_id, player_id, kind, details, day):
    conn.execute("INSERT INTO shipment_events(shipment_id,player_id,event_type,details,game_day) VALUES(?,?,?,?,?)", (shipment_id, player_id, kind, details, day))


def add_game_event(conn, day, kind, title, effect):
    conn.execute("INSERT INTO game_events(game_day,event_type,title,effect) VALUES(?,?,?,?)", (day, kind, title, effect))


def weather_for(day):
    return ["clear", "wind", "fog", "clear", "storm"][day % 5]


def tax_for(amount, reputation):
    rate = 10 if reputation < 20 else 5 if reputation < 60 else 2
    return max(1, amount * rate // 100)


def generate_orders(conn, day, generation, initial=False):
    # Fixed patterns keep a game reproducible and intentionally include edge cases.
    patterns = [
        ("stone", "port", "ore", 80, 380, 4, 4), ("port", "ice", "food", 10, 260, 3, 2),
        ("stone", "ice", "artifacts", 35, 500, 2, 1), ("ice", "stone", "ore", 100, 300, 2, 3),
        ("port", "stone", "food", 20, 40, 1, 1), ("ice", "port", "artifacts", 18, 450, 5, 3),
        ("stone", "ice", "artifacts", 51, 420, 3, 2), ("port", "stone", "ore", 90, 520, 5, 5),
    ]
    count = len(patterns) if initial else 3
    start = 0 if initial else generation * 3
    for index in range(count):
        origin, dest, cargo, weight, reward, acceptance, delivery = patterns[(start + index) % len(patterns)]
        bonus = (generation % 4) * 15
        conn.execute("""INSERT INTO orders(origin,destination,cargo,weight,reward,accept_until_day,delivery_days,status,created_day)
                     VALUES(?,?,?,?,?,?,?,?,?)""", (origin, dest, cargo, weight, reward + bonus, day + acceptance, delivery, "available", day))


def get_or_404(conn, table, object_id):
    row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (object_id,)).fetchone()
    if not row: raise HTTPException(404, f"{table[:-1]} not found")
    return row


class QuoteRequest(BaseModel):
    player_id: int = Field(gt=0)

class AcceptRequest(QuoteRequest):
    carrier: Literal["caravan", "airship", "portal"]

class ShipmentAction(BaseModel):
    player_id: int = Field(gt=0)


@app.on_event("startup")
def startup(): init_db()

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/game")
def get_game():
    with db() as conn:
        game = conn.execute("SELECT * FROM game WHERE id=1").fetchone()
        return {"day": game["day"], "weather": game["weather"], "profit_goal_coins": 1000}

@app.get("/game/events")
def game_events(limit: int = Query(30, ge=1, le=100)):
    with db() as conn:
        return [row_dict(x) for x in conn.execute("SELECT * FROM game_events ORDER BY id DESC LIMIT ?", (limit,))]

@app.post("/game/advance-day")
def advance_day():
    with db() as conn:
        new_day = game_day(conn) + 1
        conn.execute("UPDATE game SET day=? WHERE id=1", (new_day,))
        weather = weather_for(new_day)
        conn.execute("UPDATE game SET weather=? WHERE id=1", (weather,))
        if weather == "storm":
            add_game_event(conn, new_day, "weather", "Большой шторм", "воздушные перевозки задерживаются на 1 день")
            conn.execute("UPDATE shipments SET arrival_day=arrival_day+1 WHERE status='in_transit' AND carrier='airship'")
        elif weather == "fog":
            add_game_event(conn, new_day, "weather", "Туман", "все награды за срочные заказы уменьшены на 5%")
        for borrower in conn.execute("SELECT id, loan_principal, loan_rate FROM players WHERE loan_principal > 0").fetchall():
            interest = (borrower["loan_principal"] * borrower["loan_rate"] + 99) // 100
            conn.execute("UPDATE players SET balance=balance-?, loan_principal=loan_principal+? WHERE id=?", (interest, interest, borrower["id"]))
            conn.execute("INSERT INTO wallet_operations(player_id,amount,reason,game_day) VALUES(?,?,?,?)", (borrower["id"], -interest, "daily_loan_interest", new_day))
        conn.execute("UPDATE orders SET status='expired' WHERE status='available' AND accept_until_day < ?", (new_day,))
        arrivals = conn.execute("SELECT * FROM shipments WHERE status='in_transit' AND arrival_day <= ?", (new_day,)).fetchall()
        delivered = []
        for shipment in arrivals:
            payout = shipment["reward"] if shipment["arrival_day"] <= shipment["due_day"] else shipment["reward"] // 2
            player = conn.execute("SELECT reputation FROM players WHERE id=?", (shipment["player_id"],)).fetchone()
            fee = tax_for(payout, player["reputation"])
            payout_after_tax = payout - fee
            conn.execute("UPDATE shipments SET status='delivered', delivered_day=? WHERE id=?", (new_day, shipment["id"]))
            conn.execute("UPDATE orders SET status='completed' WHERE id=?", (shipment["order_id"],))
            conn.execute("UPDATE players SET balance=balance+? WHERE id=?", (payout_after_tax, shipment["player_id"]))
            conn.execute("INSERT INTO wallet_operations(player_id,amount,reason,shipment_id,game_day) VALUES(?,?,?,?,?)", (shipment["player_id"], payout_after_tax, "delivery_reward", shipment["id"], new_day))
            conn.execute("INSERT INTO taxes(player_id,amount,reason,game_day) VALUES(?,?,?,?)", (shipment["player_id"], fee, "delivery_tax", new_day))
            conn.execute("UPDATE players SET profit=profit+? WHERE id=?", (payout_after_tax - shipment["price"], shipment["player_id"]))
            reputation_delta = 5 if payout == shipment["reward"] else -3
            conn.execute("UPDATE players SET reputation=reputation+? WHERE id=?", (reputation_delta, shipment["player_id"]))
            add_event(conn, shipment["id"], shipment["player_id"], "delivered", f"payout={payout}", new_day)
            delivered.append({"shipment_id": shipment["id"], "payout_coins": payout_after_tax, "tax_coins": fee})
        generation = conn.execute("SELECT generation FROM game WHERE id=1").fetchone()["generation"] + 1
        conn.execute("UPDATE game SET generation=? WHERE id=1", (generation,))
        generate_orders(conn, new_day, generation)
        return {"day": new_day, "weather": weather, "delivered": delivered, "new_orders": 3}

@app.get("/players")
def players():
    with db() as conn: return [row_dict(x) for x in conn.execute("SELECT * FROM players ORDER BY id")]

class NewPlayer(BaseModel):
    name: str = Field(min_length=2, max_length=80)

class LoanRequest(BaseModel):
    amount: int = Field(gt=0, le=5000)

class UpgradeRequest(BaseModel):
    upgrade: Literal["warehouse", "negotiator", "insurance"]

@app.post("/players", status_code=201)
def create_player(body: NewPlayer):
    with db() as conn:
        cur = conn.execute("INSERT INTO players(name,balance,reputation) VALUES(?,?,?)", (body.name, 500, 0))
        return row_dict(conn.execute("SELECT * FROM players WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/players/{player_id}")
def player(player_id: int):
    with db() as conn: return row_dict(get_or_404(conn, "players", player_id))

@app.get("/players/{player_id}/stats")
def player_stats(player_id: int):
    with db() as conn:
        p = get_or_404(conn, "players", player_id)
        active = conn.execute("SELECT COUNT(*) c FROM shipments WHERE player_id=? AND status IN ('ready','in_transit')", (player_id,)).fetchone()["c"]
        upgrade = conn.execute("SELECT COALESCE(MAX(level),0) level FROM player_upgrades WHERE player_id=? AND upgrade='warehouse'", (player_id,)).fetchone()["level"]
        return {"player_id": player_id, "balance_coins": p["balance"], "net_profit_coins": p["profit"], "reputation": p["reputation"], "loan_principal": p["loan_principal"], "profit_goal_coins": 1000, "goal_reached": p["profit"] >= 1000, "active_orders": active, "active_order_limit": 3 + upgrade}

@app.get("/players/{player_id}/events")
def player_events(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM shipment_events WHERE player_id=? ORDER BY id", (player_id,))]

@app.get("/players/{player_id}/upgrades")
def player_upgrades(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM player_upgrades WHERE player_id=?", (player_id,))]

@app.post("/players/{player_id}/loan")
def take_loan(player_id: int, body: LoanRequest):
    with db() as conn:
        p = get_or_404(conn, "players", player_id)
        if p["loan_principal"] + body.amount > 5000: raise HTTPException(409, "credit limit reached")
        conn.execute("UPDATE players SET balance=balance+?, loan_principal=loan_principal+? WHERE id=?", (body.amount, body.amount, player_id))
        conn.execute("INSERT INTO wallet_operations(player_id,amount,reason,game_day) VALUES(?,?,?,?)", (player_id, body.amount, "loan_received", game_day(conn)))
        return row_dict(conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone())

@app.post("/players/{player_id}/loan/repay")
def repay_loan(player_id: int, body: LoanRequest):
    with db() as conn:
        p = get_or_404(conn, "players", player_id)
        amount = min(body.amount, p["loan_principal"])
        if amount > p["balance"]: raise HTTPException(409, "insufficient balance")
        conn.execute("UPDATE players SET balance=balance-?, loan_principal=loan_principal-? WHERE id=?", (amount, amount, player_id))
        conn.execute("INSERT INTO wallet_operations(player_id,amount,reason,game_day) VALUES(?,?,?,?)", (player_id, -amount, "loan_repayment", game_day(conn)))
        return row_dict(conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone())

@app.post("/players/{player_id}/upgrades", status_code=201)
def buy_upgrade(player_id: int, body: UpgradeRequest):
    prices = {"warehouse": 250, "negotiator": 200, "insurance": 300}
    with db() as conn:
        p = get_or_404(conn, "players", player_id)
        if p["balance"] < prices[body.upgrade]: raise HTTPException(409, "insufficient balance")
        conn.execute("UPDATE players SET balance=balance-? WHERE id=?", (prices[body.upgrade], player_id))
        conn.execute("INSERT INTO player_upgrades(player_id,upgrade,level) VALUES(?,?,1) ON CONFLICT(player_id,upgrade) DO UPDATE SET level=level+1", (player_id, body.upgrade))
        return row_dict(conn.execute("SELECT * FROM player_upgrades WHERE player_id=? AND upgrade=?", (player_id, body.upgrade)).fetchone())

@app.get("/players/{player_id}/shipments")
def player_shipments(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM shipments WHERE player_id=? ORDER BY id", (player_id,))]

@app.get("/players/{player_id}/wallet-operations")
def wallet_operations(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM wallet_operations WHERE player_id=? ORDER BY id", (player_id,))]

@app.get("/orders")
def orders(origin: str | None = None, destination: str | None = None, cargo: str | None = None, min_reward: int | None = Query(None, ge=0), status: str | None = None, sort_by: Literal["reward", "delivery_days"] = "reward", limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    if origin and origin not in CITIES or destination and destination not in CITIES or cargo and cargo not in GOODS: raise HTTPException(422, "unknown city or cargo")
    with db() as conn:
        filters, values = [], []
        for field, value in (("origin", origin), ("destination", destination), ("cargo", cargo), ("status", status)):
            if value is not None: filters.append(f"{field}=?"); values.append(value)
        if min_reward is not None: filters.append("reward>=?"); values.append(min_reward)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        rows = conn.execute(f"SELECT * FROM orders{where} ORDER BY {sort_by} ASC, id ASC LIMIT ? OFFSET ?", (*values, limit, offset)).fetchall()
        return [row_dict(x) for x in rows]

@app.get("/orders/{order_id}")
def order(order_id: int):
    with db() as conn: return row_dict(get_or_404(conn, "orders", order_id))

@app.post("/orders/{order_id}/quotes")
def quotes(order_id: int, body: QuoteRequest):
    with db() as conn:
        get_or_404(conn, "players", body.player_id)
        order = get_or_404(conn, "orders", order_id)
        if order["status"] != "available": raise HTTPException(409, "order is not available")
        today = conn.execute("SELECT day FROM game WHERE id=1").fetchone()[0]
        distance = DISTANCES[frozenset((order["origin"], order["destination"]))]
        available = []
        unavailable = []
        for carrier in ["caravan", "airship", "portal"]:
            reason = None
            if carrier == "caravan":
                if order["weight"] > 100:
                    reason = "maximum weight is 100 kg"
                price = 10 + 2 * order["weight"] + distance // 10
                days = 3
            elif carrier == "airship":
                if order["weight"] > 20:
                    reason = "maximum weight is 20 kg"
                elif order["cargo"] not in ["food", "artifacts"]:
                    reason = f"does not carry {order['cargo']}"
                price = 40 + 3 * order["weight"] + distance // 5
                days = 2
            else:
                if order["weight"] > 50:
                    reason = "maximum weight is 50 kg"
                elif order["cargo"] != "artifacts":
                    reason = f"does not carry {order['cargo']}"
                elif sorted([order["origin"], order["destination"]]) != ["ice", "stone"]:
                    reason = "does not operate on this route"
                price = 100 + 5 * order["weight"]
                days = 1
            if reason is None:
                available.append({"carrier": carrier, "price_coins": price, "delivery_days": days,
                                  "estimated_arrival_day": today + days, "expected_reward_coins": order["reward"],
                                  "expected_profit_coins": order["reward"] - price,
                                  "will_be_late": today + days > today + order["delivery_days"]})
            else:
                unavailable.append({"carrier": carrier, "reason": reason})
        available = sorted(available, key=lambda x: (-x["expected_profit_coins"], x["delivery_days"], x["carrier"]))
        return {"available": available, "unavailable": unavailable}

@app.post("/orders/{order_id}/accept", status_code=201)
def accept(order_id: int, body: AcceptRequest):
    with db() as conn:
        data = body.model_dump()
        p = conn.execute("SELECT * FROM players WHERE id=?", (data["player_id"],)).fetchone()
        if not p: raise HTTPException(404, "player not found")
        order = get_or_404(conn, "orders", order_id)
        today = game_day(conn)
        if order["status"] != "available" or order["accept_until_day"] < today: raise HTTPException(409, "order is not available for acceptance")
        active = conn.execute("SELECT COUNT(*) c FROM shipments WHERE player_id=? AND status IN ('ready','in_transit')", (body.player_id,)).fetchone()["c"]
        extra_slots = conn.execute("SELECT COALESCE(MAX(level),0) level FROM player_upgrades WHERE player_id=? AND upgrade='warehouse'", (body.player_id,)).fetchone()["level"]
        if active >= 3 + extra_slots: raise HTTPException(409, "active order limit reached")
        reason = None
        distance = DISTANCES[frozenset((order["origin"], order["destination"]))]
        if data["carrier"] == "caravan":
            if order["weight"] > 100: reason = "maximum weight is 100 kg"
            price = 10 + 2 * order["weight"] + distance // 10
            delivery_days = 3
        elif data["carrier"] == "airship":
            if order["weight"] > 20: reason = "maximum weight is 20 kg"
            elif order["cargo"] not in ("food", "artifacts"): reason = f"does not carry {order['cargo']}"
            price = 40 + 3 * order["weight"] + distance // 5
            delivery_days = 2
        else:
            if order["weight"] > 50: reason = "maximum weight is 50 kg"
            elif order["cargo"] != "artifacts": reason = f"does not carry {order['cargo']}"
            elif {order["origin"], order["destination"]} != {"stone", "ice"}: reason = "does not operate on this route"
            price = 100 + 5 * order["weight"]
            delivery_days = 1
        if reason is not None: raise HTTPException(422, reason)
        if p["balance"] < price: raise HTTPException(409, "insufficient balance")
        conn.execute("UPDATE orders SET status='accepted', player_id=? WHERE id=?", (body.player_id, order_id))
        cur = conn.execute("INSERT INTO shipments(order_id,player_id,carrier,price,carrier_days,reward,due_day) VALUES(?,?,?,?,?,?,?)", (order_id, body.player_id, data["carrier"], price, delivery_days, order["reward"], today + order["delivery_days"]))
        conn.execute("UPDATE players SET balance=balance-? WHERE id=?", (price, data["player_id"]))
        conn.execute("INSERT INTO wallet_operations(player_id,amount,reason,shipment_id,game_day) VALUES(?,?,?,?,?)", (body.player_id, -price, "shipment_purchase", cur.lastrowid, today))
        add_event(conn, cur.lastrowid, body.player_id, "accepted", f"carrier={data['carrier']};price={price}", today)
        return dict(conn.execute("SELECT * FROM shipments WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/shipments/{shipment_id}")
def shipment(shipment_id: int):
    with db() as conn: return row_dict(get_or_404(conn, "shipments", shipment_id))

@app.post("/shipments/{shipment_id}/dispatch")
def dispatch(shipment_id: int, body: ShipmentAction):
    return update_shipment(shipment_id, body, "dispatch")

@app.post("/shipments/{shipment_id}/cancel")
def cancel(shipment_id: int, body: ShipmentAction):
    return update_shipment(shipment_id, body.model_dump(), "cancel")


def update_shipment(shipment_id, body, action):
    with db() as conn:
        player_id = body["player_id"] if isinstance(body, dict) else body.player_id
        get_or_404(conn, "players", player_id)
        s = get_or_404(conn, "shipments", shipment_id)
        if s["player_id"] != player_id: raise HTTPException(403, "shipment belongs to another player")
        today = conn.execute("SELECT day FROM game WHERE id=1").fetchone()["day"]
        if action == "dispatch":
            if s["status"] != "ready": raise HTTPException(409, "only ready shipments can be dispatched")
            conn.execute("UPDATE shipments SET status='in_transit', dispatched_day=?, arrival_day=? WHERE id=?", (today, today + s["carrier_days"], shipment_id))
            add_event(conn, shipment_id, player_id, "dispatched", f"arrival_day={today + s['carrier_days']}", today)
        else:
            if s["status"] != "ready": raise HTTPException(409, "only ready shipments can be cancelled")
            conn.execute("UPDATE shipments SET status='cancelled' WHERE id=?", (shipment_id,))
            order = get_or_404(conn, "orders", s["order_id"])
            new_status = "available" if order["accept_until_day"] >= today else "expired"
            conn.execute("UPDATE orders SET status=?, player_id=NULL WHERE id=?", (new_status, order["id"]))
            conn.execute("UPDATE players SET balance=balance+? WHERE id=?", (s["price"], player_id))
            conn.execute("INSERT INTO wallet_operations(player_id,amount,reason,shipment_id,game_day) VALUES(?,?,?,?,?)", (player_id, s["price"], "shipment_refund", shipment_id, today))
            add_event(conn, shipment_id, player_id, "cancelled", "refund issued", today)
        return row_dict(get_or_404(conn, "shipments", shipment_id))

@app.get("/carriers")
def carriers():
    return [
        {"code": "caravan", "unit": "coins", "weight_unit": "kg", "max_weight_kg": 100, "cargoes": ["ore", "food", "artifacts"], "delivery_days": 3, "quote_format": "price_coins"},
        {"code": "airship", "unit": "cents", "weight_unit": "grams", "max_weight_kg": 20, "cargoes": ["food", "artifacts"], "delivery_days": 2, "quote_format": "price_cents"},
        {"code": "portal", "unit": "coins", "weight_unit": "kg", "max_weight_kg": 50, "cargoes": ["artifacts"], "routes": ["stone-ice"], "delivery_days": 1, "quote_format": "price_coins"},
    ]

@app.get("/carriers/health")
def carriers_health():
    with db() as conn:
        return transport.carrier_health(game_day(conn))

@app.get("/orders/{order_id}/rich-quotes")
def rich_quotes(order_id: int, player_id: int = Query(..., gt=0), priority: Literal["normal", "urgent"] = "normal", fragile: bool = False, hazardous: bool = False):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        order = get_or_404(conn, "orders", order_id)
        return transport.calculate_quotes(order, game_day(conn), order["delivery_days"], priority=priority, fragile=fragile, hazardous=hazardous)

@app.get("/shipments/{shipment_id}/risk")
def shipment_risk(shipment_id: int):
    with db() as conn:
        shipment = get_or_404(conn, "shipments", shipment_id)
        order = get_or_404(conn, "orders", shipment["order_id"])
        p = get_or_404(conn, "players", shipment["player_id"])
        risk = finance.risk_score(order["weight"], order["reward"], shipment["price"], shipment["carrier_days"], p["reputation"])
        return {"shipment_id": shipment_id, "risk": risk, "insurance_price": finance.insurance_price(order["reward"], risk)}

@app.get("/carriers/{carrier}/raw-quote")
def raw_carrier_quote(carrier: Literal["caravan", "airship", "portal"], weight_kg: int = Query(..., ge=1, le=100), distance_km: int = Query(..., ge=1)):
    if carrier == "caravan":
        return {"provider": "caravan", "cost_coins": 10 + 2 * weight_kg + distance_km // 10, "eta_days": 3, "weight_kg": weight_kg}
    if carrier == "airship":
        return {"provider": "sky-corp", "cost_cents": (40 + 3 * weight_kg + distance_km // 5) * 100, "eta_hours": 48, "weight_grams": weight_kg * 1000}
    return {"provider": "portal-labs", "amount": 100 + 5 * weight_kg, "duration": "PT24H", "distance_m": distance_km * 1000}


# Ниже начинается экспериментальная зона проекта. Здесь намеренно собрано много
# маленьких ручек, чтобы игру было удобно расширять прямо на собеседовании.
class Bid(BaseModel):
    player_id: int = Field(gt=0)
    bid_coins: int = Field(gt=0, le=10000)

class LicenseRequest(BaseModel):
    player_id: int = Field(gt=0)
    license: Literal["air", "customs", "hazardous"]

class AdminBalance(BaseModel):
    amount: int

class AdminWeather(BaseModel):
    weather: Literal["clear", "wind", "fog", "storm"]

@app.get("/leaderboard")
def leaderboard(limit: int = Query(20, ge=1, le=100)):
    with db() as conn:
        return [row_dict(x) for x in conn.execute("SELECT id, name, profit, reputation FROM players ORDER BY profit DESC, reputation DESC, id LIMIT ?", (limit,))]

@app.get("/players/{player_id}/taxes")
def player_taxes(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM taxes WHERE player_id=? ORDER BY id", (player_id,))]

@app.get("/players/{player_id}/report.csv")
def player_report(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        operations = conn.execute("SELECT id,amount,reason,game_day FROM wallet_operations WHERE player_id=? ORDER BY id", (player_id,)).fetchall()
        lines = finance.csv_report(player_id, [dict(x) for x in operations])
        return Response(lines, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=player-{player_id}.csv"})

@app.get("/players/{player_id}/finance-summary")
def finance_summary(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        operations = [dict(x) for x in conn.execute("SELECT * FROM wallet_operations WHERE player_id=?", (player_id,))]
        p = conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
        return {**finance.wallet_summary(operations), "tax_band": finance.tax_band(p["reputation"]), "repayment_plan": finance.repayment_plan(p["loan_principal"])}

@app.post("/players/{player_id}/licenses", status_code=201)
def buy_license(body: LicenseRequest):
    with db() as conn:
        p = get_or_404(conn, "players", body.player_id)
        prices = {"air": 80, "customs": 120, "hazardous": 250}
        if p["balance"] < prices[body.license]: raise HTTPException(409, "license is too expensive")
        today = game_day(conn)
        conn.execute("UPDATE players SET balance=balance-? WHERE id=?", (prices[body.license], body.player_id))
        conn.execute("INSERT INTO licenses(player_id,license,expires_day) VALUES(?,?,?) ON CONFLICT(player_id,license) DO UPDATE SET expires_day=excluded.expires_day", (body.player_id, body.license, today + 30))
        return row_dict(conn.execute("SELECT * FROM licenses WHERE player_id=? AND license=?", (body.player_id, body.license)).fetchone())

@app.get("/players/{player_id}/licenses")
def player_licenses(player_id: int):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM licenses WHERE player_id=?", (player_id,))]

@app.post("/orders/{order_id}/auction", status_code=201)
def place_bid(order_id: int, body: Bid):
    with db() as conn:
        order = get_or_404(conn, "orders", order_id)
        get_or_404(conn, "players", body.player_id)
        if order["status"] != "available": raise HTTPException(409, "order is not auctionable")
        current = conn.execute("SELECT MAX(bid_coins) value FROM auctions WHERE order_id=? AND status='open'", (order_id,)).fetchone()["value"] or 0
        if body.bid_coins <= current: raise HTTPException(409, "bid must be higher")
        cur = conn.execute("INSERT INTO auctions(order_id,player_id,bid_coins,created_day) VALUES(?,?,?,?)", (order_id, body.player_id, body.bid_coins, game_day(conn)))
        return row_dict(conn.execute("SELECT * FROM auctions WHERE id=?", (cur.lastrowid,)).fetchone())

@app.get("/orders/{order_id}/auction")
def auction(order_id: int):
    with db() as conn:
        get_or_404(conn, "orders", order_id)
        return [row_dict(x) for x in conn.execute("SELECT * FROM auctions WHERE order_id=? ORDER BY bid_coins DESC", (order_id,))]

@app.post("/orders/{order_id}/auction/close")
def close_auction(order_id: int):
    with db() as conn:
        order = get_or_404(conn, "orders", order_id)
        winner = conn.execute("SELECT * FROM auctions WHERE order_id=? AND status='open' ORDER BY bid_coins DESC, id LIMIT 1", (order_id,)).fetchone()
        if not winner: raise HTTPException(409, "auction has no bids")
        conn.execute("UPDATE auctions SET status='won' WHERE id=?", (winner["id"],))
        conn.execute("UPDATE orders SET reward=reward+?, player_id=? WHERE id=?", (winner["bid_coins"], winner["player_id"], order_id))
        return {"order_id": order_id, "winner": row_dict(winner), "status": "closed"}

@app.post("/webhooks/carriers/{provider}")
def carrier_webhook(provider: str, payload: dict):
    shipment_id = payload.get("shipment_id")
    provider_status = payload.get("status", "unknown")
    with db() as conn:
        if shipment_id:
            get_or_404(conn, "shipments", shipment_id)
        cur = conn.execute("INSERT INTO carrier_webhooks(shipment_id,provider,provider_status,payload,created_day) VALUES(?,?,?,?,?)", (shipment_id, provider, provider_status, json.dumps(payload), game_day(conn)))
        if shipment_id and provider_status == "broken":
            conn.execute("UPDATE shipments SET arrival_day=COALESCE(arrival_day,0)+2 WHERE id=? AND status='in_transit'", (shipment_id,))
            add_event(conn, shipment_id, None, "breakdown", provider, game_day(conn))
        return {"accepted": True, "webhook_id": cur.lastrowid}

@app.post("/admin/players/{player_id}/balance")
def admin_balance(player_id: int, body: AdminBalance):
    with db() as conn:
        get_or_404(conn, "players", player_id)
        conn.execute("UPDATE players SET balance=balance+? WHERE id=?", (body.amount, player_id))
        return row_dict(conn.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone())

@app.post("/admin/weather")
def admin_weather(body: AdminWeather):
    with db() as conn:
        conn.execute("UPDATE game SET weather=? WHERE id=1", (body.weather,))
        add_game_event(conn, game_day(conn), "admin", "Ручная погода", body.weather)
        return {"weather": body.weather}

@app.websocket("/ws/events")
async def events_socket(websocket: WebSocket):
    await websocket.accept()
    try:
        with db() as conn:
            latest = conn.execute("SELECT * FROM game_events ORDER BY id DESC LIMIT 10").fetchall()
        await websocket.send_json({"events": [row_dict(x) for x in latest]})
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({"type": "echo", "message": message})
    except Exception:
        return
