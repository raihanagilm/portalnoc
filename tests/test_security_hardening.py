import unittest
from starlette.testclient import TestClient
from app.main import app


class TestSecurityHardening(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.client.cookies.clear()

    def test_security_headers_present(self):
        """Memastikan seluruh respons menyertakan header keamanan standar HTTP industri"""
        r = self.client.get("/api/auth/check")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(r.headers.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(r.headers.get("x-xss-protection"), "1; mode=block")
        self.assertEqual(r.headers.get("referrer-policy"), "strict-origin-when-cross-origin")

    def test_login_rate_limiting_triggers(self):
        """Memastikan proteksi rate limiting aktif membatasi percobaan login beruntun berlebihan"""
        test_ip = "192.0.2.99"
        client = TestClient(app, raise_server_exceptions=False)
        blocked = False
        for _ in range(15):
            res = client.post(
                "/api/auth/login",
                json={"username": "attacker", "password": "wrongpassword"},
                headers={"X-Forwarded-For": test_ip}
            )
            if res.status_code == 429:
                blocked = True
                self.assertIn("Terlalu banyak percobaan", res.json().get("detail", ""))
                break

        self.assertTrue(blocked, "Rate limiter harus memblokir dengan status HTTP 429 jika melebihi batas percobaan.")

    def test_protected_admin_endpoints_require_authentication(self):
        """Memastikan endpoint admin & monitoring sensitif menolak request anonim dengan HTTP 401"""
        protected_gets = [
            "/api/kantor/list",
            "/api/customers",
            "/api/pelanggan",
            "/api/customers/CUST001",
            "/api/customers/CUST001/billing",
            "/api/monitoring/status",
            "/api/monitoring/kpi",
            "/api/monitoring/chart-data",
            "/api/monitoring/available-dates",
        ]
        for ep in protected_gets:
            r = self.client.get(ep)
            self.assertEqual(r.status_code, 401, f"Endpoint {ep} wajib menolak akses anonim dengan HTTP 401")

    def test_production_rejects_weak_secret_key(self):
        """Memastikan mode production menolak SECRET_KEY bawaan atau terlalu pendek"""
        from app.core.config import Settings
        with self.assertRaises(ValueError):
            Settings(APP_ENV="production", SECRET_KEY="edteknoguard-secret-key")
        with self.assertRaises(ValueError):
            Settings(APP_ENV="production", SECRET_KEY="terlalu-pendek")
        prod = Settings(APP_ENV="production", SECRET_KEY="a" * 48)
        self.assertEqual(len(prod.SECRET_KEY), 48)

    def test_trusted_client_ip_and_https_helpers(self):
        """Memastikan ekstraksi IP klien tahan terhadap spoofing dari non-proxy peer"""
        from unittest.mock import MagicMock
        from app.core.security import get_trusted_client_ip, is_https_request

        req_direct = MagicMock()
        req_direct.client = MagicMock(host="203.0.113.50")
        req_direct.headers = {"x-forwarded-for": "127.0.0.1", "cf-connecting-ip": "192.168.1.1"}
        self.assertEqual(get_trusted_client_ip(req_direct), "203.0.113.50")

        req_proxy = MagicMock()
        req_proxy.client = MagicMock(host="127.0.0.1")
        req_proxy.headers = {"x-forwarded-for": "1.1.1.1, 203.0.113.88", "cf-connecting-ip": "203.0.113.88", "x-forwarded-proto": "https"}
        req_proxy.url = MagicMock(scheme="http")
        self.assertEqual(get_trusted_client_ip(req_proxy), "203.0.113.88")
        self.assertTrue(is_https_request(req_proxy))

    def test_admin_session_token_verification(self):
        """Memastikan verify_session_token hanya menerima token sesi admin NOC yang sah"""
        from app.core.security import create_session_token, verify_session_token

        admin_token = create_session_token("admin", role="super admin")
        verified = verify_session_token(admin_token)
        self.assertIsNotNone(verified)
        self.assertEqual(verified.get("user"), "admin")

        self.assertIsNone(verify_session_token("invalid.token.value"))
        r_admin = self.client.get("/api/customers", headers={"Authorization": "Bearer invalid.token.value"})
        self.assertEqual(r_admin.status_code, 401)

    def test_cross_office_access_denied_for_non_super_admin(self):
        """Memastikan teknisi/admin cabang tidak dapat mengakses log atau notifikasi kantor lain"""
        from app.core.security import create_session_token, get_all_kantor_codes
        all_k = get_all_kantor_codes()
        if len(all_k) < 2:
            self.skipTest("Membutuhkan minimal 2 kantor aktif di database")
        allowed_office = all_k[0]
        forbidden_office = all_k[1]
        tek_token = create_session_token("teknisi_cabang", role="teknisi", allowed_kantor=[allowed_office])

        r_log = self.client.get(
            f"/api/activity-logs/customers?kantor={forbidden_office}",
            headers={"Authorization": f"Bearer {tek_token}"}
        )
        self.assertEqual(r_log.status_code, 403)

        r_notif = self.client.post(
            "/api/notifications/read",
            json={"type": "ticket", "reference_id": "1", "kantor": forbidden_office},
            headers={"Authorization": f"Bearer {tek_token}"}
        )
        self.assertEqual(r_notif.status_code, 403)
