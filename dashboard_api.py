#!/usr/bin/env python3
"""
GjirafaMall Seller Dashboard — Live Data API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI server që i shërben dashboard-it me të dhëna live nga SQL Server.

SETUP (Windows Server):
  1. pip install fastapi uvicorn pyodbc
  2. Ndrysho GJM_CONFIG më poshtë (server, token, origins)
  3. python dashboard_api.py
     (ose si Windows Service me NSSM: nssm install GjmDashApi python dashboard_api.py)

ENDPOINTS:
  GET /api/data          — kthon të gjitha të dhënat (kërkon Bearer token)
  GET /health            — health check (pa auth)

CORS: lejoi origin-in e GitHub Pages tënd, p.sh.:
  ALLOWED_ORIGINS = ["https://yourusername.github.io"]
"""

from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import pyodbc
from datetime import date, datetime, timedelta
import os

# ══════════════════════════════════════════════════════════════════════════════
#  !! KONFIGURO KETU !!
# ══════════════════════════════════════════════════════════════════════════════
GJM_CONFIG = {
    # Token sekret — ndrysho këtë! E njëjta me GJM_API_TOKEN në HTML.
    "token": os.getenv("DASHBOARD_TOKEN", "gjm-dashboard-2026-secret"),

    # Origins të lejuara (GitHub Pages URL juaj)
    # Shembull: ["https://yourusername.github.io", "http://localhost:8080"]
    "allowed_origins": os.getenv("ALLOWED_ORIGINS", "https://kolgj-sellers.github.io,http://localhost:8080,http://localhost:5500").split(","),

    # Connection strings për SQL Server
    # Nëse serveri përdor Windows Auth: Trusted_Connection=yes
    # Nëse përdor SQL Auth: User ID=sa;Password=xxx
    "mall_db": os.getenv("MALL_DB",
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=SQLNODE1\\SQLAG1;"
        "Database=GjirafaMallDb;"
        "Trusted_Connection=yes;"
    ),
    "merchant_db": os.getenv("MERCHANT_DB",
        "Driver={ODBC Driver 17 for SQL Server};"
        "Server=SQLNODE1\\SQLAG1;"
        "Database=GjirafaMerchantDb;"
        "Trusted_Connection=yes;"
    ),

    # Port ku do të dëgjojë API-ja
    "port": int(os.getenv("PORT", "8000")),
}
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="GjirafaMall Dashboard API", version="1.0.0")
security_scheme = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=GJM_CONFIG["allowed_origins"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def verify_token(cred: HTTPAuthorizationCredentials = Security(security_scheme)):
    if cred.credentials != GJM_CONFIG["token"]:
        raise HTTPException(status_code=401, detail="Token i pavlefshëm")

def mall_conn():
    return pyodbc.connect(GJM_CONFIG["mall_db"], timeout=30)

def merchant_conn():
    return pyodbc.connect(GJM_CONFIG["merchant_db"], timeout=30)

def to_dicts(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def flt(v, n=2):
    """Safe float round."""
    try: return round(float(v or 0), n)
    except: return 0

EXCLUDED = ['gjirafamall', 'gjirafa', 'apple', 'nodshop', 'myso', 'mysu']

def excluded(name: str) -> bool:
    nl = (name or '').lower()
    return any(kw in nl for kw in EXCLUDED)

# ── Query functions ───────────────────────────────────────────────────────────

def q_monthly(conn):
    """14 muajt e fundit nga SR_ProductsData."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
          FORMAT(DateAdded,'MMM ''yy') AS m,
          YEAR(DateAdded)*100 + MONTH(DateAdded) AS ym,
          COUNT(DISTINCT OrderId) AS orders,
          ROUND(SUM(NetoPrice*Qty), 0) AS rev
        FROM GjirafaTranslations.dbo.SR_ProductsData
        WHERE
          DateAdded >= DATEADD(MONTH, -13,
            DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1))
          AND NetoPrice * Qty < 10000
          AND OrderId != 1087139
        GROUP BY
          FORMAT(DateAdded,'MMM ''yy'),
          YEAR(DateAdded)*100 + MONTH(DateAdded)
        ORDER BY ym
    """)
    rows = to_dicts(cur)
    return [{"m": r["m"], "orders": r["orders"], "rev": int(r["rev"] or 0)} for r in rows]


def q_order_status(conn):
    """Numri i porosive sipas statusit."""
    cur = conn.cursor()
    cur.execute("SELECT Status, COUNT(*) AS cnt FROM Orders GROUP BY Status")
    rows = to_dicts(cur)
    STATUS_MAP = {
        10: ("Pending",    "#F59E0B"),
        20: ("Processing", "#3B82F6"),
        30: ("Completed",  "#10B981"),
        40: ("Cancelled",  "#EF4444"),
    }
    result = []
    for r in rows:
        if r["Status"] in STATUS_MAP:
            label, color = STATUS_MAP[r["Status"]]
            result.append({"label": label, "cnt": r["cnt"], "color": color})
    order = {"Pending": 0, "Processing": 1, "Completed": 2, "Cancelled": 3}
    result.sort(key=lambda x: order.get(x["label"], 9))
    return result


def q_daily_agg(conn):
    """Agregate ditore për muajin aktual — nga GjirafaMallDb Order+OrderItem+Vendor."""
    cur = conn.cursor()
    first = date.today().replace(day=1).isoformat()
    cur.execute("""
        SELECT
          CAST(o.CreatedOnUtc AS DATE) AS d,
          ROUND(SUM(oi.PriceInclTax), 2) AS rev,
          COUNT(DISTINCT o.Id) AS orders
        FROM [Order] o
        JOIN OrderItem oi ON oi.OrderId = o.Id
        JOIN Product p   ON p.Id = oi.ProductId
        JOIN Vendor v    ON v.Id = p.VendorId
        WHERE
          CAST(o.CreatedOnUtc AS DATE) >= ?
          AND o.Deleted = 0
          AND LOWER(v.Name) NOT LIKE '%gjirafamall%'
          AND LOWER(v.Name) NOT LIKE '%gjirafa%'
        GROUP BY CAST(o.CreatedOnUtc AS DATE)
        ORDER BY d
    """, first)
    rows = to_dicts(cur)
    return [{"d": str(r["d"]), "rev": flt(r["rev"]), "orders": r["orders"]} for r in rows]


def q_daily_sellers(conn):
    """Breakdown per-shitës për 7 ditët e fundit."""
    cur = conn.cursor()
    since = (date.today() - timedelta(days=7)).isoformat()
    cur.execute("""
        SELECT
          CAST(o.CreatedOnUtc AS DATE) AS d,
          p.VendorId AS id,
          v.Name AS n,
          ROUND(SUM(oi.PriceInclTax), 2) AS rev,
          COUNT(DISTINCT o.Id) AS orders
        FROM [Order] o
        JOIN OrderItem oi ON oi.OrderId = o.Id
        JOIN Product p    ON p.Id = oi.ProductId
        JOIN Vendor v     ON v.Id = p.VendorId
        WHERE
          CAST(o.CreatedOnUtc AS DATE) >= ?
          AND o.Deleted = 0
          AND p.VendorId > 0
        GROUP BY CAST(o.CreatedOnUtc AS DATE), p.VendorId, v.Name
        ORDER BY d, rev DESC
    """, since)
    rows = to_dicts(cur)
    grouped = {}
    for r in rows:
        if excluded(r["n"]): continue
        d = str(r["d"])
        grouped.setdefault(d, []).append({
            "id": r["id"], "n": r["n"],
            "rev": flt(r["rev"]), "orders": r["orders"]
        })
    return grouped


def q_recent_orders(conn):
    """60 porositë e fundit nga GjirafaMerchantDb."""
    cur = conn.cursor()
    cur.execute("""
        SELECT TOP 60
          o.Id,
          o.ReferenceId AS num,
          CONVERT(varchar(30), o.CreatedOn, 126) AS ts,
          o.Status AS st,
          s.ReferenceId AS sid,
          s.Name AS sn,
          COUNT(oi.Id) AS items
        FROM Orders o
        JOIN Stores s ON s.Id = o.StoreId
        LEFT JOIN OrderItems oi ON oi.OrderId = o.Id
        WHERE o.CreatedOn >= DATEADD(day, -2, GETDATE())
        GROUP BY o.Id, o.ReferenceId, o.CreatedOn, o.Status, s.ReferenceId, s.Name
        ORDER BY o.CreatedOn DESC
    """)
    rows = to_dicts(cur)
    result = []
    for r in rows:
        ts = (r["ts"] or "").replace("Z", "").replace(" ", "T")
        result.append({
            "id":    r["Id"],
            "num":   r["num"],
            "ts":    ts,
            "st":    r["st"],
            "sid":   r["sid"],
            "sn":    r["sn"],
            "items": r["items"] or 0,
        })
    return result


def q_order_store_data(conn):
    """Porosi sipas dyqanit — breakdown sipas statusit."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
          s.ReferenceId AS id,
          s.Name AS n,
          SUM(CASE WHEN o.Status = 10 THEN 1 ELSE 0 END) AS pend,
          SUM(CASE WHEN o.Status = 20 THEN 1 ELSE 0 END) AS proc,
          SUM(CASE WHEN o.Status = 40 THEN 1 ELSE 0 END) AS canc,
          SUM(CASE WHEN o.Status = 30 THEN 1 ELSE 0 END) AS done,
          COUNT(*) AS tot
        FROM Orders o
        JOIN Stores s ON s.Id = o.StoreId
        WHERE
          s.ReferenceId IS NOT NULL
          AND LOWER(s.Name) NOT LIKE '%gjirafamall%'
          AND LOWER(s.Name) NOT LIKE '%gjirafa%'
          AND LOWER(s.Name) NOT LIKE '%nodshop%'
          AND LOWER(s.Name) NOT LIKE '%apple%'
        GROUP BY s.ReferenceId, s.Name
        HAVING COUNT(*) > 0
        ORDER BY tot DESC
    """)
    rows = to_dicts(cur)
    return [{
        "id": r["id"], "n": r["n"],
        "pend": r["pend"], "proc": r["proc"],
        "canc": r["canc"], "done": r["done"],
        "tot":  r["tot"],
    } for r in rows]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check — pa autentikim."""
    return {"status": "ok", "time": datetime.now().isoformat(), "version": "1.0.0"}


@app.get("/api/data")
def get_data(_: None = Security(verify_token)):
    """
    Kthon të gjitha të dhënat e dashboard-it si JSON.
    Kërkon: Authorization: Bearer <token>
    """
    errors = []
    result = {
        "refreshed": datetime.now().isoformat(),
        "today":     date.today().isoformat(),
        "yesterday": (date.today() - timedelta(days=1)).isoformat(),
    }

    # ── GjirafaMallDb queries ──
    try:
        mc = mall_conn()
        try:
            result["monthly"]      = q_monthly(mc)
            result["dailyAgg"]     = q_daily_agg(mc)
            result["dailySellers"] = q_daily_sellers(mc)
        finally:
            mc.close()
    except Exception as e:
        errors.append(f"MallDb: {e}")

    # ── GjirafaMerchantDb queries ──
    try:
        rc = merchant_conn()
        try:
            result["orderStatus"]   = q_order_status(rc)
            result["recentOrders"]  = q_recent_orders(rc)
            result["orderStoreData"]= q_order_store_data(rc)
        finally:
            rc.close()
    except Exception as e:
        errors.append(f"MerchantDb: {e}")

    if errors:
        result["warnings"] = errors

    return result


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 GjirafaMall Dashboard API nisur në: http://0.0.0.0:{GJM_CONFIG['port']}")
    print(f"📋 Docs: http://localhost:{GJM_CONFIG['port']}/docs")
    uvicorn.run("dashboard_api:app", host="0.0.0.0", port=GJM_CONFIG["port"], reload=False)
