"""Смешанная финансовая логика: ledger, кредит, комиссии и отчёты."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

@dataclass
class Money:
    coins: int = 0
    def plus(self, amount): return Money(self.coins + int(amount))
    def minus(self, amount): return Money(self.coins - int(amount))
    def is_enough(self, amount): return self.coins >= int(amount)

def percent(amount, rate):
    return max(0, int(Decimal(amount * rate) / Decimal(100).to_integral_value(rounding=ROUND_DOWN)))

def delivery_tax(reward, reputation=0):
    rate = 10 if reputation < 20 else 5 if reputation < 60 else 2
    return max(1, percent(reward, rate))

def commission(amount, kind="guild"):
    rates = {"guild": 3, "auction": 7, "urgent": 12, "insurance": 4}
    return max(0, percent(amount, rates.get(kind, 3)))

def loan_interest(principal, rate=5):
    return max(1, percent(principal, rate)) if principal else 0

def repayment_plan(principal, days=10, rate=5):
    if principal <= 0: return []
    each = (principal + days - 1) // days
    return [{"day": i + 1, "principal": min(each, principal - each * i), "interest": loan_interest(max(0, principal - each * i), rate)} for i in range(days) if principal - each * i > 0]

def profit(reward, price, tax=0, commission_amount=0, penalty=0):
    return int(reward) - int(price) - int(tax) - int(commission_amount) - int(penalty)

def risk_score(weight, reward, price, days, reputation=0):
    base = 50 + min(30, weight // 5) + (10 if reward < price else 0) + max(0, days - 3) * 5
    return max(0, min(100, base - reputation // 10))

def insurance_price(value, risk):
    return max(1, percent(value, 2 + risk // 25))

def invoice_lines(operations):
    return [f"{x.get('game_day','')},{x.get('amount','')},{x.get('reason','')}" for x in operations]

def csv_report(player, operations):
    rows = ["player_id,operation_id,amount,reason,game_day"]
    for operation in operations:
        rows.append(f"{player},{operation.get('id','')},{operation.get('amount','')},{operation.get('reason','')},{operation.get('game_day','')}")
    return "\n".join(rows)

def wallet_summary(operations):
    total = sum(int(x.get("amount", 0)) for x in operations)
    credits = sum(int(x.get("amount", 0)) for x in operations if int(x.get("amount", 0)) > 0)
    debits = sum(int(x.get("amount", 0)) for x in operations if int(x.get("amount", 0)) < 0)
    return {"net": total, "credits": credits, "debits": debits, "operations": len(operations)}

def tax_band(reputation):
    if reputation >= 60: return {"name": "trusted", "rate": 2}
    if reputation >= 20: return {"name": "registered", "rate": 5}
    return {"name": "newcomer", "rate": 10}

def can_borrow(balance, existing, requested):
    return existing + requested <= 5000 and requested > 0

def settlement(reward, price, reputation, late=False):
    gross = reward // 2 if late else reward
    tax = delivery_tax(gross, reputation)
    fee = commission(gross)
    return {"gross": gross, "tax": tax, "commission": fee, "net": profit(gross, price, tax, fee)}

def gross(reward, late=False): return reward // 2 if late else reward
def net(reward, price, reputation=0, late=False):
    x = settlement(reward, price, reputation, late)
    return x["net"]
def balance_after(balance, *amounts): return balance + sum(int(x) for x in amounts)
def balance_can_pay(balance, amount): return int(balance) >= int(amount)
def positive(amount): return max(0, int(amount))
def negative(amount): return min(0, int(amount))
def absolute(amount): return abs(int(amount))
def clamp(amount, low=0, high=10**9): return min(high, max(low, int(amount)))
def round_down(amount, step=1): return int(amount) // int(step) * int(step)
def round_up(amount, step=1): return (int(amount) + int(step) - 1) // int(step) * int(step)
def divide(amount, parts): return int(amount) // max(1, int(parts))
def split_evenly(amount, parts):
    parts = max(1, int(parts)); base, rest = divmod(int(amount), parts)
    return [base + (1 if i < rest else 0) for i in range(parts)]
def daily_fee(balance, rate=1): return percent(max(balance, 0), rate)
def overdue_fee(amount, days): return int(amount) * max(0, int(days))
def cancellation_fee(amount, level=0): return max(0, int(amount) * (1 + int(level)) // 20)
def dispute_fee(amount): return max(1, int(amount) // 10)
def auction_fee(amount): return commission(amount, "auction")
def urgent_fee(amount): return commission(amount, "urgent")
def insurance_fee(amount): return commission(amount, "insurance")
def reputation_discount(amount, reputation): return percent(amount, min(15, max(0, reputation // 10)))
def credit_limit(reputation): return 5000 + max(0, reputation) * 20
def credit_available(existing, reputation): return max(0, credit_limit(reputation) - int(existing))
def credit_rating(reputation, principal, missed=0):
    score = 50 + int(reputation) - int(principal) // 100 - int(missed) * 10
    return max(0, min(100, score))
def interest_rate(rating): return 12 if rating < 30 else 8 if rating < 60 else 5 if rating < 85 else 3
def interest_for_rating(principal, rating): return loan_interest(principal, interest_rate(rating))
def invoice_total(lines): return sum(int(x.get("amount", 0)) for x in lines)
def invoice_debits(lines): return sum(int(x.get("amount", 0)) for x in lines if int(x.get("amount", 0)) < 0)
def invoice_credits(lines): return sum(int(x.get("amount", 0)) for x in lines if int(x.get("amount", 0)) > 0)
def invoice_count(lines): return len(list(lines))
def operation_kind(reason):
    if "loan" in reason: return "credit"
    if "tax" in reason: return "tax"
    if "reward" in reason: return "income"
    if "refund" in reason: return "refund"
    if "purchase" in reason: return "expense"
    return "other"
def group_operations(lines):
    result = {}
    for line in lines:
        key = operation_kind(line.get("reason", ""))
        result.setdefault(key, []).append(line)
    return result
def summarize_operations(lines):
    groups = group_operations(lines)
    return {key: invoice_total(value) for key, value in groups.items()}
def tax_breakdown(amount, reputation):
    band = tax_band(reputation)
    return {"gross": amount, "rate": band["rate"], "tax": delivery_tax(amount, reputation), "band": band["name"]}
def ledger_entry(player_id, amount, reason, day, shipment_id=None):
    return {"player_id": player_id, "amount": int(amount), "reason": reason, "game_day": day, "shipment_id": shipment_id}
def ledger_sort(lines): return sorted(lines, key=lambda x: (x.get("game_day", 0), x.get("id", 0)))
def ledger_balance(lines, initial=0): return int(initial) + invoice_total(lines)
def ledger_check(lines): return {"ok": ledger_balance(lines) >= 0, "balance": ledger_balance(lines)}
def credit_operation(amount, day): return ledger_entry(None, amount, "loan_received", day)
def debit_operation(amount, reason, day): return ledger_entry(None, -abs(amount), reason, day)
def reward_operation(amount, day, shipment_id): return ledger_entry(None, amount, "delivery_reward", day, shipment_id)
def tax_operation(amount, day): return ledger_entry(None, -abs(amount), "tax", day)
def refund_operation(amount, day, shipment_id): return ledger_entry(None, amount, "shipment_refund", day, shipment_id)
def purchase_operation(amount, day, shipment_id): return ledger_entry(None, -abs(amount), "shipment_purchase", day, shipment_id)
def forecast_profit(rewards, costs, taxes=0): return sum(rewards) - sum(costs) - int(taxes)
def forecast_balance(start, rewards, costs): return int(start) + sum(rewards) - sum(costs)
def goal_reached(profit_value, goal=1000): return int(profit_value) >= int(goal)
def goal_progress(profit_value, goal=1000): return min(100, max(0, int(profit_value) * 100 // max(1, int(goal))))
def goal_remaining(profit_value, goal=1000): return max(0, int(goal) - int(profit_value))
def scenario_profit(scenarios): return [forecast_profit(x.get("rewards", []), x.get("costs", []), x.get("taxes", 0)) for x in scenarios]
def compare_scenarios(left, right): return {"left": forecast_profit(left.get("rewards", []), left.get("costs", [])), "right": forecast_profit(right.get("rewards", []), right.get("costs", []))}
def best_scenario(scenarios): return max(scenarios, key=lambda x: forecast_profit(x.get("rewards", []), x.get("costs", [])), default=None)
def money_dict(amount): return {"coins": int(amount), "positive": int(amount) >= 0, "display": f"{int(amount)} coins"}
def parse_money(value):
    if isinstance(value, int): return value
    return int(str(value).replace("coins", "").replace(",", "").strip())
def format_money(value): return f"{int(value):,} coins"
def format_percent(value): return f"{int(value)}%"
def format_rate(value): return f"{float(value):.2f}%"
def interest_projection(principal, days, rate=5): return [loan_interest(max(0, principal - principal * i // max(1, days)), rate) for i in range(days)]
def repayment_total(principal, days=10, rate=5): return sum(x["principal"] + x["interest"] for x in repayment_plan(principal, days, rate))
def repayment_status(principal, paid): return "closed" if paid >= principal else "open"
def debt_ratio(balance, principal): return 0 if balance <= 0 else int(principal * 100 // balance)
def bankruptcy(balance, principal): return balance < 0 and principal > 0
def default_penalty(principal): return max(50, principal // 10)
def recovery_amount(principal, percentage=10): return max(1, principal * percentage // 100)
def insurance_claim(value, damage_percentage): return max(0, int(value) * int(damage_percentage) // 100)
def damage_after_insurance(value, damage, insured): return max(0, int(damage) - insurance_claim(value, insured))
def audit_finance(lines):
    result = wallet_summary(lines)
    result["groups"] = summarize_operations(lines)
    result["valid"] = result["net"] == result["credits"] + result["debits"]
    return result

