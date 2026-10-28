# Hostinger Cloud & Custom Domain Deployment Guide — La Jefatura Suite

This guide organizes **everything needed to deploy La Jefatura Suite 24/7 in the cloud on Hostinger** with your own custom domain (e.g., `ceo.buildingapp.us`, `mando.unitecusadesign.com`, or `app.lajefatura.com`).

---

## 1. What You Need on Hostinger (Server + Domain)

Because **La Jefatura Suite** runs a persistent 24/7 Python server (`scripts/demo_server.py`), a local SQLite database (`data/mc.db`), a 5-minute Hik-Connect Camera Poller (`server/camera_report.py`), Colombian Neural Voice TTS (`edge-tts`), and PDF generation (`reportlab`), here is the exact setup to select in Hostinger:

1. **Hostinger Server Type:**
   - **Hostinger KVM VPS (`KVM 1` or `KVM 2`)** running **Ubuntu 24.04 LTS (64-bit)**.
   - *(Note: Standard shared WordPress/PHP hosting does not run background 24/7 Python daemons; a KVM 1 VPS costs ~$5–$6/mo and gives you a dedicated public IPv4 address, root SSH, and persistent storage).*
2. **Hostinger Domain / Subdomain (DNS `A` Record):**
   - In your Hostinger DNS Zone Editor, add **1 `A` Record** pointing your chosen domain or subdomain to the VPS IPv4 address:
     - **Type:** `A`
     - **Name (Host):** `@` *(for root domain)* or `ceo` *(for `ceo.yourdomain.com`)*
     - **Points to:** `YOUR_HOSTINGER_VPS_IP`
     - **TTL:** `300` (5 minutes)

---

## 2. All Environment Variables & Secrets (Organized in One Place)

When you deploy, all credentials live in a single git-ignored file `/opt/la-jefatura-suite/.env` (plus the optional `/opt/la-jefatura-suite/data/*.secret.json` files).

| Category | Variable Name | Value / Source | Status |
| :--- | :--- | :--- | :--- |
| **1. Core Server & Security** | `PORT` | `8931` | Ready |
| | `MC_DEMO_KEY` | `mc-demo-2026-x9f4` *(or your custom CEO key)* | Ready |
| | `MC_TOKEN` | Shared `X-MC-Token` for UniTEC / BuildingApp / Camera ISAPI webhooks | Ready |
| **2. Hik-Connect Cameras (55 Channels)** | `HIKCONNECT_ACCOUNT` | `Juandgm123@hotmail.com` (`il6usm`) | Ready (Verified Live) |
| | `HIKCONNECT_PASSWORD` | Stored in `data/hikconnect.secret.json` / `.env` | Ready (Verified Live) |
| **3. BuildingApp AI (`buildingapp.us`)** | `BUILDINGAPP_BASE_URL` | `https://buildingapp.us` | Ready (Verified Live) |
| | `BUILDINGAPP_ADMIN_EMAIL` | `admin@buildingapp.us` | Ready (Verified Live) |
| | `BUILDINGAPP_ADMIN_PASSWORD` | Stored in `data/buildingapp_credentials.secret.json` / `.env` | Ready (Verified Live) |
| **4. UniTEC & Building Chatbot** | `UNITEC_BASE_URL` | `https://unitec-front-desk.vercel.app` | Ready (Verified Live) |
| | `UNITEC_CUSTOM_DOMAIN` | `https://www.chatbuildinginnovation.us` | Ready (Verified Live) |
| | `UNITEC_ADMIN_EMAIL` | `admin@unitecdesign.com` | Ready (Verified Live) |
| | `UNITEC_ADMIN_PASSWORD` | Stored in `data/unitec_credentials.secret.json` / `.env` | Ready (Verified Live) |
| | `FIREBASE_SA_PATH` | `/opt/la-jefatura-suite/data/chatbot-bi-front-desk-sa.json` | Ready (Service Account JSON) |
| **5. Official Meta WhatsApp Cloud API** | `META_WA_VERIFY_TOKEN` | `lajefatura_meta_verify_2026` | Ready |
| | `META_WA_PHONE_NUMBER_ID` | Meta App Dashboard (`developers.facebook.com/apps`) -> Use cases -> Customize -> API Setup | Pending Client Meta Setup |
| | `META_WA_WABA_ID` | Meta App Dashboard -> Use cases -> Customize -> API Setup (`WhatsApp Business Account ID`) | Pending Client Meta Setup |
| | `META_WA_ACCESS_TOKEN` | Meta Business Settings (`business.facebook.com/settings/system-users`) -> Permanent System User Token (`whatsapp_business_messaging`, `whatsapp_business_management`) | Pending Client Meta Setup |
| **6. Juan's Gmail & Google Calendar** | `JUAN_GMAIL_ADDRESS` | Juan's Gmail address (`server/google_workspace.py` / `/api/google/config`) | Pending Juan Setup |
| | `JUAN_GMAIL_APP_PASSWORD` | 16-letter Google App Password (`https://myaccount.google.com/apppasswords`) | Pending Juan Setup |
| | `JUAN_GCAL_ICAL_URL` | Google Calendar Secret iCal URL (`https://calendar.google.com/calendar/u/0/r/settings`) | Pending Juan Setup |
| **7. Email & Telegram Delivery** | `BREVO_API_KEY` | From Brevo SMTP & API settings | Optional / Pending |
| | `TG_BOT_TOKEN` | Telegram Bot Token from `@BotFather` | Optional / Pending |

---

## 3. One-Command Deployment on Hostinger VPS

SSH into your Hostinger Ubuntu VPS (`ssh root@YOUR_VPS_IP`) and run:

```bash
git clone https://github.com/Pablodd1/la-jefatura-suite.git /opt/la-jefatura-suite
cd /opt/la-jefatura-suite
bash deploy/install_hostinger_vps.sh ceo.yourdomain.com
```

### What `install_hostinger_vps.sh` Does Automatically:
1. Installs Python 3, `venv`, `ffmpeg`, and **Caddy** (automatic Let's Encrypt SSL/HTTPS).
2. Installs all Python dependencies from `requirements.txt` (`reportlab`, `matplotlib`, `edge-tts`, `google-auth`, `requests`).
3. Creates `/opt/la-jefatura-suite/.env` from `.env.example` with `chmod 600` permissions.
4. Installs and starts the `systemd` daemon `lajefatura.service` so the server and 5-minute camera poller run 24/7 and auto-restart if the VPS ever reboots.
5. Configures Caddy so `https://ceo.yourdomain.com` gets an automatic SSL certificate in ~10 seconds and proxies traffic to `127.0.0.1:8931`.

---

## 4. Alternative: Docker Compose Deployment

If your Hostinger VPS uses the **Docker / Coolify** template, simply run:

```bash
cd /opt/la-jefatura-suite
cp .env.example .env
# Edit .env with your credentials
docker compose up -d --build
```
