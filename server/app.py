
from flask import (
    Flask, request, redirect, session,
    url_for, render_template_string,
    send_from_directory, jsonify, abort
)
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta
from collections import Counter
import sqlite3
import secrets
import os
import hmac
import time
import uuid

from werkzeug.utils import secure_filename


# ==========================================
# SHADOW CALENDAR - SHADOW MONARCH ADMIN
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "instance")))
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "shadow_calendar.db"

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
ALLOWED_PDF_EXTENSIONS = {"pdf"}
UPLOAD_DIR = DATA_DIR / "calendar_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def allowed_file(filename, extensions):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in extensions
    )


app = Flask(
    __name__,
    static_folder=str(PUBLIC_DIR),
    static_url_path=""
)

app.secret_key = os.environ.get("SECRET_KEY")

if not app.secret_key:
    if os.environ.get("RENDER"):
        raise RuntimeError("SECRET_KEY manquante.")
    app.secret_key = secrets.token_hex(32)
    print("ATTENTION : clé temporaire locale.")

ADMIN_EMAIL = os.environ.get(
    "ADMIN_EMAIL",
    "seydiismaila182@gmail.com"
).lower()

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_PASSWORD:
    print("ATTENTION : ADMIN_PASSWORD non configuré.")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024
)

# ==========================================
# BASE DE DONNEES
# ==========================================

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS calendars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                price INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)

        # Migration automatique de la table calendars
        existing = {row["name"] for row in db.execute("PRAGMA table_info(calendars)").fetchall()}
        additions = {
            "description": "TEXT DEFAULT ''",
            "image_path": "TEXT DEFAULT ''",
            "pdf_path": "TEXT DEFAULT ''",
            "download_path": "TEXT DEFAULT ''",
            "status": "TEXT DEFAULT 'draft'",
            "updated_at": "TEXT DEFAULT ''",
        }
        for column, definition in additions.items():
            if column not in existing:
                db.execute(f"ALTER TABLE calendars ADD COLUMN {column} {definition}")

        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer TEXT,
                email TEXT,
                total INTEGER DEFAULT 0,
                status TEXT DEFAULT 'En attente',
                created_at TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS visitors (
                visitor_id TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS page_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                path TEXT NOT NULL,
                visited_at TEXT NOT NULL
            )
        """)


init_db()

# ==========================================
# SUIVI AUTOMATIQUE DES VISITEURS
# ==========================================

@app.before_request
def track_visitors():
    if request.method != "GET":
        return

    if request.path.startswith((
        "/admin",
        "/api",
        "/static"
    )):
        return

    if request.path.startswith("/favicon"):
        return

    visitor_id = session.get("visitor_id")

    if not visitor_id:
        visitor_id = secrets.token_hex(16)
        session["visitor_id"] = visitor_id

    now = datetime.utcnow().isoformat(timespec="seconds")

    with get_db() as db:
        db.execute("""
            INSERT INTO visitors (
                visitor_id, first_seen, last_seen
            )
            VALUES (?, ?, ?)
            ON CONFLICT(visitor_id)
            DO UPDATE SET last_seen = excluded.last_seen
        """, (visitor_id, now, now))

        db.execute("""
            INSERT INTO page_views (
                visitor_id, path, visited_at
            )
            VALUES (?, ?, ?)
        """, (visitor_id, request.path, now))


# ==========================================
# PROTECTION ADMIN
# ==========================================

login_attempts = {}


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return function(*args, **kwargs)
    return wrapper


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


def verify_csrf():
    submitted = request.form.get("csrf", "")
    saved = session.get("csrf", "")

    if not saved or not hmac.compare_digest(submitted, saved):
        abort(400)


# ==========================================
# BOUTIQUE PUBLIQUE
# ==========================================

@app.route("/")
def home():
    return send_from_directory(PUBLIC_DIR, "index.html")


@app.route("/api/status")
def status():
    return jsonify({
        "app": "SHADOW CALENDAR",
        "server": "online",
        "analytics": "active"
    })


# ==========================================
# PAGE DE CONNEXION
# ==========================================

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SHADOW ADMIN</title>
<style>
*{box-sizing:border-box}
body{
margin:0;min-height:100vh;
display:flex;align-items:center;justify-content:center;
background:radial-gradient(circle at top,#281044,#08070d 70%);
color:white;font-family:Arial,sans-serif;padding:20px
}
.panel{
width:100%;max-width:390px;padding:35px;
background:#111019;border:1px solid #6330a0;
border-radius:18px;box-shadow:0 0 35px #54228b55
}
h1{text-align:center;color:#c69aff;letter-spacing:3px}
p{text-align:center;color:#aaa}
label{display:block;margin:18px 0 8px}
input{
width:100%;padding:14px;border-radius:9px;
border:1px solid #49315f;background:#08070d;color:white
}
button{
width:100%;padding:14px;margin-top:24px;
border:0;border-radius:9px;background:#762bd1;
color:white;font-weight:bold;font-size:15px
}
.error{color:#ff6464;text-align:center}
</style>
</head>
<body>
<div class="panel">
<h1>SHADOW ADMIN</h1>
<p>Connexion du Shadow Monarch</p>
{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="POST">
<input type="hidden" name="csrf" value="{{ csrf_token() }}">
<label>Adresse administrateur</label>
<input type="email" name="email" required autocomplete="username">
<label>Mot de passe</label>
<input type="password" name="password" required autocomplete="current-password">
<button type="submit">ENTRER DANS LE ROYAUME</button>
</form>
</div>
</body>
</html>
"""


@app.route("/admin", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("dashboard"))

    error = None
    ip = request.remote_addr or "unknown"
    now = time.time()

    attempts = login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < 300]
    login_attempts[ip] = attempts

    if request.method == "POST":
        verify_csrf()

        if len(attempts) >= 5:
            error = "Trop de tentatives. Réessaie dans 5 minutes."
        else:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            valid_email = hmac.compare_digest(email, ADMIN_EMAIL)
            valid_password = (
                ADMIN_PASSWORD is not None
                and hmac.compare_digest(password, ADMIN_PASSWORD)
            )

            if valid_email and valid_password:
                login_attempts.pop(ip, None)
                session.clear()
                session["admin"] = True
                session["admin_email"] = ADMIN_EMAIL
                session["csrf"] = secrets.token_hex(32)
                return redirect(url_for("dashboard"))

            attempts.append(now)
            login_attempts[ip] = attempts
            error = "Identifiants incorrects."

    return render_template_string(LOGIN_PAGE, error=error)


# ==========================================
# TABLEAU DE BORD SHADOW MONARCH
# ==========================================

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SHADOW MONARCH | Dashboard</title>
<style>
*{box-sizing:border-box}
body{
margin:0;background:#09080e;color:#eee;
font-family:Arial,sans-serif
}
header{
padding:20px 24px;background:#12101b;
border-bottom:1px solid #51277b;
display:flex;justify-content:space-between;
align-items:center;gap:12px;flex-wrap:wrap
}
.brand{color:#d3a4ff;font-size:22px;font-weight:bold;letter-spacing:2px}
.subtitle{color:#888;font-size:11px;margin-top:5px}
button{
cursor:pointer;border:0;border-radius:8px;
padding:11px 16px;font-weight:bold
}
.logout{background:#842d48;color:white}
main{max-width:1250px;margin:auto;padding:24px}
h2{color:#d3a4ff}
.welcome{color:#999;margin-bottom:25px}
.cards{
display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
gap:15px
}
.card{
padding:22px;background:linear-gradient(145deg,#191426,#100e17);
border:1px solid #3b2455;border-radius:14px;
min-height:120px
}
.card .label{color:#aaa;font-size:13px}
.card .number{font-size:29px;color:#d5aaff;margin-top:13px;font-weight:bold}
.card .symbol{float:right;font-size:23px;color:#925bc4}
.layout{
display:grid;grid-template-columns:1.5fr 1fr;
gap:16px;margin-top:18px
}
.panel{
background:#15121e;border:1px solid #39234f;
border-radius:14px;padding:20px;min-width:0
}
.panel h3{margin-top:0;color:#d5aaff}
.chart{
display:flex;align-items:center;justify-content:center;
gap:25px;flex-wrap:wrap;min-height:190px
}
.donut{
width:155px;height:155px;border-radius:50%;
background:conic-gradient(
#9c55db 0% {{ paid_percent }}%,
#e34e75 {{ paid_percent }}% {{ done_percent }}%,
#54446a {{ done_percent }}% 100%
);
display:grid;place-items:center
}
.donut:after{
content:"";width:100px;height:100px;
background:#15121e;border-radius:50%;
grid-area:1/1
}
.donut span{
z-index:1;grid-area:1/1;font-size:23px;font-weight:bold
}
.legend{display:grid;gap:12px;color:#bbb;font-size:13px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:8px}
.purple{background:#9c55db}
.pink{background:#e34e75}
.gray{background:#54446a}
.bars{
height:175px;display:flex;align-items:end;
gap:9px;border-bottom:1px solid #49345d;padding:12px 0
}
.bar-wrap{flex:1;height:100%;display:flex;flex-direction:column;justify-content:end;align-items:center;gap:7px}
.bar{
width:70%;min-height:3px;border-radius:5px 5px 0 0;
background:linear-gradient(#c17aff,#7132b2)
}
.day{font-size:10px;color:#999}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:12px 7px;border-bottom:1px solid #30253d;text-align:left}
th{color:#bc91e4}
td{color:#bbb}
.empty{color:#888;text-align:center;padding:22px}
.footer{color:#666;text-align:center;font-size:11px;margin:25px}
@media(max-width:720px){
.layout{grid-template-columns:1fr}
main{padding:15px}
header{padding:16px}
}
</style>
</head>
<body>
<header>
<div>
<div class="brand">♛ SHADOW MONARCH</div>
<div class="subtitle">CENTRE DE CONTRÔLE · SHADOW CALENDAR</div>
</div>
<form method="POST" action="/admin/logout">
<input type="hidden" name="csrf" value="{{ csrf_token() }}">
<button class="logout">Déconnexion</button>
</form>
</header>

<main>
<h2>Bienvenue, Shadow.</h2>
<p class="welcome">Vue générale de ton royaume · {{ today }}</p>

<div class="cards">
<div class="card">
<span class="symbol">◉</span>
<div class="label">Visites totales</div>
<div class="number">{{ visits }}</div>
</div>
<div class="card">
<span class="symbol">♙</span>
<div class="label">Visiteurs uniques</div>
<div class="number">{{ unique_visitors }}</div>
</div>
<div class="card">
<span class="symbol">▣</span>
<div class="label">Commandes</div>
<div class="number">{{ orders }}</div>
</div>
<div class="card">
<span class="symbol">♧</span>
<div class="label">Calendriers</div>
<div class="number">{{ calendars }}</div>
</div>
<div class="card">
<span class="symbol">◆</span>
<div class="label">Revenus enregistrés</div>
<div class="number">{{ revenue }} FG</div>
</div>
<div class="card">
<span class="symbol">↗</span>
<div class="label">Visites aujourd'hui</div>
<div class="number">{{ today_visits }}</div>
</div>
</div>

<div style="margin:20px 0;display:flex;gap:12px;flex-wrap:wrap">
<a href="/admin/calendars" style="display:inline-block;padding:14px 20px;background:linear-gradient(135deg,#792bc2,#39165e);color:white;text-decoration:none;border:1px solid #a76be0;border-radius:10px;font-weight:bold;box-shadow:0 0 15px #712ba633">
📅 GÉRER LES CALENDRIERS
</a>
</div>

<div class="layout">
<section class="panel">
<h3>Activité des visiteurs · 7 jours</h3>
<div class="bars">
{% for day in chart %}
<div class="bar-wrap">
<div class="bar" style="height:{{ day.height }}%"></div>
<div class="day">{{ day.label }}</div>
</div>
{% endfor %}
</div>
<p style="color:#888;font-size:11px">Nombre de pages consultées par jour.</p>
</section>

<section class="panel">
<h3>Répartition des commandes</h3>
<div class="chart">
<div class="donut"><span>{{ orders }}</span></div>
<div class="legend">
<div><span class="dot purple"></span>Payées : {{ paid }}</div>
<div><span class="dot pink"></span>En attente : {{ pending }}</div>
<div><span class="dot gray"></span>Autres : {{ other }}</div>
</div>
</div>
</section>
</div>

<section class="panel" style="margin-top:18px">
<h3>Commandes récentes</h3>
<table>
<thead><tr><th>Client</th><th>Montant</th><th>Statut</th><th>Date</th></tr></thead>
<tbody>
{% for order in recent_orders %}
<tr>
<td>{{ order.customer or "Client" }}</td>
<td>{{ order.total }} FG</td>
<td>{{ order.status }}</td>
<td>{{ order.created_at or "Date inconnue" }}</td>
</tr>
{% else %}
<tr><td colspan="4" class="empty">Aucune commande enregistrée.</td></tr>
{% endfor %}
</tbody>
</table>
</section>

<section class="panel" style="margin-top:18px">
<h3>Pages les plus consultées</h3>
<table>
<thead><tr><th>Page</th><th>Visites</th></tr></thead>
<tbody>
{% for page in popular_pages %}
<tr><td>{{ page.path }}</td><td>{{ page.total }}</td></tr>
{% else %}
<tr><td colspan="2" class="empty">Pas encore de données.</td></tr>
{% endfor %}
</tbody>
</table>
</section>

<div class="footer">
SHADOW CALENDAR · SHADOW MONARCH SYSTEM · ADMINISTRATION PRIVÉE
</div>
</main>
</body>
</html>
"""


@app.route("/admin/dashboard")
@admin_required
def dashboard():
    today = datetime.utcnow().date()
    start = datetime.combine(
        today - timedelta(days=6),
        datetime.min.time()
    ).isoformat()

    today_start = datetime.combine(
        today,
        datetime.min.time()
    ).isoformat()

    with get_db() as db:
        visits = db.execute(
            "SELECT COUNT(*) FROM page_views"
        ).fetchone()[0]

        unique_visitors = db.execute(
            "SELECT COUNT(*) FROM visitors"
        ).fetchone()[0]

        today_visits = db.execute(
            "SELECT COUNT(*) FROM page_views WHERE visited_at >= ?",
            (today_start,)
        ).fetchone()[0]

        calendars = db.execute(
            "SELECT COUNT(*) FROM calendars"
        ).fetchone()[0]

        orders = db.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]

        revenue = db.execute("""
            SELECT COALESCE(SUM(total), 0)
            FROM orders
            WHERE LOWER(status) IN ('payé','payee','paid','payée')
        """).fetchone()[0]

        paid = db.execute("""
            SELECT COUNT(*) FROM orders
            WHERE LOWER(status) IN ('payé','payee','paid','payée')
        """).fetchone()[0]

        pending = db.execute("""
            SELECT COUNT(*) FROM orders
            WHERE LOWER(status) IN ('en attente','pending')
        """).fetchone()[0]

        recent_orders = db.execute("""
            SELECT customer,total,status,created_at
            FROM orders
            ORDER BY id DESC LIMIT 8
        """).fetchall()

        popular_pages = db.execute("""
            SELECT path,COUNT(*) AS total
            FROM page_views
            GROUP BY path
            ORDER BY total DESC LIMIT 6
        """).fetchall()

        raw_days = db.execute("""
            SELECT substr(visited_at,1,10) AS day,
            COUNT(*) AS total
            FROM page_views
            WHERE visited_at >= ?
            GROUP BY day
        """, (start,)).fetchall()

    day_counts = {row["day"]: row["total"] for row in raw_days}
    max_count = max(day_counts.values(), default=0)

    chart = []
    for i in range(7):
        date = today - timedelta(days=6-i)
        value = day_counts.get(date.isoformat(), 0)
        height = (value / max_count * 100) if max_count else 3
        chart.append({
            "label": date.strftime("%d/%m"),
            "height": round(height),
            "value": value
        })

    other = max(0, orders - paid - pending)
    paid_percent = paid / orders * 100 if orders else 0
    done_percent = (paid + pending) / orders * 100 if orders else 0

    return render_template_string(
        DASHBOARD_PAGE,
        visits=visits,
        unique_visitors=unique_visitors,
        today_visits=today_visits,
        calendars=calendars,
        orders=orders,
        revenue=revenue,
        paid=paid,
        pending=pending,
        other=other,
        paid_percent=round(paid_percent, 2),
        done_percent=round(done_percent, 2),
        chart=chart,
        recent_orders=recent_orders,
        popular_pages=popular_pages,
        today=today.strftime("%d/%m/%Y")
    )


# ==========================================
# DECONNEXION
# ==========================================

@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    verify_csrf()
    session.clear()
    return redirect(url_for("admin_login"))



# ==========================================
# SHADOW CALENDAR MANAGER
# ==========================================

@app.route("/admin/calendars")
@admin_required
def calendar_manager():
    with get_db() as db:
        calendars = db.execute(
            "SELECT * FROM calendars ORDER BY id DESC"
        ).fetchall()

    return render_template_string(
        Path(BASE_DIR / "server/templates/calendar_manager.html").read_text(),
        calendars=calendars
    )


@app.route("/admin/calendars/save", methods=["POST"])
@admin_required
def calendar_save():
    verify_csrf()

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    description = request.form.get("description", "").strip()
    status = request.form.get("status", "draft")

    allowed_categories = {
        "Classique", "Anime", "Gaming",
        "Couple", "Souvenirs", "Fantasy"
    }

    if not name or category not in allowed_categories:
        abort(400)

    try:
        price = int(request.form.get("price", "0"))
    except (TypeError, ValueError):
        abort(400)

    if price < 0:
        abort(400)

    if status not in ("draft", "published"):
        abort(400)

    image = request.files.get("image")
    pdf = request.files.get("pdf")

    saved_files = []

    def save_upload(file, extensions, prefix):
        if not file or not file.filename:
            return ""

        if not allowed_file(file.filename, extensions):
            abort(400)

        original = secure_filename(file.filename)
        ext = original.rsplit(".", 1)[1].lower()
        new_name = f"{prefix}_{uuid.uuid4().hex}.{ext}"

        file.save(UPLOAD_DIR / new_name)
        saved_files.append(new_name)
        return new_name

    try:
        image_name = save_upload(
            image, ALLOWED_IMAGE_EXTENSIONS, "image"
        )
        pdf_name = save_upload(
            pdf, ALLOWED_PDF_EXTENSIONS, "calendar"
        )

        now = datetime.utcnow().isoformat(timespec="seconds")

        with get_db() as db:
            db.execute("""
                INSERT INTO calendars (
                    name, category, price, created_at,
                    description, image_path, pdf_path,
                    download_path, status, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, category, price, now,
                description, image_name, pdf_name,
                pdf_name, status, now
            ))

    except Exception:
        for filename in saved_files:
            try:
                (UPLOAD_DIR / filename).unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return redirect(url_for("calendar_manager"))


@app.route("/admin/calendars/delete", methods=["POST"])
@admin_required
def calendar_delete():
    verify_csrf()

    try:
        calendar_id = int(request.form.get("id", ""))
    except (TypeError, ValueError):
        abort(400)

    with get_db() as db:
        calendar = db.execute(
            "SELECT * FROM calendars WHERE id = ?",
            (calendar_id,)
        ).fetchone()

        if not calendar:
            abort(404)

        db.execute(
            "DELETE FROM calendars WHERE id = ?",
            (calendar_id,)
        )

    for field in ("image_path", "pdf_path", "download_path"):
        filename = calendar[field]
        if filename:
            try:
                (UPLOAD_DIR / Path(filename).name).unlink(missing_ok=True)
            except OSError:
                pass

    return redirect(url_for("calendar_manager"))


@app.route("/admin/calendar-images/<filename>")
@admin_required
def calendar_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/admin/calendar-files/<filename>")
@admin_required
def calendar_file(filename):
    return send_from_directory(
        UPLOAD_DIR, filename, as_attachment=False
    )




# ==========================================
# API PUBLIC - CALENDRIERS PUBLIES
# ==========================================

@app.route("/api/calendars")
def public_calendars():
    with get_db() as db:
        rows = db.execute("""
            SELECT id, name, category, price, description, image_path
            FROM calendars
            WHERE status = 'published'
            ORDER BY id DESC
        """).fetchall()

    return jsonify([
        {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"] or "",
            "price": row["price"] or 0,
            "description": row["description"] or "",
            "image": (
                url_for("public_calendar_cover", filename=row["image_path"])
                if row["image_path"] else ""
            )
        }
        for row in rows
    ])


@app.route("/calendar-cover/<filename>")
def public_calendar_cover(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ==========================================
# DEMARRAGE
# ==========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )

