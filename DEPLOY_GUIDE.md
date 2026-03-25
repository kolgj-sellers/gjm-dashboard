# 🚀 GjirafaMall Dashboard — Udhëzues Deployment

## Arkitektura

```
[Browser] → GitHub Pages (HTML) → [API Server juaj] → SQL Server (GjirafaMallDb + MerchantDb)
                    ↕
              Login screen (SHA-256)
              AI Advisor (Claude API)
```

---

## HAPI 1 — Konfiguro & Nis API-n në Serverin Tuaj (Windows)

### 1.1 Instalo Python dependencies
```cmd
pip install fastapi uvicorn pyodbc
```

### 1.2 Ndrysho `dashboard_api.py` — rreshtat e konfigurimit
```python
GJM_CONFIG = {
    "token":   "vendos-tokenin-tuaj-sekret",     # ← ndrysho
    "allowed_origins": ["https://USERNAME.github.io"],  # ← GitHub Pages URL
    "mall_db":     "Driver={ODBC Driver 17 for SQL Server};Server=SERVERI;Database=GjirafaMallDb;Trusted_Connection=yes;",
    "merchant_db": "Driver={ODBC Driver 17 for SQL Server};Server=SERVERI;Database=GjirafaMerchantDb;Trusted_Connection=yes;",
    "port": 8000,
}
```

### 1.3 Testo API-n lokalisht
```cmd
python dashboard_api.py
# Hap: http://localhost:8000/health   → duhet { "status": "ok" }
# Hap: http://localhost:8000/docs     → Swagger UI me të gjitha endpoints
```

### 1.4 Instalo si Windows Service (me NSSM — rekomandohet)
```cmd
# Shkarko NSSM nga: https://nssm.cc/download
nssm install GjmDashboardApi python C:\path\to\dashboard_api.py
nssm set GjmDashboardApi AppDirectory C:\path\to\
nssm start GjmDashboardApi
```

### 1.5 Hap portin 8000 në Firewall
```cmd
netsh advfirewall firewall add rule name="GjmDashAPI" dir=in action=allow protocol=TCP localport=8000
```

> **Rekomandim sigurie:** Nëse serveri ka IP publike, vende HTTPS me Nginx reverse proxy para API-t.

---

## HAPI 2 — Konfiguro HTML-in

Hap `Seller Dashboard v1.6.html` dhe ndrysho **3 rreshta** në krye:

```javascript
const GJM_API_BASE  = 'http://IP_SERVERIT_TUAJ:8000';  // ← IP publike e serverit
const GJM_API_TOKEN = 'vendos-tokenin-tuaj-sekret';     // ← e njëjta me dashboard_api.py
const GJM_PASS_HASH = '034b23a0...';                    // ← SHA-256 e fjalëkalimit (shih poshtë)
```

### Gjenero hash të fjalëkalimit të ri:
```bash
python3 -c "import hashlib; print(hashlib.sha256(b'FJALAKALIMI_JOT').hexdigest())"
```

---

## HAPI 3 — Publiko në GitHub Pages

### 3.1 Krijo repo GitHub
1. Shko te [github.com/new](https://github.com/new)
2. Emri: `gjm-dashboard` (ose çfarëdo)
3. **Private** ✓ (e rëndësishme!)
4. Klikoni **Create repository**

### 3.2 Ngarko skedarin
```bash
git init
git add "Seller Dashboard v1.6.html"
git commit -m "GjirafaMall Dashboard v1.6"
git branch -M main
git remote add origin https://github.com/USERNAME/gjm-dashboard.git
git push -u origin main
```

### 3.3 Aktivizo GitHub Pages
1. Repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / **(root)**
4. Save

Pas ~2 minutave, dashboard-i hapet te:
```
https://USERNAME.github.io/gjm-dashboard/Seller%20Dashboard%20v1.6.html
```

### 3.4 (Opsionale) Emër i shkurtër me redirect
Krijo `index.html` me:
```html
<!DOCTYPE html>
<meta http-equiv="refresh" content="0; url=Seller Dashboard v1.6.html">
```
Atëherë URL bëhet thjesht: `https://USERNAME.github.io/gjm-dashboard/`

---

## HAPI 4 — Refresh automatik i të dhënave

### Opsioni A: Windows Task Scheduler (rekomandohet)
Krijoni një task që çdo ditë në 08:00 ekzekuton skriptin e refresh-it dhe pastaj pushon HTML-in e ri në GitHub:

```cmd
# refresh_and_deploy.bat
cd C:\path\to\dashboard
python update_dashboard.py
git add "Seller Dashboard v1.6.html"
git commit -m "Auto-refresh %date%"
git push
```

### Opsioni B: Manual refresh nga browser
Klikoni butonin **⟳ Live** në header të dashboardit — merr të dhëna live nga API-t direkt.

---

## Fjalëkalime & Siguri

| Gjë | Ku ndryshohet | Default |
|-----|---------------|---------|
| Fjalëkalimi i dashboardit | `GJM_PASS_HASH` në HTML | `gjm2026` |
| Token API | `GJM_API_TOKEN` në HTML + `dashboard_api.py` | `gjm-dashboard-2026-secret` |
| Anthropic API Key (AI) | Input brenda dashboardit | — |

> ⚠️ **NDRYSHOJI të gjitha default passwords para publikimit!**

---

## Troubleshooting

| Problem | Zgjidhja |
|---------|----------|
| CORS error | Shto GitHub Pages URL në `allowed_origins` te `dashboard_api.py` |
| API nuk përgjigjet | Kontro firewall: `netsh advfirewall...` dhe NSSM service status |
| "HTTP 401" | Token nuk përputhet — kontrollo `GJM_API_TOKEN` HTML vs `dashboard_api.py` |
| Të dhëna të vjetra | Kliko ⟳ Live ose presto API-n: `curl http://SERVER:8000/health` |
| Fjalëkalim i harruar | Gjenero hash të ri me Python dhe ndrysho `GJM_PASS_HASH` |
