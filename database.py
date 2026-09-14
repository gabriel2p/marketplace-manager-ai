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

# Se for PostgreSQL em nuvem (Render, Supabase, etc.) e sslmode não estiver explícito, adiciona sslmode=require
POSTGRES_CONNECT_URL = DATABASE_URL
if IS_POSTGRES:
    if "sslmode=" not in POSTGRES_CONNECT_URL and ("render.com" in POSTGRES_CONNECT_URL or "supabase.co" in POSTGRES_CONNECT_URL or "aws" in POSTGRES_CONNECT_URL):
        sep = "&" if "?" in POSTGRES_CONNECT_URL else "?"
        POSTGRES_CONNECT_URL = f"{POSTGRES_CONNECT_URL}{sep}sslmode=require"

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketplace_saas.db")
ACTIVE_ENGINE = "postgres" if IS_POSTGRES else "sqlite"
_last_postgres_fail_time = 0.0


def get_connection():
    """Retorna uma conexão ativa com o banco (PostgreSQL ou SQLite fallback com tolerância a falhas)."""
    global ACTIVE_ENGINE, _last_postgres_fail_time
    now = datetime.now().timestamp()

    if IS_POSTGRES and (now - _last_postgres_fail_time > 60.0):
        try:
            import psycopg2
            import psycopg2.extras
            # Timeout curto de 5s para nunca travar o servidor nem o deploy do Render
            conn = psycopg2.connect(POSTGRES_CONNECT_URL, connect_timeout=5)
            ACTIVE_ENGINE = "postgres"
            _last_postgres_fail_time = 0.0
            return conn, "postgres"
        except Exception as e:
            _last_postgres_fail_time = now
            ACTIVE_ENGINE = "sqlite"
            print(f"[DB] Aviso: Conexão PostgreSQL falhou ({e}). Usando SQLite local com segurança.", flush=True)
    
    ACTIVE_ENGINE = "sqlite"
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
                    trial_granted BOOLEAN DEFAULT TRUE,
                    ml_user_id VARCHAR(64) DEFAULT '',
                    ml_access_token TEXT DEFAULT '',
                    ml_refresh_token TEXT DEFAULT '',
                    ml_connected_at TIMESTAMP WITH TIME ZONE
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
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ml_user_id VARCHAR(64) DEFAULT '';")
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ml_access_token TEXT DEFAULT '';")
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ml_refresh_token TEXT DEFAULT '';")
            cur.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS ml_connected_at TIMESTAMP WITH TIME ZONE;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_ip ON usuarios(ip_origem);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_usuarios_device_id ON usuarios(device_id);")

            # Tabela de Produtos e Preços por SKU (PostgreSQL)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS produtos_precificados (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    sku VARCHAR(100) NOT NULL,
                    titulo VARCHAR(255) DEFAULT '',
                    categoria VARCHAR(100) DEFAULT '',
                    marketplace VARCHAR(50) DEFAULT 'mercadolivre',
                    cmv NUMERIC(10, 2) DEFAULT 0.00,
                    margem_alvo NUMERIC(5, 4) DEFAULT 0.20,
                    peso_kg NUMERIC(8, 3) DEFAULT 0.50,
                    embalagem_custo NUMERIC(10, 2) DEFAULT 3.00,
                    logistica_tipo VARCHAR(50) DEFAULT 'both',
                    reputacao VARCHAR(50) DEFAULT 'green',
                    preco_venda_sugerido NUMERIC(10, 2) NOT NULL,
                    lucro_liquido_unitario NUMERIC(10, 2) DEFAULT 0.00,
                    margem_liquida_percentual NUMERIC(6, 2) DEFAULT 0.00,
                    comissao_ml NUMERIC(10, 2) DEFAULT 0.00,
                    frete_estimado NUMERIC(10, 2) DEFAULT 0.00,
                    imposto_estimado NUMERIC(10, 2) DEFAULT 0.00,
                    estoque_qtd INTEGER DEFAULT 1,
                    veredito_gate VARCHAR(50) DEFAULT 'A',
                    dados_extras TEXT DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(usuario_id, sku, marketplace)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_produtos_precificados_user_sku ON produtos_precificados(usuario_id, sku);")

            # Tabela de Concorrentes Validados e Ignorados (PostgreSQL)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS concorrentes_feedback (
                    id SERIAL PRIMARY KEY,
                    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    query VARCHAR(255) NOT NULL,
                    sku VARCHAR(100) DEFAULT '',
                    product_id VARCHAR(100) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    product_title VARCHAR(255) DEFAULT '',
                    product_price NUMERIC(10, 2) DEFAULT 0.00,
                    product_seller VARCHAR(100) DEFAULT '',
                    product_permalink TEXT DEFAULT '',
                    product_thumbnail TEXT DEFAULT '',
                    is_full BOOLEAN DEFAULT FALSE,
                    free_shipping BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(usuario_id, query, product_id)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_concorrentes_feedback_user_query ON concorrentes_feedback(usuario_id, query);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_concorrentes_feedback_user_sku ON concorrentes_feedback(usuario_id, sku);")

            # Tabela de Sessões Persistentes de Usuários (PostgreSQL)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessoes_usuarios (
                    token VARCHAR(64) PRIMARY KEY,
                    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP WITH TIME ZONE
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessoes_token ON sessoes_usuarios(token);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessoes_usuario_id ON sessoes_usuarios(usuario_id);")
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
                    trial_granted INTEGER DEFAULT 1,
                    ml_user_id TEXT DEFAULT '',
                    ml_access_token TEXT DEFAULT '',
                    ml_refresh_token TEXT DEFAULT '',
                    ml_connected_at TEXT DEFAULT ''
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

            # Tabela de Produtos e Preços por SKU (SQLite)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS produtos_precificados (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    titulo TEXT DEFAULT '',
                    categoria TEXT DEFAULT '',
                    marketplace TEXT DEFAULT 'mercadolivre',
                    cmv REAL DEFAULT 0.00,
                    margem_alvo REAL DEFAULT 0.20,
                    peso_kg REAL DEFAULT 0.50,
                    embalagem_custo REAL DEFAULT 3.00,
                    logistica_tipo TEXT DEFAULT 'both',
                    reputacao TEXT DEFAULT 'green',
                    preco_venda_sugerido REAL NOT NULL,
                    lucro_liquido_unitario REAL DEFAULT 0.00,
                    margem_liquida_percentual REAL DEFAULT 0.00,
                    comissao_ml REAL DEFAULT 0.00,
                    frete_estimado REAL DEFAULT 0.00,
                    imposto_estimado REAL DEFAULT 0.00,
                    estoque_qtd INTEGER DEFAULT 1,
                    veredito_gate TEXT DEFAULT 'A',
                    dados_extras TEXT DEFAULT '{}',
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                    UNIQUE(usuario_id, sku, marketplace)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_produtos_precificados_user_sku ON produtos_precificados(usuario_id, sku);")

            # Tabela de Concorrentes Validados e Ignorados (SQLite)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS concorrentes_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id INTEGER NOT NULL,
                    query TEXT NOT NULL,
                    sku TEXT DEFAULT '',
                    product_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    product_title TEXT DEFAULT '',
                    product_price REAL DEFAULT 0.00,
                    product_seller TEXT DEFAULT '',
                    product_permalink TEXT DEFAULT '',
                    product_thumbnail TEXT DEFAULT '',
                    is_full INTEGER DEFAULT 0,
                    free_shipping INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                    UNIQUE(usuario_id, query, product_id)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_concorrentes_feedback_user_query ON concorrentes_feedback(usuario_id, query);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_concorrentes_feedback_user_sku ON concorrentes_feedback(usuario_id, sku);")

            # Tabela de Sessões Persistentes de Usuários (SQLite)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sessoes_usuarios (
                    token TEXT PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    expires_at TEXT,
                    FOREIGN KEY(usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessoes_token ON sessoes_usuarios(token);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sessoes_usuario_id ON sessoes_usuarios(usuario_id);")

            # Migrações idempotentes para tabelas SQLite existentes
            cur.execute("PRAGMA table_info(usuarios);")
            col_names = [col[1] for col in cur.fetchall()]
            if "ip_origem" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN ip_origem TEXT DEFAULT '';")
            if "device_id" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN device_id TEXT DEFAULT '';")
            if "trial_granted" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN trial_granted INTEGER DEFAULT 1;")
            if "ml_user_id" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN ml_user_id TEXT DEFAULT '';")
            if "ml_access_token" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN ml_access_token TEXT DEFAULT '';")
            if "ml_refresh_token" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN ml_refresh_token TEXT DEFAULT '';")
            if "ml_connected_at" not in col_names:
                cur.execute("ALTER TABLE usuarios ADD COLUMN ml_connected_at TEXT DEFAULT '';")
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


def get_user_ml_credentials(user_id: int) -> dict:
    """Retorna as credenciais individuais da conta do Mercado Livre vinculadas a um usuário específico."""
    if not user_id:
        return {"connected": False, "access_token": "", "refresh_token": "", "ml_user_id": "", "connected_at": ""}
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(f"SELECT ml_access_token, ml_refresh_token, ml_user_id, ml_connected_at FROM usuarios WHERE id = {ph}", (user_id,))
        row = cur.fetchone()
        if row:
            token = row[0] if engine == "postgres" else (row["ml_access_token"] if "ml_access_token" in row.keys() else row[0])
            refresh = row[1] if engine == "postgres" else (row["ml_refresh_token"] if "ml_refresh_token" in row.keys() else row[1])
            ml_uid = row[2] if engine == "postgres" else (row["ml_user_id"] if "ml_user_id" in row.keys() else row[2])
            conn_at = row[3] if engine == "postgres" else (row["ml_connected_at"] if "ml_connected_at" in row.keys() else row[3])
            token_str = (token or "").strip()
            return {
                "connected": bool(token_str),
                "access_token": token_str,
                "refresh_token": (refresh or "").strip(),
                "ml_user_id": str(ml_uid or ""),
                "connected_at": str(conn_at or "")
            }
        return {"connected": False, "access_token": "", "refresh_token": "", "ml_user_id": "", "connected_at": ""}
    except Exception as e:
        print(f"[DB] Erro ao buscar credenciais ML do usuario {user_id}: {e}", flush=True)
        return {"connected": False, "access_token": "", "refresh_token": "", "ml_user_id": "", "connected_at": ""}
    finally:
        cur.close()
        conn.close()


def save_user_ml_credentials(user_id: int, access_token: str, refresh_token: str = "", ml_user_id: str = "") -> bool:
    """Salva com segurança as credenciais do Mercado Livre de forma isolada para o lojista."""
    if not user_id:
        return False
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    now_str = get_brasilia_now().isoformat()
    try:
        cur.execute(
            f"""UPDATE usuarios 
                SET ml_access_token = {ph}, ml_refresh_token = {ph}, ml_user_id = {ph}, ml_connected_at = {ph}
                WHERE id = {ph}""",
            (access_token.strip(), (refresh_token or "").strip(), str(ml_user_id or ""), now_str, user_id)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao salvar credenciais ML do usuario {user_id}: {e}", flush=True)
        return False
    finally:
        cur.close()
        conn.close()


def disconnect_user_ml(user_id: int) -> bool:
    """Desconecta a conta do Mercado Livre do lojista, limpando os tokens com segurança."""
    return save_user_ml_credentials(user_id, "", "", "")


def upsert_sku_product(user_id: int, sku: str, data: dict) -> dict:
    """
    Insere ou atualiza deterministicamente a precificação e parâmetros de um SKU para o lojista.
    """
    if not user_id or not sku:
        return {"success": False, "error": "Parâmetros user_id e sku obrigatórios"}
    
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    now_str = get_brasilia_now().isoformat()

    titulo = str(data.get("titulo") or data.get("product_name") or data.get("title_raw") or "").strip()
    categoria = str(data.get("categoria") or data.get("category_hint") or "").strip()
    marketplace = str(data.get("marketplace", "mercadolivre")).strip().lower()
    cmv = float(data.get("cmv") or data.get("cost_price") or 0.0)
    margem_alvo = float(data.get("margem_alvo") or data.get("target_margin") or 0.20)
    peso_kg = float(data.get("peso_kg") or data.get("weight_kg") or 0.50)
    embalagem_custo = float(data.get("embalagem_custo") or data.get("packaging_cost") or 3.00)
    logistica_tipo = str(data.get("logistica_tipo") or data.get("logistics_type") or "both").strip()
    reputacao = str(data.get("reputacao") or data.get("reputation") or "green").strip()
    preco_venda = float(data.get("preco_venda_sugerido") or data.get("suggested_price") or 0.0)
    lucro_liquido = float(data.get("lucro_liquido_unitario") or data.get("net_profit") or 0.0)
    margem_liquida = float(data.get("margem_liquida_percentual") or data.get("net_margin") or 0.0)
    comissao_ml = float(data.get("comissao_ml") or data.get("ml_fee") or 0.0)
    frete_estimado = float(data.get("frete_estimado") or data.get("shipping") or 0.0)
    imposto_estimado = float(data.get("imposto_estimado") or data.get("tax") or 0.0)
    estoque_qtd = int(data.get("estoque_qtd") or data.get("stock_quantity") or data.get("monthly_units") or 1)
    veredito_gate = str(data.get("veredito_gate") or "A").strip()
    dados_extras = json.dumps(data.get("dados_extras") or {}, ensure_ascii=False)

    try:
        if engine == "postgres":
            query = f"""
                INSERT INTO produtos_precificados (
                    usuario_id, sku, titulo, categoria, marketplace, cmv, margem_alvo, peso_kg,
                    embalagem_custo, logistica_tipo, reputacao, preco_venda_sugerido,
                    lucro_liquido_unitario, margem_liquida_percentual, comissao_ml, frete_estimado,
                    imposto_estimado, estoque_qtd, veredito_gate, dados_extras, created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
                )
                ON CONFLICT (usuario_id, sku, marketplace) DO UPDATE SET
                    titulo = EXCLUDED.titulo,
                    categoria = EXCLUDED.categoria,
                    cmv = EXCLUDED.cmv,
                    margem_alvo = EXCLUDED.margem_alvo,
                    peso_kg = EXCLUDED.peso_kg,
                    embalagem_custo = EXCLUDED.embalagem_custo,
                    logistica_tipo = EXCLUDED.logistica_tipo,
                    reputacao = EXCLUDED.reputacao,
                    preco_venda_sugerido = EXCLUDED.preco_venda_sugerido,
                    lucro_liquido_unitario = EXCLUDED.lucro_liquido_unitario,
                    margem_liquida_percentual = EXCLUDED.margem_liquida_percentual,
                    comissao_ml = EXCLUDED.comissao_ml,
                    frete_estimado = EXCLUDED.frete_estimado,
                    imposto_estimado = EXCLUDED.imposto_estimado,
                    estoque_qtd = EXCLUDED.estoque_qtd,
                    veredito_gate = EXCLUDED.veredito_gate,
                    dados_extras = EXCLUDED.dados_extras,
                    updated_at = EXCLUDED.updated_at;
            """
        else:
            query = f"""
                INSERT INTO produtos_precificados (
                    usuario_id, sku, titulo, categoria, marketplace, cmv, margem_alvo, peso_kg,
                    embalagem_custo, logistica_tipo, reputacao, preco_venda_sugerido,
                    lucro_liquido_unitario, margem_liquida_percentual, comissao_ml, frete_estimado,
                    imposto_estimado, estoque_qtd, veredito_gate, dados_extras, created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
                )
                ON CONFLICT(usuario_id, sku, marketplace) DO UPDATE SET
                    titulo = excluded.titulo,
                    categoria = excluded.categoria,
                    cmv = excluded.cmv,
                    margem_alvo = excluded.margem_alvo,
                    peso_kg = excluded.peso_kg,
                    embalagem_custo = excluded.embalagem_custo,
                    logistica_tipo = excluded.logistica_tipo,
                    reputacao = excluded.reputacao,
                    preco_venda_sugerido = excluded.preco_venda_sugerido,
                    lucro_liquido_unitario = excluded.lucro_liquido_unitario,
                    margem_liquida_percentual = excluded.margem_liquida_percentual,
                    comissao_ml = excluded.comissao_ml,
                    frete_estimado = excluded.frete_estimado,
                    imposto_estimado = excluded.imposto_estimado,
                    estoque_qtd = excluded.estoque_qtd,
                    veredito_gate = excluded.veredito_gate,
                    dados_extras = excluded.dados_extras,
                    updated_at = excluded.updated_at;
            """
        params = (
            user_id, sku.strip(), titulo, categoria, marketplace, cmv, margem_alvo, peso_kg,
            embalagem_custo, logistica_tipo, reputacao, preco_venda, lucro_liquido, margem_liquida,
            comissao_ml, frete_estimado, imposto_estimado, estoque_qtd, veredito_gate, dados_extras,
            now_str, now_str
        )
        cur.execute(query, params)
        conn.commit()
        return {
            "success": True,
            "sku": sku,
            "preco_venda_sugerido": preco_venda,
            "lucro_liquido_unitario": lucro_liquido,
            "margem_liquida_percentual": margem_liquida,
            "updated_at": now_str
        }
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao salvar SKU {sku} para usuario {user_id}: {e}", flush=True)
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def get_sku_product(user_id: int, sku: str, marketplace: str = "mercadolivre") -> dict:
    """Busca o produto e histórico financeiro de um SKU específico do lojista."""
    if not user_id or not sku:
        return None
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(
            f"""SELECT * FROM produtos_precificados 
                WHERE usuario_id = {ph} AND sku = {ph} AND marketplace = {ph}""",
            (user_id, sku.strip(), marketplace.strip().lower())
        )
        row = cur.fetchone()
        if not row:
            return None
        if engine == "sqlite":
            return dict(row)
        cols = [desc[0] for desc in cur.description]
        return dict(zip(cols, row))
    except Exception as e:
        print(f"[DB] Erro ao buscar SKU {sku} do usuario {user_id}: {e}", flush=True)
        return None
    finally:
        cur.close()
        conn.close()


def list_sku_products(user_id: int, marketplace: str = "mercadolivre", limit: int = 50) -> list:
    """Retorna a lista de produtos precificados salvos para o usuário ordenados pelo mais recente."""
    if not user_id:
        return []
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    try:
        cur.execute(
            f"""SELECT * FROM produtos_precificados 
                WHERE usuario_id = {ph} AND marketplace = {ph}
                ORDER BY updated_at DESC LIMIT {limit}""",
            (user_id, marketplace.strip().lower())
        )
        rows = cur.fetchall()
        if engine == "sqlite":
            return [dict(r) for r in rows]
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        print(f"[DB] Erro ao listar SKUs do usuario {user_id}: {e}", flush=True)
        return []
    finally:
        cur.close()
        conn.close()


def save_competitor_feedback(user_id: int, query: str, product_id: str, status: str, sku: str = "", item_data: dict = None) -> dict:
    """
    Salva ou atualiza a classificação de um concorrente ('direct' ou 'ignored') para um termo de busca e SKU.
    """
    if not user_id or not query or not product_id:
        return {"success": False, "error": "Parametros obrigatorios ausentes"}
    
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    now_str = get_brasilia_now().isoformat()
    q_norm = query.strip().lower()
    item_data = item_data or {}

    p_title = str(item_data.get("title") or item_data.get("product_title") or "").strip()
    p_price = float(item_data.get("price") or item_data.get("product_price") or 0.0)
    p_seller = str(item_data.get("seller") or item_data.get("product_seller") or "").strip()
    p_permalink = str(item_data.get("permalink") or item_data.get("product_permalink") or "").strip()
    p_thumb = str(item_data.get("thumbnail") or item_data.get("product_thumbnail") or "").strip()
    p_is_full = bool(item_data.get("is_full", False))
    p_free_shipping = bool(item_data.get("free_shipping", False))

    try:
        if engine == "postgres":
            sql = f"""
                INSERT INTO concorrentes_feedback (
                    usuario_id, query, sku, product_id, status, product_title, product_price,
                    product_seller, product_permalink, product_thumbnail, is_full, free_shipping,
                    created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}
                )
                ON CONFLICT (usuario_id, query, product_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    sku = CASE WHEN EXCLUDED.sku != '' THEN EXCLUDED.sku ELSE concorrentes_feedback.sku END,
                    product_title = CASE WHEN EXCLUDED.product_title != '' THEN EXCLUDED.product_title ELSE concorrentes_feedback.product_title END,
                    product_price = CASE WHEN EXCLUDED.product_price > 0 THEN EXCLUDED.product_price ELSE concorrentes_feedback.product_price END,
                    product_seller = CASE WHEN EXCLUDED.product_seller != '' THEN EXCLUDED.product_seller ELSE concorrentes_feedback.product_seller END,
                    product_permalink = CASE WHEN EXCLUDED.product_permalink != '' THEN EXCLUDED.product_permalink ELSE concorrentes_feedback.product_permalink END,
                    product_thumbnail = CASE WHEN EXCLUDED.product_thumbnail != '' THEN EXCLUDED.product_thumbnail ELSE concorrentes_feedback.product_thumbnail END,
                    is_full = EXCLUDED.is_full,
                    free_shipping = EXCLUDED.free_shipping,
                    updated_at = EXCLUDED.updated_at;
            """
        else:
            sql = f"""
                INSERT INTO concorrentes_feedback (
                    usuario_id, query, sku, product_id, status, product_title, product_price,
                    product_seller, product_permalink, product_thumbnail, is_full, free_shipping,
                    created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}, {ph}, {ph}, {ph},
                    {ph}, {ph}
                )
                ON CONFLICT(usuario_id, query, product_id) DO UPDATE SET
                    status = excluded.status,
                    sku = CASE WHEN excluded.sku != '' THEN excluded.sku ELSE concorrentes_feedback.sku END,
                    product_title = CASE WHEN excluded.product_title != '' THEN excluded.product_title ELSE concorrentes_feedback.product_title END,
                    product_price = CASE WHEN excluded.product_price > 0 THEN excluded.product_price ELSE concorrentes_feedback.product_price END,
                    product_seller = CASE WHEN excluded.product_seller != '' THEN excluded.product_seller ELSE concorrentes_feedback.product_seller END,
                    product_permalink = CASE WHEN excluded.product_permalink != '' THEN excluded.product_permalink ELSE concorrentes_feedback.product_permalink END,
                    product_thumbnail = CASE WHEN excluded.product_thumbnail != '' THEN excluded.product_thumbnail ELSE concorrentes_feedback.product_thumbnail END,
                    is_full = excluded.is_full,
                    free_shipping = excluded.free_shipping,
                    updated_at = excluded.updated_at;
            """
        params = (
            user_id, q_norm, sku.strip(), product_id.strip(), status.strip().lower(),
            p_title, p_price, p_seller, p_permalink, p_thumb,
            (1 if p_is_full else 0) if engine == "sqlite" else p_is_full,
            (1 if p_free_shipping else 0) if engine == "sqlite" else p_free_shipping,
            now_str, now_str
        )
        cur.execute(sql, params)
        conn.commit()
        return {"success": True, "product_id": product_id, "status": status, "query": q_norm}
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao salvar feedback do concorrente {product_id}: {e}", flush=True)
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def remove_competitor_feedback(user_id: int, query: str, product_id: str) -> dict:
    """Remove a marcação de um concorrente (volta ao estado neutro de potencial concorrente)."""
    if not user_id or not query:
        return {"success": False, "error": "Parametros invalidos"}
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    q_norm = query.strip().lower()
    try:
        if product_id == "all":
            cur.execute(f"DELETE FROM concorrentes_feedback WHERE usuario_id = {ph} AND query = {ph}", (user_id, q_norm))
        else:
            cur.execute(f"DELETE FROM concorrentes_feedback WHERE usuario_id = {ph} AND query = {ph} AND product_id = {ph}", (user_id, q_norm, product_id.strip()))
        conn.commit()
        return {"success": True, "message": "Feedback removido com sucesso"}
    except Exception as e:
        conn.rollback()
        print(f"[DB] Erro ao remover feedback do concorrente {product_id}: {e}", flush=True)
        return {"success": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


def get_competitor_feedback_for_query(user_id: int, query: str, sku: str = "") -> dict:
    """
    Retorna as listas de concorrentes validados ('direct') e ignorados ('ignored') para a busca / SKU.
    """
    result = {"direct": [], "ignored": []}
    if not user_id or (not query and not sku):
        return result
    conn, engine = get_connection()
    cur = conn.cursor()
    ph = "%s" if engine == "postgres" else "?"
    q_norm = query.strip().lower() if query else ""
    sku_norm = sku.strip()
    seen_ids = set()
    try:
        if q_norm and sku_norm:
            sql = f"""SELECT product_id, status, product_title, product_price, product_seller,
                             product_permalink, product_thumbnail, is_full, free_shipping
                      FROM concorrentes_feedback
                      WHERE usuario_id = {ph} AND (query = {ph} OR (sku != '' AND sku = {ph}))
                      ORDER BY updated_at DESC"""
            params = (user_id, q_norm, sku_norm)
        elif sku_norm:
            sql = f"""SELECT product_id, status, product_title, product_price, product_seller,
                             product_permalink, product_thumbnail, is_full, free_shipping
                      FROM concorrentes_feedback
                      WHERE usuario_id = {ph} AND sku = {ph}
                      ORDER BY updated_at DESC"""
            params = (user_id, sku_norm)
        else:
            sql = f"""SELECT product_id, status, product_title, product_price, product_seller,
                             product_permalink, product_thumbnail, is_full, free_shipping
                      FROM concorrentes_feedback
                      WHERE usuario_id = {ph} AND query = {ph}
                      ORDER BY updated_at DESC"""
            params = (user_id, q_norm)

        cur.execute(sql, params)
        rows = cur.fetchall()
        for r in rows:
            if engine == "sqlite":
                p_id = r["product_id"]
                st = r["status"]
                item = {
                    "id": p_id,
                    "title": r["product_title"],
                    "price": float(r["product_price"] or 0.0),
                    "seller": r["product_seller"],
                    "permalink": r["product_permalink"],
                    "thumbnail": r["product_thumbnail"],
                    "is_full": bool(r["is_full"]),
                    "free_shipping": bool(r["free_shipping"]),
                    "is_direct": (st == "direct"),
                    "available": True,
                    "stock_status": "in_stock"
                }
            else:
                p_id = r[0]
                st = r[1]
                item = {
                    "id": p_id,
                    "title": r[2],
                    "price": float(r[3] or 0.0),
                    "seller": r[4],
                    "permalink": r[5],
                    "thumbnail": r[6],
                    "is_full": bool(r[7]),
                    "free_shipping": bool(r[8]),
                    "is_direct": (st == "direct"),
                    "available": True,
                    "stock_status": "in_stock"
                }
            if p_id in seen_ids:
                continue
            seen_ids.add(p_id)

            if st == "direct":
                result["direct"].append(item)
            elif st == "ignored":
                result["ignored"].append(p_id)
        return result
    except Exception as e:
        print(f"[DB] Erro ao buscar feedback de concorrentes para '{query}' (SKU: '{sku}'): {e}", flush=True)
        return result
    finally:
        cur.close()
        conn.close()


def save_user_session(token: str, user_id: int, duration_days: int = 30):
    """Persiste a sessão do usuário no banco de dados para resistir a reinicializações de contêiner/servidor."""
    if not token or not user_id:
        return
    conn, engine = get_connection()
    try:
        cur = conn.cursor()
        expires = datetime.now(timezone.utc) + timedelta(days=duration_days)
        if engine == "postgres":
            cur.execute("""
                INSERT INTO sessoes_usuarios (token, usuario_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (token) DO UPDATE SET expires_at = EXCLUDED.expires_at;
            """, (token, user_id, expires))
        else:
            cur.execute("""
                INSERT INTO sessoes_usuarios (token, usuario_id, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET expires_at = excluded.expires_at;
            """, (token, user_id, expires.isoformat()))
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro ao salvar sessao {token[:8]}...: {e}", flush=True)
    finally:
        cur.close()
        conn.close()


def get_user_by_session_token(token: str):
    """Busca o usuário associado a um token de sessão persistido no banco de dados."""
    if not token:
        return None
    conn, engine = get_connection()
    try:
        cur = conn.cursor()
        if engine == "postgres":
            cur.execute("""
                SELECT u.id, u.email, u.nome, u.plano, u.creditos_mensais, u.creditos_restantes, u.status_assinatura
                FROM sessoes_usuarios s
                JOIN usuarios u ON s.usuario_id = u.id
                WHERE s.token = %s AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP);
            """, (token,))
            row = cur.fetchone()
            if row:
                return {
                    "user_id": row[0],
                    "id": row[0],
                    "email": row[1],
                    "username": row[1],
                    "nome": row[2] or row[1].split("@")[0],
                    "role": "admin" if row[3] == "Admin" else "user",
                    "plano": row[3],
                    "creditos_mensais": row[4],
                    "creditos_restantes": row[5],
                    "status_assinatura": row[6]
                }
        else:
            cur.execute("""
                SELECT u.id, u.email, u.nome, u.plano, u.creditos_mensais, u.creditos_restantes, u.status_assinatura
                FROM sessoes_usuarios s
                JOIN usuarios u ON s.usuario_id = u.id
                WHERE s.token = ? AND (s.expires_at IS NULL OR s.expires_at > datetime('now'));
            """, (token,))
            row = cur.fetchone()
            if row:
                return {
                    "user_id": row["id"],
                    "id": row["id"],
                    "email": row["email"],
                    "username": row["email"],
                    "nome": row["nome"] or row["email"].split("@")[0],
                    "role": "admin" if row["plano"] == "Admin" else "user",
                    "plano": row["plano"],
                    "creditos_mensais": row["creditos_mensais"],
                    "creditos_restantes": row["creditos_restantes"],
                    "status_assinatura": row["status_assinatura"]
                }
    except Exception as e:
        print(f"[DB] Erro ao buscar sessao {token[:8]}...: {e}", flush=True)
    finally:
        cur.close()
        conn.close()
    return None


def delete_user_session(token: str):
    """Remove a sessão persistida ao fazer logout."""
    if not token:
        return
    conn, engine = get_connection()
    try:
        cur = conn.cursor()
        if engine == "postgres":
            cur.execute("DELETE FROM sessoes_usuarios WHERE token = %s;", (token,))
        else:
            cur.execute("DELETE FROM sessoes_usuarios WHERE token = ?;", (token,))
        conn.commit()
    except Exception as e:
        print(f"[DB] Erro ao deletar sessao: {e}", flush=True)
    finally:
        cur.close()
        conn.close()




