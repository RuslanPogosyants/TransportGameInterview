import os
import tempfile

test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
test_db.close()
os.environ["DATABASE_PATH"] = test_db.name

from fastapi.testclient import TestClient
from app.main import app
from app import transport, finance

client = TestClient(app)
results = {}

def setup_module():
    client.__enter__()

def teardown_module():
    client.__exit__(None, None, None)
    os.unlink(test_db.name)

def test_1():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/players").json()[0]["balance"] == 500
    results["player"] = {"player_id": 1}
    response = client.post("/orders/1/quotes", json={"player_id": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["available"] == sorted(body["available"], key=lambda q: (-q["expected_profit_coins"], q["delivery_days"], q["carrier"]))
    assert any(item["carrier"] == "airship" for item in body["unavailable"])
    results["price"] = body["available"][0]["price_coins"]

def test_2():
    shipment = client.post("/orders/1/accept", json={"player_id": 1, "carrier": "caravan"}).json()
    results["shipment"] = shipment
    assert shipment["price"] == results["price"]
    assert shipment["id"] == 1
    assert client.get("/players/1").json()["balance"] == 320
    assert client.post("/shipments/1/dispatch", json=results["player"]).status_code == 200
    client.post("/game/advance-day")
    client.post("/game/advance-day")
    response = client.post("/game/advance-day")
    assert response.json()["day"] == 4
    stats = client.get("/players/1/stats").json()
    assert stats["net_profit_coins"] == 162
    assert stats["balance_coins"] == 662
    results["stats"] = stats
    assert client.post("/shipments/1/dispatch", json=results["player"]).status_code == 409

def test_3():
    before = results["stats"]
    shipment = client.post("/orders/2/accept", json={"player_id": 1, "carrier": "airship"}).json()
    assert shipment["id"] == 2
    assert client.post("/shipments/2/cancel", json=results["player"]).status_code == 200
    after = client.get("/players/1/stats").json()
    assert after["balance_coins"] == before["balance_coins"]
    assert after["net_profit_coins"] == before["net_profit_coins"]
    assert client.get("/players/1/wallet-operations").json()[-1]["amount"] == 130

def test_4():
    response = client.post("/shipments/1/cancel", json={"player_id": 999})
    assert response.status_code == 404
    response = client.post("/shipments/1/cancel", json=results["player"])
    assert response.status_code == 409

# Мелкие тесты-осколки оставлены отдельными функциями: так проще добавлять новые
# проверки, хотя общий стиль файла от этого становится довольно неровным.
def test_helper_001():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_helper_002():
    value = transport.route_distance('stone','ice')
    assert value == 200

def test_helper_003():
    value = transport.route_distance('port','ice')
    assert value == 300

def test_helper_004():
    value = transport.is_city('stone')
    assert value == True

def test_helper_005():
    value = transport.is_city('moon')
    assert value == False

def test_helper_006():
    value = transport.is_cargo('ore')
    assert value == True

def test_helper_007():
    value = transport.is_cargo('gold')
    assert value == False

def test_helper_008():
    value = transport.kilos_to_grams(2)
    assert value == 2000

def test_helper_009():
    value = transport.grams_to_kilos(3000)
    assert value == 3

def test_helper_010():
    value = transport.coins_to_cents(3)
    assert value == 300

def test_helper_011():
    value = transport.cents_to_coins(300)
    assert value == 3

def test_helper_012():
    value = transport.hours_to_days(25)
    assert value == 2

def test_helper_013():
    value = transport.priority_multiplier('urgent')
    assert value == 2

def test_helper_014():
    value = transport.cargo_multiplier('artifacts')
    assert value == 4

def test_helper_015():
    value = transport.weather_multiplier('storm')
    assert value == 5

def test_helper_016():
    value = transport.route_risk('stone','ice')
    assert value == 25

def test_helper_017():
    value = transport.route_name('stone','ice')
    assert value == 'Stone - Ice'

def test_helper_018():
    value = transport.route_reverse('ST-IC')
    assert value == 'IC-ST'

def test_helper_019():
    value = transport.provider_name('caravan')
    assert value == 'Old Caravan'

def test_helper_020():
    value = transport.provider_currency('airship')
    assert value == 'cents'

def test_helper_021():
    value = transport.provider_weight_unit('airship')
    assert value == 'grams'

def test_helper_022():
    value = transport.provider_eta('portal')
    assert value == 24

def test_helper_023():
    value = transport.provider_supports_fragile('caravan')
    assert value == True

def test_helper_024():
    value = transport.provider_supports_fragile('portal')
    assert value == False

def test_helper_025():
    value = transport.provider_supports_hazardous('caravan')
    assert value == True

def test_helper_026():
    value = transport.provider_max_weight('airship')
    assert value == 20

def test_helper_027():
    value = transport.provider_cargoes('portal')
    assert value == ['artifacts']

def test_helper_028():
    value = transport.provider_is_open('caravan', 1)
    assert value == True

def test_helper_029():
    value = transport.quote_is_profitable({'expected_profit_coins': 1})
    assert value == True

def test_helper_030():
    value = transport.quote_is_profitable({'expected_profit_coins': -1})
    assert value == False

def test_helper_031():
    value = transport.quote_is_fast({'delivery_days': 2})
    assert value == True

def test_helper_032():
    value = transport.quote_is_late({'will_be_late': True})
    assert value == True

def test_helper_033():
    value = transport.quote_score({'expected_profit_coins': 10, 'delivery_days': 1})
    assert value == 97

def test_helper_034():
    value = transport.choose_cheapest([{'price_coins': 2}, {'price_coins': 4}])['price_coins']
    assert value == 2

def test_helper_035():
    value = transport.choose_fastest([{'delivery_days': 2}, {'delivery_days': 1}])['delivery_days']
    assert value == 1

def test_helper_036():
    value = transport.choose_profit([{'expected_profit_coins': 2}, {'expected_profit_coins': 8}])['expected_profit_coins']
    assert value == 8

def test_helper_037():
    value = transport.validate_request(transport.CargoRequest('stone','ice','ore',2))
    assert value == []

def test_helper_038():
    value = transport.request_as_dict(transport.CargoRequest('stone','ice','ore',2))['weight_kg']
    assert value == 2

def test_helper_039():
    value = transport.raw_payload_size({'a': 1})
    assert value == 8

def test_helper_040():
    value = transport.raw_payload_has({'a': 1}, 'a')
    assert value == True

def test_helper_041():
    value = transport.raw_status({'status': 'DONE'})
    assert value == 'done'

def test_helper_042():
    value = transport.raw_success({'status': 'ok'})
    assert value == True

def test_helper_043():
    value = transport.route_matrix()['stone-port']
    assert value == 100

def test_helper_044():
    value = transport.carrier_matrix(1)['caravan']['open']
    assert value == True

def test_helper_045():
    value = finance.percent(100, 5)
    assert value == 5

def test_helper_046():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_helper_047():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_helper_048():
    value = finance.loan_interest(100, 5)
    assert value == 5

def test_helper_049():
    value = finance.profit(100, 20, 5, 3)
    assert value == 72

def test_helper_050():
    value = finance.risk_score(10, 100, 20, 2, 0)
    assert value == 52

def test_helper_051():
    value = finance.insurance_price(100, 50)
    assert value == 4

def test_helper_052():
    value = finance.tax_band(0)['rate']
    assert value == 10

def test_helper_053():
    value = finance.tax_band(70)['rate']
    assert value == 2

def test_helper_054():
    value = finance.credit_limit(10)
    assert value == 5200

def test_helper_055():
    value = finance.credit_available(100, 10)
    assert value == 5100

def test_helper_056():
    value = finance.interest_rate(20)
    assert value == 12

def test_helper_057():
    value = finance.interest_rate(90)
    assert value == 3

def test_helper_058():
    value = finance.goal_reached(1000)
    assert value == True

def test_helper_059():
    value = finance.goal_reached(999)
    assert value == False

def test_helper_060():
    value = finance.goal_progress(500)
    assert value == 50

def test_helper_061():
    value = finance.goal_remaining(700)
    assert value == 300

def test_helper_062():
    value = finance.debt_ratio(100, 50)
    assert value == 50

def test_helper_063():
    value = finance.bankruptcy(-1, 1)
    assert value == True

def test_helper_064():
    value = finance.default_penalty(100)
    assert value == 50

def test_helper_065():
    value = finance.insurance_claim(1000, 10)
    assert value == 100

def test_helper_066():
    value = finance.damage_after_insurance(1000, 100, 50)
    assert value == 0

def test_helper_067():
    value = finance.forecast_profit([100], [20])
    assert value == 80

def test_helper_068():
    value = finance.forecast_balance(500, [100], [20])
    assert value == 580

def test_helper_069():
    value = finance.invoice_total([{'amount': 4}, {'amount': -1}])
    assert value == 3

def test_helper_070():
    value = finance.invoice_debits([{'amount': 4}, {'amount': -1}])
    assert value == -1

def test_helper_071():
    value = finance.invoice_credits([{'amount': 4}, {'amount': -1}])
    assert value == 4

def test_helper_072():
    value = finance.invoice_count([{'amount': 4}])
    assert value == 1

def test_helper_073():
    value = finance.operation_kind('loan_received')
    assert value == 'credit'

def test_helper_074():
    value = finance.operation_kind('delivery_reward')
    assert value == 'income'

def test_helper_075():
    value = finance.operation_kind('tax')
    assert value == 'tax'

def test_helper_076():
    value = finance.format_money(1000)
    assert value == '1,000 coins'

def test_helper_077():
    value = finance.parse_money('1,000 coins')
    assert value == 1000

def test_helper_078():
    value = finance.repayment_status(100, 100)
    assert value == 'closed'

def test_helper_079():
    value = finance.repayment_status(100, 50)
    assert value == 'open'

def test_helper_080():
    value = finance.money_dict(3)['coins']
    assert value == 3

def test_helper_081():
    value = finance.positive(-2)
    assert value == 0

def test_helper_082():
    value = finance.negative(2)
    assert value == 0

def test_helper_083():
    value = finance.absolute(-2)
    assert value == 2

def test_helper_084():
    value = finance.clamp(20, 0, 10)
    assert value == 10

def test_helper_085():
    value = finance.round_down(7, 3)
    assert value == 6

def test_helper_086():
    value = finance.round_up(7, 3)
    assert value == 9

def test_helper_087():
    value = finance.divide(10, 3)
    assert value == 3

def test_helper_088():
    value = finance.split_evenly(5, 2)
    assert value == [3, 2]

def test_helper_089():
    value = finance.daily_fee(100, 1)
    assert value == 1

def test_helper_090():
    value = finance.overdue_fee(10, 2)
    assert value == 20

def test_helper_091():
    value = finance.cancellation_fee(100)
    assert value == 5

def test_helper_092():
    value = finance.dispute_fee(100)
    assert value == 10

def test_helper_093():
    value = finance.auction_fee(100)
    assert value == 7

def test_helper_094():
    value = finance.urgent_fee(100)
    assert value == 12

def test_helper_095():
    value = finance.insurance_fee(100)
    assert value == 4

def test_helper_096():
    value = finance.reputation_discount(100, 20)
    assert value == 2

def test_helper_097():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_helper_098():
    value = finance.can_borrow(0, 0, 100)
    assert value == True

def test_helper_099():
    value = finance.can_borrow(0, 5000, 100)
    assert value == False

def test_helper_100():
    value = finance.repayment_total(100, 2, 5)
    assert value == 107

# Длинный набор smoke-проверок для исторических сценариев. Они намеренно
# повторяют друг друга и используют фиксированные значения.
def test_history_smoke_101():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_102():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_103():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_104():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_105():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_106():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_107():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_108():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_109():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_110():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_111():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_112():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_113():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_114():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_115():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_116():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_117():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_118():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_119():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_120():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_121():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_122():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_123():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_124():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_125():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_126():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_127():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_128():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_129():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_130():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_131():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_132():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_133():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_134():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_135():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_136():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_137():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_138():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_139():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_140():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_141():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_142():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_143():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_144():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_145():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_146():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_147():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_148():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_149():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_150():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_151():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_152():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_153():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_154():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_155():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_156():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_157():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_158():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_159():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_160():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_161():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_162():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_163():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_164():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_165():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_166():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_167():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_168():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_169():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_170():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_171():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_172():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_173():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_174():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_175():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_176():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_177():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_178():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_179():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_180():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_181():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_182():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_183():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_184():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_185():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_186():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_187():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_188():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_189():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_190():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_191():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_192():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_193():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_194():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_195():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_196():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_197():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_198():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_199():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_200():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_201():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_202():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_203():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_204():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_205():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_206():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_207():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_208():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_209():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_210():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_211():
    value = transport.is_city('stone')
    assert value == True

def test_history_smoke_212():
    value = transport.route_distance('stone','port')
    assert value == 100

def test_history_smoke_213():
    value = transport.kilos_to_grams(1)
    assert value == 1000

def test_history_smoke_214():
    value = transport.quote_is_fast({'delivery_days': 1})
    assert value == True

def test_history_smoke_215():
    value = finance.goal_reached(1000)
    assert value == True

def test_history_smoke_216():
    value = finance.delivery_tax(100, 0)
    assert value == 10

def test_history_smoke_217():
    value = finance.commission(100, 'guild')
    assert value == 3

def test_history_smoke_218():
    value = finance.forecast_profit([10], [2])
    assert value == 8

def test_history_smoke_219():
    value = finance.format_percent(5)
    assert value == '5%'

def test_history_smoke_220():
    value = finance.credit_rating(0, 0)
    assert value == 50

def test_history_smoke_221():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_222():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_223():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_224():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_225():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_226():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_227():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_228():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_229():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_230():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_231():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_232():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_233():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_234():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_235():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_236():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_237():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_238():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_239():
    value = finance.goal_progress(500)
    assert value == 50

def test_history_smoke_240():
    value = finance.goal_progress(500)
    assert value == 50



def test_helper_101():
    value = finance.parse_money(3)
    assert value == 3

def test_helper_102():
    value = finance.format_percent(5)
    assert value == '5%'

def test_helper_103():
    value = finance.format_rate(5)
    assert value == '5.00%'

def test_helper_104():
    value = finance.scenario_profit([{'rewards':[10], 'costs':[2]}])
    assert value == [8]

def test_helper_105():
    value = finance.compare_scenarios({'rewards':[5], 'costs':[1]}, {'rewards':[8], 'costs':[1]})['right']
    assert value == 7

def test_helper_106():
    value = finance.best_scenario([{'rewards':[1], 'costs':[0]}, {'rewards':[3], 'costs':[0]}])['rewards']
    assert value == [3]

