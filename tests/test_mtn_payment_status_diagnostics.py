import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from routers import orders

ORDER = {
    "id": "diagnostic-order", "buyer_id": "diagnostic-buyer",
    "seller_id": "diagnostic-seller", "payment_status": "pending",
    "order_status": "placed", "payment_reference": "mtn-ref",
    "payment_external_id": "external-1", "total_amount": "1.00",
    "quantity": 1, "crop": "Beans", "product_id": "product-1",
    "stock_reserved": True, "stock_released": False,
}

def invoke(monkeypatch, provider, transition, changes=None):
    row = {**ORDER, **(changes or {})}
    db = Mock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [row]
    monkeypatch.setattr(orders, "supabase", db)
    monkeypatch.setattr(orders, "get_payment_status", lambda ref: provider)
    monkeypatch.setattr(orders, "verify_collection_payment", lambda order, status: None)
    rpc = Mock(return_value=transition)
    monkeypatch.setattr(orders, "apply_collection_payment_result", rpc)
    monkeypatch.setattr(orders, "get_admin_supabase", Mock(return_value=Mock()))
    monkeypatch.setattr(orders, "notify_buyer", Mock())
    monkeypatch.setattr(orders, "notify_seller", Mock())
    result = asyncio.run(orders.check_payment_status(
        ORDER["id"], SimpleNamespace(id=ORDER["buyer_id"])
    ))
    return result, rpc

def test_new_failed_response_includes_provider_reason(monkeypatch):
    provider = {"status":"FAILED","reason":"COULD_NOT_PERFORM_TRANSACTION",
                "externalId":"external-1","amount":"1.00","currency":"EUR"}
    transition = {"processed":True,"newly_failed":True,"payment_status":"failed",
                  "stock_released":True,"already_released":False}
    result, rpc = invoke(monkeypatch, provider, transition)
    assert result["mtn_status"] == "FAILED"
    assert result["mtn_reason"] == "COULD_NOT_PERFORM_TRANSACTION"
    assert result["stock_released"] is True
    rpc.assert_called_once()

def test_repeated_failed_response_includes_reason(monkeypatch):
    provider = {"status":"FAILED","reason":"PAYER_NOT_FOUND",
                "externalId":"external-1","amount":"1.00","currency":"EUR"}
    transition = {"processed":True,"newly_failed":False,"payment_status":"failed",
                  "stock_released":False,"already_released":True}
    result, rpc = invoke(monkeypatch, provider, transition, {
        "payment_status":"failed","order_status":"cancelled",
        "stock_reserved":False,"stock_released":True})
    assert result["mtn_status"] == "FAILED"
    assert result["mtn_reason"] == "PAYER_NOT_FOUND"
    assert result["already_released"] is True
    rpc.assert_called_once()

def test_pending_response_includes_reason_without_transition(monkeypatch):
    provider = {"status":"PENDING","reason":"ONGOING",
                "externalId":"external-1","amount":"1.00","currency":"EUR"}
    result, rpc = invoke(monkeypatch, provider, None)
    assert result["payment_status"] == "pending"
    assert result["mtn_status"] == "PENDING"
    assert result["mtn_reason"] == "ONGOING"
    assert result["stock_released"] is False
    rpc.assert_not_called()
