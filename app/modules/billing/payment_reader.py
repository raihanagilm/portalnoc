"""
payment_reader.py - Pembaca data tagihan & riwayat pembayaran live dari Network Bill API v1
untuk kebutuhan modul Admin NOC TeknoGuard (tanpa ketergantungan ke modul portal).
"""
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.network_bill_service import NetworkBillService

_CACHE_TTL_SECONDS = 8

CHANNEL_BANKS: Dict[str, str] = {
    "802": "mandiri",
    "800": "bri",
    "702": "bca",
    "723": "bsi",
    "402": "permata",
    "708": "danamon",
    "825": "cimb",
    "818": "sinarmas",
    "408": "maybank",
}

_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, fetcher) -> Dict[str, Any]:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < _CACHE_TTL_SECONDS:
            return hit[1]

    result = fetcher()
    if result.get("ok") or result.get("status") in (403, 404):
        with _cache_lock:
            _cache[key] = (time.monotonic(), result)
            if len(_cache) > 2000:
                cutoff = time.monotonic() - _CACHE_TTL_SECONDS
                for k, (ts, _) in list(_cache.items()):
                    if ts < cutoff:
                        _cache.pop(k, None)
    return result


class NetworkBillPaymentReader:
    """Reader tagihan, Virtual Account, dan riwayat pembayaran live dari Network Bill."""

    @staticmethod
    def resolve_identity(pelanggan) -> Optional[Tuple[str, str]]:
        """Memetakan pelanggan lokal menjadi pasangan (pop_slug, customer_id) Network Bill."""
        if not pelanggan:
            return None

        pop_slug = (getattr(pelanggan, "kantor", "") or "").strip().lower()
        if pop_slug == "cabang":
            pop_slug = "slawi"

        nb_id = str(getattr(pelanggan, "network_bill_id", "") or "").strip()
        if pop_slug and nb_id and nb_id.isdigit():
            return pop_slug, nb_id

        raw_id = str(getattr(pelanggan, "id_pelanggan", "") or "").strip()
        if pop_slug and raw_id.isdigit():
            return pop_slug, raw_id

        try:
            if pop_slug and hasattr(pelanggan, "_sa_instance_state"):
                from sqlalchemy.orm import object_session
                sess = object_session(pelanggan)
                if sess:
                    from app.modules.billing.sync_worker import BillingSyncWorker
                    matched = BillingSyncWorker.resolve_nb_id(sess, pelanggan, pop_slug)
                    if matched and str(matched).isdigit():
                        return pop_slug, str(matched)
        except Exception:
            pass

        return None

    @classmethod
    def read_invoices(cls, pop: str, cid: str, status: Optional[str] = None, limit: int = 24) -> Dict[str, Any]:
        key = f"inv:{pop}:{cid}:{status or 'all'}:{limit}"
        return _cached(key, lambda: NetworkBillService.fetch_invoices(pop, cid, status=status, limit=limit))

    @classmethod
    def read_payments(cls, pop: str, cid: str, limit: int = 24) -> Dict[str, Any]:
        key = f"pay:{pop}:{cid}:{limit}"
        return _cached(key, lambda: NetworkBillService.fetch_payments(pop, cid, limit=limit))

    @classmethod
    def read_virtual_account(cls, pop: str, cid: str) -> Dict[str, Any]:
        key = f"va:{pop}:{cid}"
        return _cached(key, lambda: NetworkBillService.fetch_virtual_account(pop, cid))

    @classmethod
    def read_customer_profile(cls, pop: str, cid: str) -> Dict[str, Any]:
        key = f"cust_profile:{pop}:{cid}"
        return _cached(key, lambda: NetworkBillService.fetch_customer(pop, cid))

    @staticmethod
    def shape_invoice(raw: Dict[str, Any]) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for it in raw.get("items") or []:
            speed = it.get("package_speed")
            items.append({
                "package_name": it.get("package_name") or "",
                "package_speed": f"{speed} Mbps" if isinstance(speed, (int, float)) else (speed or ""),
                "price": it.get("price"),
                "quantity": it.get("quantity"),
                "subtotal": it.get("subtotal"),
            })

        payment = raw.get("payment") or None
        if payment:
            method = (payment.get("method") or "").lower()
            payment = {
                "date": payment.get("date"),
                "amount": payment.get("amount"),
                "method": method,
                "method_label": {
                    "tunai": "Tunai ke Petugas",
                    "transfer": "Transfer Bank",
                    "gateway": "Virtual Account",
                }.get(method, method.title() or "-"),
            }

        return {
            "id": raw.get("id"),
            "number": raw.get("number") or "",
            "type": raw.get("type") or "",
            "billing_period": raw.get("billing_period") or "",
            "issue_date": raw.get("issue_date"),
            "due_date": raw.get("due_date"),
            "subtotal": raw.get("subtotal"),
            "discount": raw.get("discount"),
            "total": raw.get("total"),
            "status": raw.get("status") or "",
            "overdue": bool(raw.get("overdue")),
            "items": items,
            "payment": payment,
        }

    @staticmethod
    def shape_channel(raw: Dict[str, Any]) -> Dict[str, Any]:
        channel = str(raw.get("channel") or "").strip()
        va = "".join(ch for ch in str(raw.get("va_number") or "") if ch.isdigit())
        return {
            "channel": channel,
            "bank": raw.get("bank") or f"Bank {channel}",
            "bank_key": CHANNEL_BANKS.get(channel, ""),
            "va_number": va,
            "admin_fee": raw.get("admin_fee"),
            "amount_to_pay": raw.get("amount_to_pay"),
        }

    @classmethod
    def build_billing_page(cls, pelanggan) -> Dict[str, Any]:
        ident = cls.resolve_identity(pelanggan)
        billing_mode = NetworkBillService.normalize_billing_mode(getattr(pelanggan, "billing_mode", None)) if pelanggan else None
        if not ident:
            return {
                "ok": True,
                "va_state": "not_linked",
                "billing_mode": billing_mode,
                "message": "Data langganan pelanggan belum tertaut ke sistem tagihan.",
                "unpaid": [], "next_bill": None, "channels": [], "other_unpaid": [],
            }

        pop, cid = ident
        inv_res = cls.read_invoices(pop, cid, status="unpaid", limit=120)
        va_res = cls.read_virtual_account(pop, cid)

        if not inv_res.get("ok") and inv_res.get("status") != 404:
            return {
                "ok": False,
                "va_state": "error",
                "billing_mode": billing_mode,
                "status": inv_res.get("status"),
                "retry_after": inv_res.get("retry_after"),
                "message": inv_res.get("message") or "Gagal membaca tagihan.",
                "unpaid": [], "next_bill": None, "channels": [], "other_unpaid": [],
            }

        raw_invoices = sorted(
            inv_res.get("data") or [],
            key=lambda x: (str(x.get("due_date") or x.get("billing_period") or ""), int(x.get("id") or 0))
        )
        unpaid = [cls.shape_invoice(r) for r in raw_invoices]

        va_state = "payable"
        next_bill: Optional[Dict[str, Any]] = None
        channels: List[Dict[str, Any]] = []
        message = None

        if va_res.get("status") == 404:
            va_state = "inactive"
            message = "Pembayaran lewat Virtual Account belum tersedia di kantor layanan ini."
        elif not va_res.get("ok"):
            va_state = "error"
            message = va_res.get("message") or "Gagal membaca nomor Virtual Account."
        else:
            va_data = va_res.get("data") or {}
            raw_next = va_data.get("next_bill")
            raw_channels = va_data.get("channels") or []
            channels = [cls.shape_channel(c) for c in raw_channels]

            if not raw_channels:
                va_state = "not_issued"
                message = "Nomor Virtual Account pelanggan belum diterbitkan."
            elif not raw_next:
                va_state = "no_bill"
                message = "Belum ada tagihan yang perlu dibayar."
            else:
                nb_id = raw_next.get("invoice_id")
                detail = next((i for i in unpaid if i.get("id") == nb_id), None)
                next_bill = {
                    "invoice_id": nb_id,
                    "number": raw_next.get("number") or (detail or {}).get("number") or "",
                    "total": raw_next.get("total"),
                    "type": (detail or {}).get("type") or "",
                    "billing_period": (detail or {}).get("billing_period") or "",
                    "due_date": (detail or {}).get("due_date"),
                    "overdue": bool((detail or {}).get("overdue")),
                    "items": (detail or {}).get("items") or [],
                }

        other_unpaid = [i for i in unpaid if i.get("id") != next_bill.get("invoice_id")] if next_bill else []
        return {
            "ok": True,
            "va_state": va_state,
            "billing_mode": billing_mode,
            "message": message,
            "unpaid": unpaid,
            "unpaid_count": len(unpaid),
            "unpaid_total": sum(i.get("total") or 0 for i in unpaid),
            "next_bill": next_bill,
            "channels": channels,
            "other_unpaid": other_unpaid,
        }

    @staticmethod
    def shape_payment(raw: Dict[str, Any]) -> Dict[str, Any]:
        method = (raw.get("method") or "").lower()
        method_label = raw.get("method_label") or {
            "tunai": "Tunai",
            "transfer": "Transfer Bank",
            "gateway": "Virtual Account",
        }.get(method, method.title() or "-")

        inv_raw = raw.get("invoice") or {}
        invoice = {
            "id": inv_raw.get("id"),
            "number": inv_raw.get("number") or "",
            "type": inv_raw.get("type") or "langganan",
            "billing_period": inv_raw.get("billing_period") or "",
            "total": inv_raw.get("total"),
        }

        return {
            "id": raw.get("id"),
            "date": raw.get("date"),
            "amount": raw.get("amount"),
            "method": method,
            "method_label": method_label,
            "bank_account": raw.get("bank_account"),
            "credit_used": raw.get("credit_used") or 0,
            "credit_added": raw.get("credit_added") or 0,
            "invoice": invoice,
            "number": invoice["number"],
            "billing_period": invoice["billing_period"],
            "type": invoice["type"],
            "total": invoice["total"] if invoice["total"] is not None else raw.get("amount"),
            "payment": {
                "date": raw.get("date"),
                "amount": raw.get("amount"),
                "method": method,
                "method_label": method_label,
            }
        }

    @classmethod
    def build_history(cls, pelanggan, limit: int = 24) -> Dict[str, Any]:
        ident = cls.resolve_identity(pelanggan)
        if not ident:
            return {"ok": True, "linked": False, "invoices": []}

        pop, cid = ident
        pay_res = cls.read_payments(pop, cid, limit=limit)
        if pay_res.get("ok"):
            raw_payments = pay_res.get("data") or []
            return {
                "ok": True,
                "linked": True,
                "invoices": [cls.shape_payment(p) for p in raw_payments],
            }

        res = cls.read_invoices(pop, cid, status="paid", limit=limit)
        if not res.get("ok"):
            return {
                "ok": False, "linked": True, "invoices": [],
                "status": res.get("status"),
                "retry_after": res.get("retry_after"),
                "message": res.get("message") or "Gagal membaca riwayat pembayaran.",
            }

        return {
            "ok": True,
            "linked": True,
            "invoices": [cls.shape_invoice(r) for r in (res.get("data") or [])],
        }
