import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

BASE_DIR = os.path.dirname(__file__)
FRONT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "front"))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "inventory.db")

app = Flask(__name__, static_folder=FRONT_DIR, static_url_path="")


def now_local():
    tz_name = os.getenv("APP_TZ", "America/Panama")
    return datetime.now(ZoneInfo(tz_name))


def pdf_safe(value, default="N/A"):
    if value is None:
        return default
    text = str(value)
    return text.encode("latin-1", "replace").decode("latin-1")


def format_invoice_datetime(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.strftime("%Y-%m-%d %H:%M")
        tz_name = os.getenv("APP_TZ", "America/Panama")
        return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                sku TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                location TEXT NOT NULL,
                price REAL NOT NULL,
                threshold INTEGER NOT NULL,
                description TEXT,
                image_url TEXT,
                status TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sales (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                total REAL NOT NULL,
                payment_method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items (id)
            )
            """
        )

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(items)").fetchall()
        }
        if "description" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN description TEXT")
        if "image_url" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
        if "status" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN status TEXT")
        if "cost_unit" not in columns:
            conn.execute("ALTER TABLE items ADD COLUMN cost_unit REAL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def row_to_item(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "sku": row["sku"],
        "quantity": row["quantity"],
        "location": row["location"],
        "price": row["price"],
        "costUnit": row["cost_unit"] if "cost_unit" in row.keys() else 0,
        "threshold": row["threshold"],
        "description": row["description"],
        "imageUrl": row["image_url"],
        "status": row["status"],
        "updatedAt": row["updated_at"],
    }


def row_to_sale(row):
    return {
        "id": row["id"],
        "itemId": row["item_id"],
        "quantity": row["quantity"],
        "price": row["price"],
        "total": row["total"],
        "paymentMethod": row["payment_method"],
        "createdAt": row["created_at"],
    }


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_item(payload):
    name = str(payload.get("name", "")).strip()
    sku = str(payload.get("sku", "")).strip()
    location = str(payload.get("location", "")).strip()
    description = str(payload.get("description", "")).strip()
    image_url = str(payload.get("imageUrl", "")).strip()
    status = str(payload.get("status", "Nuevo")).strip() or "Nuevo"
    if not name or not sku or not location:
        return None, "Missing name, sku, or location."

    item_id = str(payload.get("id") or uuid.uuid4())
    quantity = to_int(payload.get("quantity"))
    threshold = to_int(payload.get("threshold"))
    price = to_float(payload.get("price"))
    cost_unit = to_float(payload.get("costUnit"))
    updated_at = payload.get("updatedAt") or now_local().isoformat()

    return (
        {
            "id": item_id,
            "name": name,
            "sku": sku,
            "quantity": quantity,
            "location": location,
            "price": price,
            "costUnit": cost_unit,
            "threshold": threshold,
            "description": description,
            "imageUrl": image_url,
            "status": status,
            "updatedAt": updated_at,
        },
        None,
    )


def get_week_range():
    now = now_local()
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start, end


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Limpiar sesiones expiradas
        cleanup_expired_sessions()
        
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Unauthorized"}), 401

        if token.startswith("Bearer "):
            token = token[7:]

        with get_db() as conn:
            session = conn.execute(
                "SELECT user_id FROM sessions WHERE token = ?", (token,)
            ).fetchone()

        if not session:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)

    return decorated


def cleanup_expired_sessions():
    """Limpiar sesiones más antiguas de 7 días"""
    try:
        with get_db() as conn:
            cutoff = (now_local() - timedelta(days=7)).isoformat()
            conn.execute(
                "DELETE FROM sessions WHERE created_at < ?", (cutoff,)
            )
            conn.commit()
    except Exception as e:
        print(f"Error cleaning up sessions: {e}")


@app.route("/")
def index():
    response = send_from_directory(FRONT_DIR, "index.html")
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route("/<path:path>")
def static_files(path):
    file_path = os.path.join(FRONT_DIR, path)
    if os.path.isfile(file_path):
        response = send_from_directory(FRONT_DIR, path)
        # No cache for CSS, JS, HTML files
        if path.endswith(('.css', '.js', '.html')):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    response = send_from_directory(FRONT_DIR, "index.html")
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "2.1"})


@app.route("/api/auth/register", methods=["POST"])
def register():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username and password required."}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return jsonify({"error": "Username already exists."}), 400

        user_id = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        created_at = now_local().isoformat()

        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, password_hash, created_at),
        )

        token = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, created_at),
        )
        conn.commit()

    return jsonify({"token": token, "username": username}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username and password required."}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    token = str(uuid.uuid4())
    created_at = now_local().isoformat()

    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user["id"], created_at),
        )
        conn.commit()

    return jsonify({"token": token, "username": username})


@app.route("/api/auth/logout", methods=["POST"])
@require_auth
def logout():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    return jsonify({"status": "ok"})


@app.route("/api/auth/validate", methods=["GET"])
@require_auth
def validate_session():
    """Endpoint para validar que la sesión actual es válida"""
    return jsonify({"status": "valid"})


@app.route("/api/store/items", methods=["GET"])
def list_store_items():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, sku, quantity, price, description, image_url, status
            FROM items
            WHERE quantity > 0
            ORDER BY name ASC
            """
        ).fetchall()

    return jsonify(
        [
            {
                "id": row["id"],
                "name": row["name"],
                "sku": row["sku"],
                "quantity": row["quantity"],
                "price": row["price"],
                "description": row["description"],
                "imageUrl": row["image_url"],
                "status": row["status"],
            }
            for row in rows
        ]
    )


@app.route("/api/items", methods=["GET"])
@require_auth
def list_items():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM items ORDER BY updated_at DESC"
        ).fetchall()
    return jsonify([row_to_item(row) for row in rows])


@app.route("/api/items", methods=["POST"])
@require_auth
def create_item():
    payload = request.get_json(silent=True) or {}
    item, error = parse_item(payload)
    if error:
        return jsonify({"error": error}), 400

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM items WHERE sku = ? AND id != ?",
            (item["sku"], item["id"]),
        ).fetchone()
        if existing:
            return jsonify({"error": "SKU already exists."}), 400

        conn.execute(
            """
            INSERT OR REPLACE INTO items
            (id, name, sku, quantity, location, price, cost_unit, threshold, description, image_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["sku"],
                item["quantity"],
                item["location"],
                item["price"],
                item["costUnit"],
                item["threshold"],
                item["description"],
                item["imageUrl"],
                item["updatedAt"],
            ),
        )
        conn.commit()
    return jsonify(item), 201


@app.route("/api/items/<item_id>", methods=["PUT"])
@require_auth
def update_item(item_id):
    payload = request.get_json(silent=True) or {}
    payload["id"] = item_id
    item, error = parse_item(payload)
    if error:
        return jsonify({"error": error}), 400

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if not existing:
            return jsonify({"error": "Item not found."}), 404

        sku_duplicate = conn.execute(
            "SELECT id FROM items WHERE sku = ? AND id != ?",
            (item["sku"], item_id),
        ).fetchone()
        if sku_duplicate:
            return jsonify({"error": "SKU already exists."}), 400

        conn.execute(
            """
            UPDATE items
            SET name = ?, sku = ?, quantity = ?, location = ?, price = ?, cost_unit = ?,
                threshold = ?, description = ?, image_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                item["name"],
                item["sku"],
                item["quantity"],
                item["location"],
                item["price"],
                item["costUnit"],
                item["threshold"],
                item["description"],
                item["imageUrl"],
                item["updatedAt"],
                item_id,
            ),
        )
        conn.commit()
    return jsonify(item)


@app.route("/api/items/<item_id>", methods=["DELETE"])
@require_auth
def delete_item(item_id):
    with get_db() as conn:
        conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
    return jsonify({"status": "ok"})


@app.route("/api/items", methods=["DELETE"])
@require_auth
def clear_items():
    with get_db() as conn:
        conn.execute("DELETE FROM items")
    return jsonify({"status": "cleared"})


@app.route("/api/items/bulk", methods=["POST"])
@require_auth
def bulk_items():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    cleaned = []
    for raw in items:
        item, error = parse_item(raw or {})
        if error:
            continue
        cleaned.append(item)

    with get_db() as conn:
        conn.execute("DELETE FROM items")
        conn.executemany(
            """
            INSERT OR REPLACE INTO items
            (id, name, sku, quantity, location, price, cost_unit, threshold, description, image_url, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["id"],
                    item["name"],
                    item["sku"],
                    item["quantity"],
                    item["location"],
                    item["price"],
                    item["costUnit"],
                    item["threshold"],
                    item["description"],
                    item["imageUrl"],
                    item["updatedAt"],
                )
                for item in cleaned
            ],
        )
        conn.commit()
    return jsonify(cleaned)


@app.route("/api/sales", methods=["GET"])
@require_auth
def list_sales():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT s.*, i.cost_unit
            FROM sales s
            LEFT JOIN items i ON s.item_id = i.id
            ORDER BY s.created_at DESC
            """
        ).fetchall()
    
    sales_list = []
    for row in rows:
        sale = row_to_sale(row)
        cost_unit = row["cost_unit"] if row["cost_unit"] else 0
        gain = (row["price"] - cost_unit) * row["quantity"]
        sale["gain"] = round(gain, 2)
        sales_list.append(sale)
    
    return jsonify(sales_list)


@app.route("/api/backup")
@require_auth
def backup():
    """Download database backup."""
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Database not found"}), 404
    return send_file(
        DB_PATH,
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"backup-{now_local().strftime('%Y-%m-%d')}.db"
    )


@app.route("/api/reports/weekly")
@require_auth
def weekly_report():
    start, end = get_week_range()
    start_iso = start.isoformat()
    end_iso = end.isoformat()

    with get_db() as conn:
        summary = conn.execute(
            """
            SELECT
                SUM(total) AS total,
                COUNT(*) AS count,
                SUM(quantity) AS units
            FROM sales
            WHERE created_at >= ? AND created_at < ?
            """,
            (start_iso, end_iso),
        ).fetchone()

        by_payment = conn.execute(
            """
            SELECT
                payment_method,
                SUM(total) AS total,
                COUNT(*) AS count,
                SUM(quantity) AS units
            FROM sales
            WHERE created_at >= ? AND created_at < ?
            GROUP BY payment_method
            ORDER BY total DESC
            """,
            (start_iso, end_iso),
        ).fetchall()

    total = summary["total"] or 0
    count = summary["count"] or 0
    units = summary["units"] or 0

    breakdown = [
        {
            "method": row["payment_method"],
            "total": row["total"] or 0,
            "count": row["count"] or 0,
            "units": row["units"] or 0,
        }
        for row in by_payment
    ]

    return jsonify(
        {
            "start": start_iso,
            "end": end_iso,
            "total": total,
            "count": count,
            "units": units,
            "byPayment": breakdown,
        }
    )


@app.route("/api/sales", methods=["POST"])
@require_auth
def create_sale():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("itemId")
    quantity = int(payload.get("quantity") or 0)
    price = float(payload.get("price") or 0)
    payment_method = str(payload.get("paymentMethod") or "").strip()

    if not item_id or quantity <= 0 or price < 0 or not payment_method:
        return jsonify({"error": "Invalid sale data."}), 400

    total = quantity * price
    sale_id = str(uuid.uuid4())
    created_at = now_local().isoformat()

    with get_db() as conn:
        item = conn.execute(
            "SELECT quantity, cost_unit FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return jsonify({"error": "Item not found."}), 404

        if item["quantity"] < quantity:
            return jsonify({"error": "Not enough stock."}), 400

        # Usar el costo unitario del item
        cost_unit = item["cost_unit"] if item["cost_unit"] else 0
        gain = (price - cost_unit) * quantity

        conn.execute(
            "INSERT INTO sales (id, item_id, quantity, price, total, payment_method, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sale_id, item_id, quantity, price, total, payment_method, created_at),
        )
        conn.execute(
            "UPDATE items SET quantity = quantity - ? WHERE id = ?",
            (quantity, item_id),
        )
        
        conn.commit()

    return (
        jsonify(
            {
                "id": sale_id,
                "itemId": item_id,
                "quantity": quantity,
                "price": price,
                "total": total,
                "gain": round(gain, 2),
                "paymentMethod": payment_method,
                "createdAt": created_at,
            }
        ),
        201,
    )


@app.route("/api/sales/<sale_id>", methods=["DELETE"])
@require_auth
def delete_sale(sale_id):
    with get_db() as conn:
        sale = conn.execute(
            "SELECT * FROM sales WHERE id = ?", (sale_id,)
        ).fetchone()
        if not sale:
            return jsonify({"error": "Sale not found."}), 404

        conn.execute(
            "UPDATE items SET quantity = quantity + ? WHERE id = ?",
            (sale["quantity"], sale["item_id"]),
        )
        conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        conn.commit()

    return jsonify({"status": "deleted"})








@app.route("/api/sales/<sale_id>/invoice", methods=["GET"])
@require_auth
def get_invoice(sale_id):
    with get_db() as conn:
        sale = conn.execute(
            """
            SELECT s.id, s.item_id, s.quantity, s.price, s.total, s.payment_method, s.created_at, i.name, i.sku
            FROM sales s
            LEFT JOIN items i ON s.item_id = i.id
            WHERE s.id = ?
            """,
            (sale_id,)
        ).fetchone()
        
        if not sale:
            return jsonify({"error": "Sale not found"}), 404
        
        # Crear PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "FACTURA DE VENTA", ln=True, align="C")
        
        pdf.set_font("Arial", "", 10)
        pdf.ln(5)
        pdf.cell(0, 5, f"Fecha: {format_invoice_datetime(sale['created_at'])}", ln=True)
        pdf.cell(0, 5, f"Factura #: {sale['id'][:8]}", ln=True)
        
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(60, 5, "Producto", border=1)
        pdf.cell(30, 5, "SKU", border=1)
        pdf.cell(25, 5, "Cantidad", border=1)
        pdf.cell(30, 5, "Precio Unit.", border=1)
        pdf.cell(30, 5, "Total", border=1, ln=True)
        
        pdf.set_font("Arial", "", 10)
        pdf.cell(60, 5, pdf_safe(sale["name"]), border=1)
        pdf.cell(30, 5, pdf_safe(sale["sku"]), border=1)
        pdf.cell(25, 5, str(sale["quantity"]), border=1)
        pdf.cell(30, 5, f"${sale['price']:.2f}", border=1)
        pdf.cell(30, 5, f"${sale['total']:.2f}", border=1, ln=True)
        
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(120, 5, "TOTAL:", border=1)
        pdf.cell(30, 5, f"${sale['total']:.2f}", border=1, ln=True)
        
        pdf.ln(5)
        pdf.cell(0, 5, f"Metodo de Pago: {pdf_safe(sale['payment_method'])}", ln=True)
        
        # Devolver PDF
        pdf_output = pdf.output(dest="S")
        if isinstance(pdf_output, str):
            pdf_output = pdf_output.encode("latin-1", "replace")
        pdf_bytes = BytesIO(pdf_output)
        pdf_bytes.seek(0)
        
        return send_file(
            pdf_bytes,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"factura_{sale_id[:8]}.pdf"
        )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
