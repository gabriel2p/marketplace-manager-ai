"""
Marketplace Manager AI - API FastAPI
Ponto de entrada do backend do sistema multiagente
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.models.intake import ProductIntakeRequest
from app.models.listing import HumanApprovalRequest
from app.agents.orchestrator import orchestrator_instance

app = FastAPI(
    title="Marketplace Manager AI - Backend",
    description="Sistema de Inteligência Comercial, Criação, Execução e Otimização Contínua em Marketplaces",
    version="1.0.0"
)

# Habilita CORS para o dashboard web React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {
        "system": "Marketplace Manager AI (Versão Definitiva)",
        "status": "ONLINE",
        "mode": "SANDBOX (Simulador Seguro Ativo)",
        "marketplaces": {
            "mercadolivre": "ATIVO (Modo Seguro)",
            "shopee": "PLUGAVEL (Scaffold Pronto)"
        }
    }


@app.post("/api/intake")
def start_intake_pipeline(intake: ProductIntakeRequest):
    """
    Inicia o fluxo multiagente com o SKU e parâmetros informados.
    Executa as camadas 1 a 12 do diagrama e pausa para Aprovação Humana (12.7).
    """
    try:
        ctx = orchestrator_instance.start_pipeline(intake)
        return {
            "session_id": ctx.session_id,
            "status": ctx.status,
            "message": "Pipeline executado até o portão de segurança 12.7. Aguardando aprovação humana.",
            "data": {
                "evidence_store": ctx.evidence_store.export_snapshot(),
                "specialists": ctx.specialists_output,
                "decision_gate": ctx.decision_gate_result,
                "prepared_listing": ctx.prepared_listing,
                "agent_logs": ctx.agent_logs
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}")
def get_session_status(session_id: str):
    """Consulta o estado atual da sessão e todos os artefatos de inteligência."""
    ctx = orchestrator_instance.sessions.get(session_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Sessão {session_id} não encontrada.")

    return {
        "session_id": ctx.session_id,
        "status": ctx.status,
        "created_at": ctx.created_at,
        "evidence_store": ctx.evidence_store.export_snapshot(),
        "specialists": ctx.specialists_output,
        "decision_gate": ctx.decision_gate_result,
        "prepared_listing": ctx.prepared_listing,
        "execution_result": ctx.execution_result,
        "agent_logs": ctx.agent_logs
    }


@app.post("/api/approval")
def process_human_approval(req: HumanApprovalRequest):
    """
    Processa a decisão humana da etapa 12.7 (Aprovar, Ajustar ou Rejeitar).
    Se aprovado, despacha para a Camada 13 (Execução Controlada com Guardrails).
    """
    try:
        res = orchestrator_instance.process_human_decision(
            session_id=req.session_id,
            action=req.action,
            custom_price=req.custom_price,
            custom_title=req.custom_title
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/marketplaces")
def get_marketplaces():
    return [
        {
            "id": "mercadolivre",
            "name": "Mercado Livre",
            "status": "Conectado (Sandbox Seguro)",
            "icon": "handshake",
            "active": True
        },
        {
            "id": "shopee",
            "name": "Shopee",
            "status": "Plugável (Arquitetura Pronta)",
            "icon": "shopping-bag",
            "active": False
        }
    ]
