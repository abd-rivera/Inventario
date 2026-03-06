import os
import sqlite3
import uuid
import importlib
import hashlib
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, request, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from fpdf import FPDF

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Detectar si estamos en Render con PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None
psycopg2 = None
psycopg2_extras = None

if USE_POSTGRES:
    try:
        psycopg2 = importlib.import_module("psycopg2")
        psycopg2_extras = importlib.import_module("psycopg2.extras")
    except ImportError:
        USE_POSTGRES = False

BASE_DIR = os.path.dirname(__file__)
FRONT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "front"))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "inventory.db")

if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
    load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"), override=False)

app = Flask(__name__, static_folder=FRONT_DIR, static_url_path="")

EMAIL_CODE_EXPIRY_MINUTES = 10
EMAIL_RESEND_COOLDOWN_SECONDS = 60
EMAIL_MAX_ATTEMPTS = 5


def is_production_env():
    app_env = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "").strip().lower()
    on_render = (os.getenv("RENDER") or "").strip().lower() == "true"
    return app_env == "production" or on_render


def allow_dev_email_fallback():
    default_value = "0" if is_production_env() else "1"
    raw = (os.getenv("ALLOW_DEV_EMAIL_FALLBACK", default_value) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def require_email_verification():
    # Temporary global bypass requested: disable OTP/email verification.
    # Keeping the function allows easy re-enable later from one place.
    return False


def allow_auto_verify_on_email_failure():
    """Allow local/dev to continue when SMTP/network is unavailable.

    In production this remains disabled unless explicitly enabled.
    """
    default_value = "0" if is_production_env() else "1"
    raw = (os.getenv("ALLOW_AUTO_VERIFY_ON_EMAIL_FAILURE", default_value) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def now_local():
    tz_name = os.getenv("APP_TZ", "America/Panama")
    return datetime.now(ZoneInfo(tz_name))


def normalize_email(value):
    return str(value or "").strip().lower()


def is_valid_email(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def hash_email_code(user_id, code):
    salt = os.getenv("AUTH_CODE_SALT", "inventario-dev-salt")
    payload = f"{user_id}:{code}:{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def generate_email_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def parse_iso_datetime(value):
    if not value:
        return now_local()
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return now_local()


def send_verification_email(to_email, username, code):
    gmail_user = (os.getenv("GMAIL_USER") or "").strip()
    gmail_app_password = (os.getenv("GMAIL_APP_PASSWORD") or "").strip()

    smtp_host = (os.getenv("SMTP_HOST") or "").strip() or (
        "smtp.gmail.com" if gmail_user and gmail_app_password else None
    )
    smtp_port_raw = (os.getenv("SMTP_PORT") or "587").strip()
    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        return False, f"Invalid SMTP_PORT value: '{smtp_port_raw}'. Use 587 or 465."

    smtp_user = (os.getenv("SMTP_USER") or "").strip() or gmail_user
    smtp_pass = (os.getenv("SMTP_PASS") or "").strip() or gmail_app_password
    smtp_from = (os.getenv("SMTP_FROM") or "").strip() or smtp_user

    if not smtp_host or not smtp_user or not smtp_pass or not smtp_from:
        return False, (
            "SMTP is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM "
            "or use GMAIL_USER and GMAIL_APP_PASSWORD."
        )

    msg = EmailMessage()
    msg["Subject"] = "Codigo de verificacion - Plus Control"
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(
        f"Hola {username},\n\n"
        f"Tu codigo de verificacion es: {code}\n"
        f"Este codigo expira en {EMAIL_CODE_EXPIRY_MINUTES} minutos.\n\n"
        "Si no solicitaste esta cuenta, ignora este correo."
    )

    try:
        timeout_seconds = 20
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout_seconds) as server:
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout_seconds) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


def store_email_verification(conn, user_id, code):
    now = now_local()
    expires_at = (now + timedelta(minutes=EMAIL_CODE_EXPIRY_MINUTES)).isoformat()
    resend_available_at = (now + timedelta(seconds=EMAIL_RESEND_COOLDOWN_SECONDS)).isoformat()
    created_at = now.isoformat()
    code_hash = hash_email_code(user_id, code)

    conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user_id,))
    conn.execute(
        """
        INSERT INTO email_verifications
        (user_id, code_hash, expires_at, attempts, resend_available_at, created_at)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (user_id, code_hash, expires_at, resend_available_at, created_at),
    )


def create_session(conn, user_id):
    token = str(uuid.uuid4())
    created_at = now_local().isoformat()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, created_at),
    )
    return token


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
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        # Retornar un wrapper que proporciona execute() compatible
        return PostgresConnectionWrapper(conn)
    else:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn


class PostgresConnectionWrapper:
    """Wrapper que hace psycopg2 compatible con sqlite3"""
    def __init__(self, conn):
        self.conn = conn
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.conn.close()
    
    def execute(self, query, params=None):
        cur = self.conn.cursor(cursor_factory=psycopg2_extras.RealDictCursor)
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return PostgresCursor(cur, self.conn)
    
    def commit(self):
        try:
            self.conn.commit()
        except:
            pass
    
    def close(self):
        self.conn.close()
    
    def rollback(self):
        try:
            self.conn.rollback()
        except:
            pass


class PostgresCursor:
    """Cursor wrapper para psycopg2 compatible con sqlite3"""
    def __init__(self, cur, conn):
        self.cur = cur
        self.conn = conn
    
    def fetchone(self):
        return self.cur.fetchone()
    
    def fetchall(self):
        return self.cur.fetchall()
    
    def close(self):
        self.cur.close()


def execute_query(conn, query, params=None, fetch=False, fetch_one=False):
    """Ejecutar query de forma agnóstica entre SQLite y PostgreSQL"""
    try:
        if params:
            cur = conn.execute(query, params)
        else:
            cur = conn.execute(query)
        if fetch_one:
            result = cur.fetchone()
            cur.close()
            return result
        elif fetch:
            result = cur.fetchall()
            cur.close()
            return result
        else:
            conn.commit()
            return None
    except Exception as e:
        print(f"Query error: {e}")
        if USE_POSTGRES:
            conn.rollback()
        raise


def init_db():
    conn = get_db()
    try:
        if USE_POSTGRES:
            cur = conn.cursor()
        else:
            cur = conn.cursor()
        
        # Crear tablas base
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_verifications (
                user_id TEXT PRIMARY KEY,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                resend_available_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        cur.execute(
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
                cost_unit REAL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        
        # Para SQLite, agregar columnas faltantes si es necesario
        if not USE_POSTGRES:
            user_columns = {
                row[1]
                for row in cur.execute("PRAGMA table_info(users)").fetchall()
            }
            try:
                if "email" not in user_columns:
                    cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
            except:
                pass
            try:
                if "email_verified" not in user_columns:
                    cur.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1")
            except:
                pass

            columns = {
                row[1]
                for row in cur.execute("PRAGMA table_info(items)").fetchall()
            }
            try:
                if "description" not in columns:
                    cur.execute("ALTER TABLE items ADD COLUMN description TEXT")
            except: pass
            try:
                if "image_url" not in columns:
                    cur.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
            except: pass
            try:
                if "status" not in columns:
                    cur.execute("ALTER TABLE items ADD COLUMN status TEXT")
            except: pass
            try:
                if "cost_unit" not in columns:
                    cur.execute("ALTER TABLE items ADD COLUMN cost_unit REAL DEFAULT 0")
            except: pass
        else:
            try:
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT")
            except:
                pass
            try:
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified INTEGER NOT NULL DEFAULT 1")
            except:
                pass

        try:
            cur.execute("UPDATE users SET email_verified = 1 WHERE email_verified IS NULL")
        except:
            pass
        
        conn.commit()
    except Exception as e:
        print(f"Error initializing DB: {e}")
        if not USE_POSTGRES:
            conn.rollback()
    finally:
        if not USE_POSTGRES:
            conn.close()
        else:
            conn.commit()
            conn.close()


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
    email = normalize_email(payload.get("email"))
    password = str(payload.get("password", "")).strip()

    if not username or not password or not email:
        return jsonify({"error": "Username, email and password required."}), 400

    if not is_valid_email(email):
        return jsonify({"error": "Invalid email format."}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    if not require_email_verification():
        user_id = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        created_at = now_local().isoformat()
        token = str(uuid.uuid4())

        with get_db() as conn:
            existing_username = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if existing_username:
                return jsonify({"error": "Username already exists."}), 400

            existing_email = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(?)", (email,)
            ).fetchone()
            if existing_email:
                return jsonify({"error": "Email already exists."}), 400

            conn.execute(
                "INSERT INTO users (id, username, email, password_hash, email_verified, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, email, password_hash, 1, created_at),
            )
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, created_at),
            )
            conn.commit()

        return jsonify({"token": token, "username": username, "requiresVerification": False}), 201

    with get_db() as conn:
        existing_username = conn.execute(
            "SELECT id, email, email_verified FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing_username:
            if existing_username["email_verified"] == 1:
                return jsonify({"error": "Username already exists."}), 400
            existing_user_email = normalize_email(existing_username["email"])
            if existing_user_email != email:
                return jsonify({"error": "Username already exists with a different email."}), 400

            user_id = existing_username["id"]
            code = generate_email_code()
            store_email_verification(conn, user_id, code)
            conn.commit()

            email_ok, email_error = send_verification_email(email, username, code)
            if not email_ok:
                if allow_dev_email_fallback():
                    return jsonify(
                        {
                            "requiresVerification": True,
                            "email": email,
                            "username": username,
                            "devCode": code,
                            "warning": f"Email not sent in local/dev mode: {email_error}",
                        }
                    ), 200
                if allow_auto_verify_on_email_failure():
                    conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
                    token = create_session(conn, user_id)
                    conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user_id,))
                    conn.commit()
                    return jsonify(
                        {
                            "token": token,
                            "username": username,
                            "requiresVerification": False,
                            "warning": f"Auto-verified in local/dev because email could not be sent: {email_error}",
                        }
                    ), 200
                return jsonify({"error": f"Could not send verification email: {email_error}"}), 503

            return jsonify({"requiresVerification": True, "email": email, "username": username}), 200

        existing_email = conn.execute(
            "SELECT id, username, email_verified FROM users WHERE lower(email) = lower(?)", (email,)
        ).fetchone()
        if existing_email:
            if existing_email["email_verified"] == 1:
                return jsonify({"error": "Email already exists."}), 400

            user_id = existing_email["id"]
            username = existing_email["username"]
            code = generate_email_code()
            store_email_verification(conn, user_id, code)
            conn.commit()

            email_ok, email_error = send_verification_email(email, username, code)
            if not email_ok:
                if allow_dev_email_fallback():
                    return jsonify(
                        {
                            "requiresVerification": True,
                            "email": email,
                            "username": username,
                            "devCode": code,
                            "warning": f"Email not sent in local/dev mode: {email_error}",
                        }
                    ), 200
                if allow_auto_verify_on_email_failure():
                    conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
                    token = create_session(conn, user_id)
                    conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user_id,))
                    conn.commit()
                    return jsonify(
                        {
                            "token": token,
                            "username": username,
                            "requiresVerification": False,
                            "warning": f"Auto-verified in local/dev because email could not be sent: {email_error}",
                        }
                    ), 200
                return jsonify({"error": f"Could not send verification email: {email_error}"}), 503

            return jsonify({"requiresVerification": True, "email": email, "username": username}), 200

        user_id = str(uuid.uuid4())
        password_hash = generate_password_hash(password)
        created_at = now_local().isoformat()

        conn.execute(
            "INSERT INTO users (id, username, email, password_hash, email_verified, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, email, password_hash, 0, created_at),
        )

        code = generate_email_code()
        store_email_verification(conn, user_id, code)
        conn.commit()

    email_ok, email_error = send_verification_email(email, username, code)

    if not email_ok:
        if allow_dev_email_fallback():
            return jsonify(
                {
                    "requiresVerification": True,
                    "email": email,
                    "username": username,
                    "devCode": code,
                    "warning": f"Email not sent in local/dev mode: {email_error}",
                }
            ), 201
        if allow_auto_verify_on_email_failure():
            with get_db() as conn:
                conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
                token = create_session(conn, user_id)
                conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user_id,))
                conn.commit()
            return jsonify(
                {
                    "token": token,
                    "username": username,
                    "requiresVerification": False,
                    "warning": f"Auto-verified in local/dev because email could not be sent: {email_error}",
                }
            ), 201
        return jsonify({"error": f"Could not send verification email: {email_error}"}), 503

    return jsonify({"requiresVerification": True, "email": email, "username": username}), 201


@app.route("/api/auth/verify-email", methods=["POST"])
def verify_email():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))
    code = str(payload.get("code", "")).strip()

    if not email or not code:
        return jsonify({"error": "Email and code are required."}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, email_verified FROM users WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()

        if not user:
            return jsonify({"error": "User not found."}), 404

        if user["email_verified"] == 1:
            token = create_session(conn, user["id"])
            conn.commit()
            return jsonify({"token": token, "username": user["username"], "alreadyVerified": True})

        verification = conn.execute(
            "SELECT code_hash, expires_at, attempts FROM email_verifications WHERE user_id = ?",
            (user["id"],),
        ).fetchone()

        if not verification:
            return jsonify({"error": "Verification code not found. Request a new one."}), 404

        if verification["attempts"] >= EMAIL_MAX_ATTEMPTS:
            return jsonify({"error": "Too many attempts. Request a new code."}), 429

        if parse_iso_datetime(verification["expires_at"]) < now_local():
            return jsonify({"error": "Verification code expired. Request a new code."}), 400

        if hash_email_code(user["id"], code) != verification["code_hash"]:
            conn.execute(
                "UPDATE email_verifications SET attempts = attempts + 1 WHERE user_id = ?",
                (user["id"],),
            )
            conn.commit()
            return jsonify({"error": "Invalid verification code."}), 400

        conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user["id"],))
        conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user["id"],))

        token = create_session(conn, user["id"])
        conn.commit()

    return jsonify({"token": token, "username": user["username"]})


@app.route("/api/auth/resend-code", methods=["POST"])
def resend_code():
    payload = request.get_json(silent=True) or {}
    email = normalize_email(payload.get("email"))

    if not email:
        return jsonify({"error": "Email is required."}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, email_verified FROM users WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()

        if not user:
            return jsonify({"error": "User not found."}), 404

        if user["email_verified"] == 1:
            return jsonify({"error": "Email is already verified."}), 400

        verification = conn.execute(
            "SELECT resend_available_at FROM email_verifications WHERE user_id = ?",
            (user["id"],),
        ).fetchone()

        if verification:
            resend_at = parse_iso_datetime(verification["resend_available_at"])
            now = now_local()
            if resend_at > now:
                wait_seconds = int((resend_at - now).total_seconds())
                return jsonify({"error": "Please wait before requesting another code.", "waitSeconds": wait_seconds}), 429

        code = generate_email_code()
        store_email_verification(conn, user["id"], code)
        conn.commit()

    email_ok, email_error = send_verification_email(email, user["username"], code)

    if not email_ok:
        if allow_dev_email_fallback():
            return jsonify(
                {
                    "status": "sent-dev",
                    "devCode": code,
                    "warning": f"Email not sent in local/dev mode: {email_error}",
                }
            )
        return jsonify({"error": f"Could not send verification email: {email_error}"}), 503

    return jsonify({"status": "sent"})


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username and password required."}), 400

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, email, password_hash, email_verified FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401

    if user["email_verified"] != 1 and not require_email_verification():
        with get_db() as conn:
            conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user["id"],))
            conn.commit()

    if user["email_verified"] != 1:
        verification_code = generate_email_code()
        with get_db() as conn:
            store_email_verification(conn, user["id"], verification_code)
            conn.commit()

        email_ok, email_error = send_verification_email(user["email"], user["username"], verification_code)
        if not email_ok:
            if allow_dev_email_fallback():
                return jsonify(
                    {
                        "error": "Email not verified.",
                        "code": "EMAIL_NOT_VERIFIED",
                        "email": user["email"],
                        "devCode": verification_code,
                        "warning": f"Email not sent in local/dev mode: {email_error}",
                    }
                ), 403
            if allow_auto_verify_on_email_failure():
                with get_db() as conn:
                    conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user["id"],))
                    conn.execute("DELETE FROM email_verifications WHERE user_id = ?", (user["id"],))
                    token = create_session(conn, user["id"])
                    conn.commit()
                return jsonify(
                    {
                        "token": token,
                        "username": user["username"],
                        "warning": f"Auto-verified in local/dev because email could not be sent: {email_error}",
                    }
                ), 200
            return jsonify(
                {
                    "error": f"Email not verified. Could not send verification code: {email_error}",
                    "code": "EMAIL_NOT_VERIFIED",
                    "email": user["email"],
                }
            ), 403

        return jsonify(
            {
                "error": "Email not verified. We sent you a new verification code.",
                "code": "EMAIL_NOT_VERIFIED",
                "email": user["email"],
            }
        ), 403

    with get_db() as conn:
        token = create_session(conn, user["id"])
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


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=not is_production_env())
