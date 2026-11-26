# PRODUCT.md — PortalNOC (TeknoGuard)

## 1. Product Identity & Mission
- **Product Name:** PortalNOC / TeknoGuard (Admin NOC & Network Telemetry Engine).
- **Ecosystem Role:** Standalone Admin NOC Data Plane in the 3-repo ISP SaaS ecosystem (`portalnoc`, `portalpelanggan`, `portalvendor`).
- **Domain:** ISP Operations, Periodic Automated Optical Network Terminal (ONT) Monitoring, Early Warning System (SOP Optical Attenuation Rx Power dBm), Bandwidth Accounting via MikroTik RouterOS API, Customer Billing Monitoring via Network Bill API v1.
- **Core Mission:** Provide local internet service providers and network operators with white-label NOC telemetry and early detection of optical fiber degradation before link disconnection occurs, sellable independently from `portalpelanggan` and centrally governed by `portalvendor`.

## 2. Target Users & Operating Personas
- **NOC Engineers & Network Admins:** Primary users of TeknoGuard desktop dashboard. Needs dense telemetry data, high scannability, instant diagnostic actions, and zero distracting fluff. Can upload/customize the ISP's local **Logo & Brand Name**.
- **Field Technicians:** On-the-go users managing trouble tickets, modem swaps, and field cable splices.
- **Vendor / Platform Owner (via `portalvendor`):** Controls paid feature toggles (ON/OFF), subscription status, and theme colors remotely via signed policy.

## 3. Surface Mode (Impeccable Taxonomy)
- **TeknoGuard Admin NOC (`/`):** **Mode: `Operate`**
  - High information density, high contrast, clean telemetry metrics, zero decorative AI slop.
  - Prioritizes operational status, live scan triggers, billing overview, and optical health tables.
