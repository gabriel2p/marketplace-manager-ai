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
    "Free Trial": {"creditos": 3, "nome": "Free Trial"},
    "Starter": {"creditos": 50, "nome": "Starter"},
    "Pro": {"creditos": 250, "nome": "Pro"},
    "Advanced": {"creditos": 1000, "nome": "Advanced"},
    "Admin": {"creditos": 999999, "nome": "Admin"}
}

SIGNUP_DEFAULT_CREDITS = 3

DISPOSABLE_EMAIL_DOMAINS = {
    "10minutemail.com", "10minutemail.net", "10minutemail.org", "20minutemail.com",
    "burnermail.io", "crazymailing.com", "disposablemail.com", "dispostable.com",
    "dropmail.me", "emailondeck.com", "fake-box.com", "fakeinbox.com", "fakemailgenerator.com",
    "getairmail.com", "getnada.com", "guerrillamail.biz", "guerrillamail.com",
    "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com", "inboxkitten.com",
    "jetable.org", "mailcatch.com", "maildrop.cc", "mailinator.com", "mailinator2.com",
    "mohmal.com", "mytemp.email", "nada.ltd", "sharklasers.com", "grr.la",
    "temp-mail.io", "temp-mail.org", "tempail.com", "tempmail.com", "tempmail.net",
    "throwawaymail.com", "trashmail.com", "trashmail.me", "trashmail.net", "yopmail.com",
    "yopmail.fr", "yopmail.net", "cool.fr.nf", "jetable.fr.nf", "courriel.fr.nf",
    "moncourrier.fr.nf", "monemail.fr.nf", "monmail.fr.nf", "guerrillamail.info",
    "pokemail.net", "spam4.me", "bccto.me", "chacuo.net", "0-mail.com", "mytempemail.com",
    "generator.email", "emailfake.com", "guerrillamail.de"
}


def is_disposable_email(email: str) -> bool:
    """Verifica se o e-mail pertence a serviços de e-mail temporários/descartáveis."""
    if not email or "@" not in email:
        return False
    domain = email.split("@")[-1].strip().lower()
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return True
    for disp in DISPOSABLE_EMAIL_DOMAINS:
        if domain == disp or domain.endswith("." + disp):
            return True
    suspicious_keywords = ["tempmail", "throwaway", "disposable", "fakemail", "trashmail", "guerrillamail", "10minutemail"]
    for kw in suspicious_keywords:
        if kw in domain:
            return True
    return False

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
    """Inicializa as tabelas 'usuarios' e 'logs_consumo_creditos' e aplica migrações de segurança."""
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
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    ip_origem VARCHAR(64) DEFAULT '',
                    device_id VARCHAR(128) DEFAULT '',
                    trial_granted BOOLEAN DEFAULT TRUE
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
            # Migrações idempotentes para schemas Postgres pré-existentes
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ip_origem VARCHAR(64) DEFAULT '';")
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS device_id VARCHAR(128) DEFAULT '';")
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS trial_granted BOOLEAN DEFAULT TRUE;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_ip ON usuarios(ip_origem);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_device_id ON usuarios(device_id);")
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
                    created_at TEXT,
                    ip_origem TEXT DEFAULT '',
                    device_id TEXT DEFAULT '',
                    trial_granted INTEGER DEFAULT 1
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
            # Migrações idempotentes para tabelas SQLite existentes
            cur.execute("PRAGMA table_info(usuarios);")
            col_names = [col[1] for col in cur.fetchall()]
            if "ip_origem" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN ip_origem TEXT DEFAULT '';")
            if "device_id" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN device_id TEXT DEFAULT '';")
            if "trial_granted" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN trial_granted INTEGER DEFAULT 1;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_ip ON usuarios(ip_origem);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_device_id ON usuarios(device_id);")

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
                f"""INSERT INTO usuarios (email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, created_at, ip_origem, device_id, trial_granted)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
                (admin_user, hashed, "Administrador Mestre", "Admin", 999999, 999999, "ativo", now_str, now_str, "127.0.0.1", "admin_device", True if engine == "postgres" else 1)
            )
            conn.commit()
            print(f"[DB] Usuário Admin Mestre '{admin_user}' criado com sucesso no banco de dados.")
        else:
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


def check_trial_eligibility(ip_origem: str = "", device_id: str = "", trial_claimed: bool = False) -> tuple[bool, str]:
    """
    Verifica se o novo cadastro é elegível aos 3 créditos gratuitos do Free Trial.
    Regras anti-abuso:
    1. Marcador no cliente (trial_claimed == True) -> Inelegível.
    2. Identificador de dispositivo (device_id) já vinculado a conta anterior com trial -> Inelegível.
    3. IP de origem com conta criada nas últimas 72 horas com trial (exceto localhost) -> Inelegível.
    """
    if trial_claimed:
        return False, "O teste gratuito de 3 créditos já foi utilizado neste dispositivo anteriormente."

    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        # Camada 2: Verificação por device_id persistente
        dev = (device_id or "").strip()
        if dev:
            cur.execute(
                f"SELECT id, email FROM usuarios WHERE device_id = {ph} AND (trial_granted = {ph} OR creditos_mensais > 0) LIMIT 1",
                (dev, True if engine == "postgres" else 1)
            )
            row = cur.fetchone()
            if row:
                return False, "O teste gratuito de 3 créditos já foi resgatado neste dispositivo."

        # Camada 3: Verificação por IP de Origem (Rate limit de 72h por IP)
        ip_clean = (ip_origem or "").strip()
        ignored_ips = {"127.0.0.1", "::1", "localhost", "testclient"}
        if ip_clean and ip_clean not in ignored_ips:
            if engine == "postgres":
                cur.execute(
                    f"""SELECT id, email FROM usuarios 
                        WHERE ip_origem = {ph} AND (trial_granted = TRUE OR creditos_mensais > 0)
                        AND (created_at >= NOW() - INTERVAL '72 hours')
                        LIMIT 1""",
                    (ip_clean,)
                )
                row_ip = cur.fetchone()
                if row_ip:
                    return False, "O teste gratuito de 3 créditos já foi resgatado nesta conexão de rede nas últimas 72 horas."
            else:
                cur.execute(
                    f"SELECT id, email, created_at FROM usuarios WHERE ip_origem = {ph} AND (trial_granted = 1 OR creditos_mensais > 0) ORDER BY id DESC LIMIT 1",
                    (ip_clean,)
                )
                row_ip = cur.fetchone()
                if row_ip:
                    created_raw = row_ip[2] if isinstance(row_ip, tuple) else row_ip["created_at"]
                    try:
                        created_dt = datetime.fromisoformat(created_raw)
                        if (get_brasilia_now() - created_dt).total_seconds() < 72 * 3600:
                            return False, "O teste gratuito de 3 créditos já foi resgatado nesta conexão de rede nas últimas 72 horas."
                    except Exception:
                        return False, "O teste gratuito de 3 créditos já foi resgatado nesta conexão de rede recentemente."

        return True, "Elegível ao teste gratuito."
    except Exception as e:
        print(f"[DB] Erro ao checar elegibilidade do trial: {e}")
        return True, "Elegível por fallback."
    finally:
        cur.close()
        conn.close()


def create_user(email: str, password: str, nome: str = "", plano: str = "Starter", creditos: int = None,
                ip_origem: str = "", device_id: str = "", trial_claimed: bool = False) -> dict:
    """Cria um novo usuário na plataforma com defesa anti-abuso em 3 camadas."""
    email_clean = email.strip().lower()
    if not email_clean or not password:
        return {"success": False, "error": "E-mail e senha são obrigatórios."}

    # Camada 1: Bloqueio de e-mails descartáveis / temporários
    if is_disposable_email(email_clean):
        return {
            "success": False,
            "error": "Por favor, utilize um e-mail corporativo ou pessoal válido (Gmail, Outlook, Yahoo, domínio próprio, etc.). E-mails descartáveis ou temporários não são permitidos para ativação do teste gratuito."
        }

    # Determinação de créditos e validação de elegibilidade do Free Trial
    if creditos is not None:
        credits = int(creditos)
        trial_granted = True
        trial_msg = "Créditos atribuídos manualmente."
    elif plano in ("Starter", "Free Trial"):
        is_eligible, reason = check_trial_eligibility(ip_origem=ip_origem, device_id=device_id, trial_claimed=trial_claimed)
        if is_eligible:
            credits = SIGNUP_DEFAULT_CREDITS
            trial_granted = True
            trial_msg = "Parabéns! 3 créditos gratuitos foram concedidos para você testar e validar o software na prática."
        else:
            credits = 0
            trial_granted = False
            trial_msg = reason
    else:
        plan_info = PLANS_CONFIG.get(plano, PLANS_CONFIG["Starter"])
        credits = plan_info["creditos"]
        trial_granted = True
        trial_msg = f"Plano {plano} ativado com {credits} créditos contratados."

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
            f"""INSERT INTO usuarios (email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, created_at, ip_origem, device_id, trial_granted)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})""",
            (email_clean, hashed, nome or email_clean.split("@")[0], plano, credits, credits, "ativo", renovacao_str, now_str, ip_origem or "", device_id or "", trial_granted if engine == "postgres" else (1 if trial_granted else 0))
        )
        conn.commit()

        cur.execute(f"SELECT id, email, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, ip_origem, device_id, trial_granted FROM usuarios WHERE email = {ph}", (email_clean,))
        user_row = cur.fetchone()
        user_dict = dict(user_row) if engine == "sqlite" else {
            "id": user_row[0],
            "email": user_row[1],
            "nome": user_row[2],
            "plano": user_row[3],
            "creditos_mensais": user_row[4],
            "creditos_restantes": user_row[5],
            "status_assinatura": user_row[6],
            "data_renovacao": str(user_row[7]),
            "ip_origem": user_row[8],
            "device_id": user_row[9],
            "trial_granted": bool(user_row[10])
        }
        return {
            "success": True,
            "user": user_dict,
            "trial_granted": trial_granted,
            "trial_message": trial_msg
        }
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
        cur.execute(f"SELECT id, email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, ip_origem, device_id, trial_granted FROM usuarios WHERE email = {ph}", (email.strip().lower(),))
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
            "data_renovacao": str(row[8]),
            "ip_origem": row[9] if len(row) > 9 else "",
            "device_id": row[10] if len(row) > 10 else "",
            "trial_granted": bool(row[11]) if len(row) > 11 else True
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
        cur.execute(f"SELECT id, email, senha_hash, nome, plano, creditos_mensais, creditos_restantes, status_assinatura, data_renovacao, ip_origem, device_id, trial_granted FROM usuarios WHERE id = {ph}", (user_id,))
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
            "data_renovacao": str(row[8]),
            "ip_origem": row[9] if len(row) > 9 else "",
            "device_id": row[10] if len(row) > 10 else "",
            "trial_granted": bool(row[11]) if len(row) > 11 else True
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

