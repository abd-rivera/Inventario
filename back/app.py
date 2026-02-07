import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO

from flask import Flask, jsonify, request, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

BASE_DIR = os.path.dirname(__file__)
FRONT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "front"))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "inventory.db")

app = Flask(__name__, static_folder=FRONT_DIR, static_url_path="")


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
                id TEXT PRIMARY KEY,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                cost_unit REAL NOT NULL,
                total_cost REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items (id)
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
        "threshold": row["threshold"],
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
    if not name or not sku or not location:
        return None, "Missing name, sku, or location."

    item_id = str(payload.get("id") or uuid.uuid4())
    quantity = to_int(payload.get("quantity"))
    threshold = to_int(payload.get("threshold"))
    price = to_float(payload.get("price"))
    updated_at = payload.get("updatedAt") or datetime.now().isoformat()

    return (
        {
            "id": item_id,
            "name": name,
            "sku": sku,
            "quantity": quantity,
            "location": location,
            "price": price,
            "threshold": threshold,
            "updatedAt": updated_at,
        },
        None,
    )


def get_week_range():
    now = datetime.now()
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
            cutoff = (datetime.now() - timedelta(days=7)).isoformat()
            conn.execute(
                "DELETE FROM sessions WHERE created_at < ?", (cutoff,)
            )
            conn.commit()
    except Exception as e:
        print(f"Error cleaning up sessions: {e}")


@app.route("/")
def index():
    return send_from_directory(FRONT_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    file_path = os.path.join(FRONT_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(FRONT_DIR, path)
    return send_from_directory(FRONT_DIR, "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


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
        created_at = datetime.now().isoformat()

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
    created_at = datetime.now().isoformat()

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
            (id, name, sku, quantity, location, price, threshold, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["name"],
                item["sku"],
                item["quantity"],
                item["location"],
                item["price"],
                item["threshold"],
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
            SET name = ?, sku = ?, quantity = ?, location = ?, price = ?,
                threshold = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                item["name"],
                item["sku"],
                item["quantity"],
                item["location"],
                item["price"],
                item["threshold"],
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
            (id, name, sku, quantity, location, price, threshold, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item["id"],
                    item["name"],
                    item["sku"],
                    item["quantity"],
                    item["location"],
                    item["price"],
                    item["threshold"],
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
            "SELECT * FROM sales ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([row_to_sale(row) for row in rows])


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
        download_name=f"backup-{datetime.now().strftime('%Y-%m-%d')}.db"
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
    created_at = datetime.now().isoformat()

    with get_db() as conn:
        item = conn.execute(
            "SELECT quantity FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return jsonify({"error": "Item not found."}), 404

        if item["quantity"] < quantity:
            return jsonify({"error": "Not enough stock."}), 400

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


@app.route("/api/finance", methods=["GET"])
@require_auth
def get_finance():
    with get_db() as conn:
        # Capital inicial
        config = conn.execute(
            "SELECT value FROM config WHERE key = 'initial_capital'"
        ).fetchone()
        initial_capital = float(config["value"]) if config else 0

        # Total invertido en compras
        purchases = conn.execute(
            "SELECT SUM(total_cost) as total FROM purchases"
        ).fetchone()
        total_invested = float(purchases["total"]) if purchases["total"] else 0

        # Costo promedio por producto
        items_data = conn.execute(
            """
            SELECT 
                i.id,
                i.name,
                COALESCE(
                    (SELECT SUM(cost_unit * quantity) FROM purchases WHERE item_id = i.id) / 
                    NULLIF((SELECT SUM(quantity) FROM purchases WHERE item_id = i.id), 0),
                    0
                ) as cost_unit
            FROM items i
            """
        ).fetchall()

        # Calcular ganancia de ventas
        total_gain = 0
        for item in items_data:
            sales_of_item = conn.execute(
                "SELECT SUM(quantity) as qty_sold, i.price FROM sales s JOIN items i ON s.item_id = i.id WHERE s.item_id = ? GROUP BY s.item_id",
                (item["id"],),
            ).fetchone()
            if sales_of_item:
                qty_sold = sales_of_item["qty_sold"]
                cost_unit = item["cost_unit"]
                total_gain += (sales_of_item["price"] - cost_unit) * qty_sold

        capital_actual = initial_capital + total_invested + total_gain
        margin = (total_gain / capital_actual * 100) if capital_actual > 0 else 0

        # Ganancia por período
        today = datetime.now().date().isoformat()
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        month_ago = (datetime.now() - timedelta(days=30)).date().isoformat()

        gain_today = conn.execute(
            f"""
            SELECT COALESCE(SUM(s.total), 0) as revenue FROM sales s 
            WHERE DATE(s.created_at) = '{today}'
            """
        ).fetchone()["revenue"]

        gain_week = conn.execute(
            f"""
            SELECT COALESCE(SUM(s.total), 0) as revenue FROM sales s 
            WHERE DATE(s.created_at) >= '{week_ago}'
            """
        ).fetchone()["revenue"]

        gain_month = conn.execute(
            f"""
            SELECT COALESCE(SUM(s.total), 0) as revenue FROM sales s 
            WHERE DATE(s.created_at) >= '{month_ago}'
            """
        ).fetchone()["revenue"]

    return jsonify(
        {
            "initialCapital": initial_capital,
            "totalInvested": total_invested,
            "totalGain": total_gain,
            "capitalActual": capital_actual,
            "marginPercent": round(margin, 2),
            "gainToday": gain_today,
            "gainWeek": gain_week,
            "gainMonth": gain_month,
        }
    )


@app.route("/api/config", methods=["POST"])
@require_auth
def set_config():
    payload = request.get_json()
    key = payload.get("key")
    value = payload.get("value")

    if not key or value is None:
        return jsonify({"error": "key and value required"}), 400

    with get_db() as conn:
        conn.execute("DELETE FROM config WHERE key = ?", (key,))
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
        conn.commit()

    return jsonify({"key": key, "value": value}), 201


@app.route("/api/purchases", methods=["POST"])
@require_auth
def create_purchase():
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("itemId")
    quantity = to_int(payload.get("quantity"))
    cost_unit = to_float(payload.get("costUnit"))

    if not item_id or quantity <= 0 or cost_unit < 0:
        return jsonify({"error": "Invalid purchase data."}), 400

    total_cost = quantity * cost_unit
    purchase_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    with get_db() as conn:
        # Verificar que el item existe
        item = conn.execute(
            "SELECT * FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            return jsonify({"error": "Item not found."}), 404

        # Agregar la compra
        conn.execute(
            "INSERT INTO purchases (id, item_id, quantity, cost_unit, total_cost, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (purchase_id, item_id, quantity, cost_unit, total_cost, created_at),
        )
        conn.commit()

    return jsonify(
        {
            "id": purchase_id,
            "itemId": item_id,
            "quantity": quantity,
            "costUnit": cost_unit,
            "totalCost": total_cost,
            "createdAt": created_at,
        }
    ), 201


@app.route("/api/purchases", methods=["GET"])
@require_auth
def get_purchases():
    with get_db() as conn:
        purchases = conn.execute(
            """
            SELECT p.id, p.item_id, p.quantity, p.cost_unit, p.total_cost, p.created_at, i.name
            FROM purchases p 
            LEFT JOIN items i ON p.item_id = i.id 
            ORDER BY p.created_at DESC
            """
        ).fetchall()

    return jsonify(
        [
            {
                "id": p["id"],
                "itemId": p["item_id"],
                "itemName": p["name"] or "Unknown Item",
                "quantity": p["quantity"],
                "costUnit": p["cost_unit"],
                "totalCost": p["total_cost"],
                "createdAt": p["created_at"],
            }
            for p in purchases
        ]
    )


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
        pdf.cell(0, 5, f"Fecha: {sale['created_at'][:10]}", ln=True)
        pdf.cell(0, 5, f"Factura #: {sale['id'][:8]}", ln=True)
        
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(60, 5, "Producto", border=1)
        pdf.cell(30, 5, "SKU", border=1)
        pdf.cell(25, 5, "Cantidad", border=1)
        pdf.cell(30, 5, "Precio Unit.", border=1)
        pdf.cell(30, 5, "Total", border=1, ln=True)
        
        pdf.set_font("Arial", "", 10)
        pdf.cell(60, 5, sale["name"] or "N/A", border=1)
        pdf.cell(30, 5, sale["sku"] or "N/A", border=1)
        pdf.cell(25, 5, str(sale["quantity"]), border=1)
        pdf.cell(30, 5, f"${sale['price']:.2f}", border=1)
        pdf.cell(30, 5, f"${sale['total']:.2f}", border=1, ln=True)
        
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(120, 5, "TOTAL:", border=1)
        pdf.cell(30, 5, f"${sale['total']:.2f}", border=1, ln=True)
        
        pdf.ln(5)
        pdf.cell(0, 5, f"Metodo de Pago: {sale['payment_method']}", ln=True)
        
        # Devolver PDF
        pdf_bytes = BytesIO(pdf.output(dest='S').encode('latin-1'))
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
