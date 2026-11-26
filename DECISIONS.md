# DECISIONS.md — Architecture Decision Records (ADR)

## ADR-001: Adopsi Single Portal dan Normalisasi Database Tunggal
- **Status:** Diterima & Diimplementasikan
- **Konteks:** Menghilangkan redundansi tabel akun pelanggan dan menyatukan portal pelanggan ke dalam master tabel `pelanggan`.
- **Keputusan:** Menggabungkan kredensial portal langsung ke `pelanggan` dan menggunakan relasi CASCADE untuk tabel anakan.

## ADR-002: Standar Ikon UI SVG Murni & Larangan Emoji
- **Status:** Diterima & Diimplementasikan
- **Konteks:** Menghindari inkonsistensi visual emoji atau icon font eksternal.
- **Keputusan:** Seluruh antarmuka menggunakan inline SVG murni atau Lucide icons tanpa emoji dan tanpa dot kosong.

## ADR-003: Integrasi Harness Engineering WalkingLabs
- **Status:** Diterima & Diimplementasikan
- **Konteks:** Menjamin keandalan agen AI dalam sesi panjang (*cross-session continuity*).
- **Keputusan:** Mengimplementasikan 5 subsistem: Instructions, Tools, Environment, State, dan Feedback.

## ADR-004: Pemisahan Ekosistem Menjadi 3 Repo Mandiri (`portalnoc`, `portalpelanggan`, `portalvendor`)
- **Status:** Diterima & Diimplementasikan (untuk `portalnoc` & `portalpelanggan`; `portalvendor` dalam tahap inisialisasi)
- **Konteks:** Produk ingin dijual terpisah ke berbagai ISP dengan kustomisasi fitur ON/OFF, warna tema, dan logo per klien.
- **Keputusan:**
  - Memisahkan modul Admin NOC ke repo **`portalnoc`** tanpa `app.portal` maupun `frontend/src/portal` (`NetworkBillPaymentReader` diekstrak ke `app/modules/billing/payment_reader.py`).
  - Memisahkan portal pelanggan MyTekno ke repo fullstack mandiri **`portalpelanggan`**.
  - Membangun repo **`portalvendor`** sebagai Vendor Control Plane terpusat.

## ADR-005: Control Plane vs Data Plane & Pembagian Hak Kustomisasi Multi-Tenant
- **Status:** Diterima (Arsitektur Aktif)
- **Konteks:** Setiap ISP memiliki topologi IP lokal, MikroTik, dan merek modem ONT yang berbeda-beda, namun kontrol fitur komersial tidak boleh dimanipulasi oleh klien ISP.
- **Keputusan:**
  - **Data Plane per ISP (`portalnoc` & `portalpelanggan`):** Tetap dijalankan di deployment masing-masing ISP dengan driver adapter modem di `app/services/scraper/driver_registry.py`.
  - **Control Plane (`portalvendor`):** Vendor mengelola tenant, status langganan, feature flags (ON/OFF), dan warna tema melalui *signed policy* kriptografis yang diverifikasi backend Data Plane.
  - **Kustomisasi Admin ISP:** Admin ISP lokal hanya diperbolehkan mengubah **Logo & Nama Brand** lokal mereka.

## ADR-006: Rencana Refaktor Fitur Statik ke Dynamic `FeatureGuard` & Sinkronisasi `ECOSYSTEM_SYNC.md`
- **Status:** Diterima (Masuk Antrean Tahap 2 setelah `portalvendor` siap)
- **Konteks:** Saat ini seluruh 13 modul router di `routes/api.py` dan daftar tab di `frontend/src/components/layout/Navigation.jsx` (`menuSections`) serta branding (`TeknoGuard`, `/tekno-indo-logo.png`, `#0B2545`) masih bersifat statik.
- **Keputusan:**
  - Menjadikan [ECOSYSTEM_SYNC.md](ECOSYSTEM_SYNC.md) sebagai kontrak tersinkron antar 3 repo (`portalvendor` pada port `:9000/:5175`, `portalnoc` pada `:7890/:7891`, `portalpelanggan` pada `:8001/:7891`).
  - Menjadwalkan refaktor `portalnoc` pada Tahap 2 untuk memindahkan kontrol menu/API dari statik menjadi dinamis via `app/core/feature_guard.py` (verifikasi `Ed25519`) + upload logo lokal di modul `settings`, tanpa menyentuh server live `portal.teknoindo.net`.
