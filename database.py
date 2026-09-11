import os
import re
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

# Fuso horário oficial de Brasília (UTC-3)
BRASILIA_TZ = timezone(timedelta(hours=-3))

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

PLANS_CONFIG = {
    "Starter": {"creditos": 50, "nome": "Starter"},
    "Pro": {"creditos": 250, "nome": "Pro"},
    "Advanced": {"creditos": 1000, "nome": "Advanced"},
    "Admin": {"creditos": 999999, "nome": "Admin"}
}

IS_POSTGRES = bool(DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")))

if IS_POSTGRES and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketplace_saas.db")


def get_connection():
    """Retorna uma conexão ativa com o banco (PostgreSQL ou SQLite fallback)."""
    if IS_POSTGRES:
        try:
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(DATABASE_URL)
            return conn, "postgres"
        except Exception as e:
            print(f"[DB] Falha ao conectar no PostgreSQL ({e}). Usando SQLite local.")
    
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn, "sqlite"


def hash_password(password: str) -> str:
    """Gera hash PBKDF2-SHA256 seguro com salt aleatório."""
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"{salt}${pw_hash}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verifica se a senha digitada confere com o hash ou senha pura histórica."""
    if not stored_hash:
        return False
    if "$" in stored_hash:
        parts = stored_hash.split("$", 1)
        salt = parts[0]
        expected_hash = parts[1]
        actual_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
        return secrets.compare_digest(actual_hash, expected_hash)
    # Suporte a senhas antigas em texto puro (legado do admin)
    return secrets.compare_digest(plain_password, stored_hash)


def get_brasilia_now():
    """Retorna o timestamp atual no fuso horário de Brasília."""
    return datetime.now(BRASILIA_TZ)


def init_db():
    """Inicializa as tabelas 'usuarios' e 'logs_consumo_creditos'."""
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        if engine == "postgres":
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    senha_hash VARCHAR(255) NOT NULL,
                    nome VARCHAR(100) DEFAULT '',
                    plano VARCHAR(50) DEFAULT 'Starter',
                    creditos_mensais INTEGER DEFAULT 50,
                    creditos_restantes INTEGER DEFAULT 50,
                    status_assinatura VARCHAR(50) DEFAULT 'ativo',
                    data_renovacao TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs_consumo_creditos (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    produto_sku VARCHAR(100) DEFAULT '',
                    produto_nome VARCHAR(255) DEFAULT '',
                    marketplace VARCHAR(50) DEFAULT 'Mercado Livre',
                    creditos_debitados INTEGER DEFAULT 1,
                    saldo_restante_na_hora INTEGER NOT NULL,
                    data_hora TIMESTAMP WITH TIME ZONE NOT NULL
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_usuario_id ON logs_consumo_creditos(usuario_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);")
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    senha_hash TEXT NOT NULL,
                    nome TEXT DEFAULT '',
                    plano TEXT DEFAULT 'Starter',
                    creditos_mensais INTEGER DEFAULT 50,
                    creditos_restantes INTEGER DEFAULT 50,
                    status_assinatura TEXT DEFAULT 'ativo',
                    data_renovacao TEXT,
                    created_at TEXT
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs_consumo_creditos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    produto_sku TEXT DEFAULT '',
                    produto_nome TEXT DEFAULT '',
                    marketplace TEXT DEFAULT 'Mercado Livre',
                    creditos_debitados INTEGER DEFAULT 1,
                    saldo_restante_na_hora INTEGER NOT NULL,
                    data_hora TEXT NOT NULL,
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_usuario_id ON logs_consumo_creditos(usuario_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);")

        conn.commit()
        print(f"[DB] Banco de dados inicializado com sucesso (Engine: {engine}).")
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao criar tabelas: {e}")
    finally:
        cur.close()
        conn.close()


def seed_default_admin(admin_user: str = "admin", admin_password: str = "admin123"):
    """Garante que o administrador configurado no ambiente exista no banco de dados."""
    if not admin_user or not admin_password:
        return
    conn, engine = get_connection()
    cur = conn.cursor()
    try:
        ph = "%s" if engine == "postgres" else "?"
        cur.execute(f"SELECT id, senha_hash FROM usuarios WHERE email = {ph}", (admin_user,))
        row = cur.fetchone()
        now_str = get_brasilia_now().isoformat()
        if not row:
            hashed = hash_password(admin_password)
            cur.execute(
                f"""INSERT INTO usuarios (email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, created_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                (admin_user, hashed, "Administrador Mestre", "Admin", 999999, 999999, "ativo", now_str, now_str)
            )
            conn.commit()
            print(f"[DB] Usuário Admin Mestre '{admin_user}' criado com sucesso no banco de dados.")
        else:
            # Garante que o admin tenha plano Admin e status ativo
            cur.execute(
                f"UPDATE usuarios SET plano = 'Admin', creditos_mensais = 999999, status_assinatura = 'ativo' WHERE email = {ph}",
                (admin_user,)
            )
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao semear admin: {e}")
    finally:
        cur.close()
        conn.close()


def create_user(email: str, password: str, nome: str = "", plano: str = "Starter") -> dict:
    """Cria um novo usuário cliente na plataforma."""
    email_clean = email.strip().lower()
    if not email_clean or not password:
        return {"success": False, "error": "E-mail e senha são obrigatórios."}
    
    plan_info = PLANS_CONFIG.get(plano, PLANS_CONFIG["Starter"])
    credits = plan_info["creditos"]
    hashed = hash_password(password)
    now_dt = get_brasilia_now()
    renovacao_dt = now_dt + timedelta(days=30)
    now_str = now_dt.isoformat()
    renovacao_str = renovacao_dt.isoformat()

    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(f"SELECT id FROM usuarios WHERE email = {ph}", (email_clean,))
        if cur.fetchone():
            return {"success": False, "error": "Este e-mail já está cadastrado no sistema."}

        cur.execute(
            f"""INSERT INTO usuarios (email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (email_clean, hashed, nome or email_clean.split("@")[0], plano, credits, credits, "ativo", renovacao_str, now_str)
        )
        conn.commit()

        cur.execute(f"SELECT id, email, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao FROM usuarios WHERE email = {ph}", (email_clean,))
        user_row = cur.fetchone()
        user_dict = dict(user_row) if engine == "sqlite" else {
            "id": user_row[0],
            "email": user_row[1],
            "nome": user_row[2],
            "plano": user_row[3],
            "creditos_mensais": user_row[4],
            "creditos_restantes": user_row[5],
            "status_assinatura": user_row[6],
            "data_renovacao": str(user_row[7])
        }
        return {"success": True, "user": user_dict}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def get_user_by_email(email: str) -> dict:
    """Busca os dados de um usuário pelo e-mail."""
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(f"SELECT id, email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao FROM usuarios WHERE email = {ph}", (email.strip().lower(),))
        row = cur.fetchone()
        if not row:
            return None
        if engine == "sqlite":
            return dict(row)
        return {
            "id": row[0],
            "email": row[1],
            "senha_hash": row[2],
            "nome": row[3],
            "plano": row[4],
            "creditos_mensais": row[5],
            "creditos_restantes": row[6],
            "status_assinatura": row[7],
            "data_renovacao": str(row[8])
        }
    finally:
        cur.close()
        conn.close()


def get_user_by_id(user_id: int) -> dict:
    """Busca os dados de um usuário pelo ID numérico."""
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(f"SELECT id, email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao FROM usuarios WHERE id = {ph}", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        if engine == "sqlite":
            return dict(row)
        return {
            "id": row[0],
            "email": row[1],
            "senha_hash": row[2],
            "nome": row[3],
            "plano": row[4],
            "creditos_mensais": row[5],
            "creditos_restantes": row[6],
            "status_assinatura": row[7],
            "data_renovacao": str(row[8])
        }
    finally:
        cur.close()
        conn.close()


def authenticate_user(email_or_user: str, password: str) -> dict:
    """Valida credenciais no banco e retorna perfil com saldo de créditos."""
    user = get_user_by_email(email_or_user)
    if not user:
        return {"authenticated": False, "error": "Usuário ou senha incorretos."}

    if not verify_password(password, user.get("senha_hash")):
        return {"authenticated": False, "error": "Usuário ou senha incorretos."}

    return {
        "authenticated": True,
        "user_id": user["id"],
        "email": user["email"],
        "nome": user.get("nome", ""),
        "plano": user.get("plano", "Starter"),
        "role": "admin" if user.get("plano") == "Admin" else "user",
        "creditos_mensais": user.get("creditos_mensais", 50),
        "creditos_restantes": user.get("creditos_restantes", 0),
        "status_assinatura": user.get("status_assinatura", "ativo"),
        "data_renovacao": user.get("data_renovacao")
    }


def consume_credit(user_id: int, sku: str, produto_nome: str, marketplace: str = "Mercado Livre", creditos: int = 1) -> dict:
    """
    Middleware Atômico de Débito de Créditos & Auditoria:
    1. Valida se o usuário tem assinatura ativa ('ativo')
    2. Valida se 'creditos_restantes >= creditos'
    3. Em transação atômica:
       - Subtrai os créditos de 'usuarios'
       - Grava a linha de auditoria com timestamp de Brasília em 'logs_consumo_creditos'
    4. Se saldo for insuficiente ou status inativo, bloqueia e retorna motivo claro.
    """
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(f"SELECT id, email, plano, creditos_restantes, status_assinatura FROM usuarios WHERE id = {ph}", (user_id,))
        user_row = cur.fetchone()
        if not user_row:
            return {"success": False, "reason": "not_found", "message": "Usuário não encontrado."}

        plano = user_row[2] if engine == "postgres" else user_row["plano"]
        saldo_atual = user_row[3] if engine == "postgres" else user_row["creditos_restantes"]
        status = user_row[4] if engine == "postgres" else user_row["status_assinatura"]

        if status != "ativo":
            return {
                "success": False,
                "reason": "inactive",
                "message": "Sua assinatura não está ativa. Verifique seu pagamento ou entre em contato com o suporte."
            }

        # Administradores têm cota infinita garantida
        if plano == "Admin":
            now_dt = get_brasilia_now().isoformat()
            cur.execute(
                f"""INSERT INTO logs_consumo_creditos (usuario_id, produto_sku, produto_nome, marketplace, creditos_debitados, saldo_restante_na_hora, data_hora)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                (user_id, sku or "N/A", produto_nome or "Produto", marketplace, creditos, saldo_atual, now_dt)
            )
            conn.commit()
            return {
                "success": True,
                "creditos_debitados": creditos,
                "saldo_restante": saldo_atual,
                "plano": plano,
                "status_assinatura": status
            }

        if saldo_atual < creditos:
            return {
                "success": False,
                "reason": "no_credits",
                "message": "Você atingiu o limite de consultas do seu plano atual. Faça um upgrade ou recarregue seus créditos para continuar.",
                "saldo_restante": saldo_atual,
                "plano": plano
            }

        novo_saldo = saldo_atual - creditos
        now_dt = get_brasilia_now().isoformat()

        # Atualização atômica
        cur.execute(
            f"UPDATE usuarios SET creditos_restantes = creditos_restantes - {ph} WHERE id = {ph} AND creditos_restantes >= {ph}",
            (creditos, user_id, creditos)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {
                "success": False,
                "reason": "concurrency_limit",
                "message": "Saldo insuficiente para completar a requisição concorrente."
            }

        cur.execute(
            f"""INSERT INTO logs_consumo_creditos (usuario_id, produto_sku, produto_nome, marketplace, creditos_debitados, saldo_restante_na_hora, data_hora)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (user_id, sku or "N/A", produto_nome or "Produto", marketplace, creditos, novo_saldo, now_dt)
        )
        conn.commit()

        return {
            "success": True,
            "creditos_debitados": creditos,
            "saldo_restante": novo_saldo,
            "plano": plano,
            "status_assinatura": status
        }
    except Exception as e:
        conn.rollback()
        return {"success": False, "reason": "db_error", "message": str(e)}
    finally:
        cur.close()
        conn.close()


def get_user_audit_logs(user_id: int, limit: int = 30) -> list:
    """Recupera os registros de auditoria e consumo de créditos de um usuário."""
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(
            f"""SELECT id, produto_sku, produto_nome, marketplace, creditos_debitados, saldo_restante_na_hora, data_hora
                FROM logs_consumo_creditos
                WHERE usuario_id = {ph}
                ORDER BY id DESC
                LIMIT {ph}""",
            (user_id, limit)
        )
        rows = cur.fetchall()
        logs = []
        for r in rows:
            if engine == "sqlite":
                logs.append(dict(r))
            else:
                logs.append({
                    "id": r[0],
                    "produto_sku": r[1],
                    "produto_nome": r[2],
                    "marketplace": r[3],
                    "creditos_debitados": r[4],
                    "saldo_restante_na_hora": r[5],
                    "data_hora": str(r[6])
                })
        return logs
    finally:
        cur.close()
        conn.close()


def recharge_user_credits(email: str, plano: str = "Pro", status: str = "ativo", credits: int = None, add_only: bool = False) -> dict:
    """
    Atualiza o plano e recarrega a cota mensal de créditos (utilizado pelos Webhooks de pagamento).
    Se add_only for True, incrementa o saldo atual sem alterar o plano contratado.
    """
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(f"SELECT id, creditos_restantes, plano FROM usuarios WHERE email = {ph}", (email.strip().lower(),))
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": f"Usuário '{email}' não encontrado no banco."}

        cur_saldo = row[1] if engine == "postgres" else row["creditos_restantes"]
        cur_plano = row[2] if engine == "postgres" else row["plano"]

        if add_only and credits:
            novo_saldo = cur_saldo + int(credits)
            cur.execute(
                f"UPDATE usuarios SET creditos_restantes = {ph}, status_assinatura = {ph} WHERE email = {ph}",
                (novo_saldo, status, email.strip().lower())
            )
            conn.commit()
            return {
                "success": True,
                "email": email,
                "plano": cur_plano,
                "plan": cur_plano,
                "creditos_restantes": novo_saldo,
                "new_credits_left": novo_saldo,
                "status_assinatura": status
            }

        plan_info = PLANS_CONFIG.get(plano, PLANS_CONFIG["Pro"])
        cred_total = int(credits) if credits is not None else plan_info["creditos"]
        now_dt = get_brasilia_now()
        next_renewal = (now_dt + timedelta(days=30)).isoformat()

        cur.execute(
            f"""UPDATE usuarios
                SET plano = {ph},
                    creditos_mensais = {ph},
                    creditos_restantes = {ph},
                    status_assinatura = {ph},
                    data_renovacao = {ph}
                WHERE email = {ph}""",
            (plano, cred_total, cred_total, status, next_renewal, email.strip().lower())
        )
        conn.commit()
        return {
            "success": True,
            "email": email,
            "plano": plano,
            "plan": plano,
            "creditos_restantes": cred_total,
            "new_credits_left": cred_total,
            "status_assinatura": status,
            "data_renovacao": next_renewal
        }
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def update_user(user_id: int, **fields) -> bool:
    """Atualiza campos arbitrários de um usuário (saldo, plano, status, etc)."""
    if not fields:
        return True
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    set_clauses = [f"{k} = {ph}" for k in fields.keys()]
    values = list(fields.values()) + [user_id]
    try:
        cur.execute(f"UPDATE usuarios SET {', '.join(set_clauses)} WHERE id = {ph}", values)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao atualizar usuário: {e}")
        return False
    finally:
        cur.close()
        conn.close()

