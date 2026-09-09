"""
Orchestrator - Agente Principal
Baseado na Camada 2 do diagrama:
- Interpreta o objetivo
- Decompõe em tarefas
- Define dependências
- Seleciona especialistas
- Controla contexto e memória (Evidence Store)
- Garante coerência
- Decide próximas ações
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from app.models.intake import ProductIntakeRequest
from app.models.evidence import EvidenceType
from app.models.listing import PreparedListing, DecisionGateResult, HumanApprovalAction
from app.core.evidence_store import EvidenceStore
from app.core.financial_engine import FinancialEngine
from app.core.stress_test_engine import StressTestEngine
from app.core.viability_gate import ViabilityDecisionGate
from app.agents.specialists import SpecializedAgentsPipeline
from app.core.guardrails import ExecutionGuardrails, GuardrailViolation
from app.marketplaces.mercado_livre import MercadoLivreAdapter


class SessionPipelineContext:
    """Mantém o estado completo da sessão de análise e aprovação."""
    def __init__(self, session_id: str, intake: ProductIntakeRequest):
        self.session_id = session_id
        self.intake = intake
        self.created_at = datetime.now().isoformat()
        self.status = "IN_PROGRESS"  # IN_PROGRESS, AWAITING_HUMAN_APPROVAL, APPROVED, REJECTED, EXECUTED
        self.evidence_store = EvidenceStore(session_id=session_id)
        self.specialists_output: Dict[str, Any] = {}
        self.decision_gate_result: Optional[DecisionGateResult] = None
        self.prepared_listing: Optional[PreparedListing] = None
        self.execution_result: Optional[Dict[str, Any]] = None
        self.agent_logs: list = []

    def log(self, agent_name: str, step: str, details: str):
        self.agent_logs.append({
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": agent_name,
            "step": step,
            "details": details
        })


class MainOrchestrator:
    """
    Orquestrador Principal do Sistema Marketplace Manager AI
    """

    def __init__(self):
        self.sessions: Dict[str, SessionPipelineContext] = {}
        self.guardrails = ExecutionGuardrails()
        self.ml_adapter = MercadoLivreAdapter()

    def start_pipeline(self, intake: ProductIntakeRequest) -> SessionPipelineContext:
        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        ctx = SessionPipelineContext(session_id, intake)
        self.sessions[session_id] = ctx

        ctx.log("2. ORCHESTRATOR", "INTAKE_PARSED", f"Briefing recebido para SKU '{intake.sku}' ({intake.title_raw}).")

        # -------------------------------------------------------------
        # 1. Ingestão inicial no Evidence Store (Camada 6)
        # -------------------------------------------------------------
        ctx.evidence_store.record_evidence(
            field="cmv_unitario",
            value=intake.cost_price,
            formatted_value=f"R$ {intake.cost_price:.2f}",
            source="Briefing Lojista / ERP",
            evidence_type=EvidenceType.FATO,
            confidence=100.0,
            layer="1. INTAKE & BRIEFING"
        )
        ctx.evidence_store.record_evidence(
            field="margem_alvo_desejada",
            value=intake.target_margin,
            formatted_value=f"{intake.target_margin * 100:.1f}%",
            source="Briefing Lojista",
            evidence_type=EvidenceType.FATO,
            confidence=100.0,
            layer="1. INTAKE & BRIEFING"
        )
        ctx.evidence_store.record_evidence(
            field="aliquota_imposto",
            value=intake.tax_rate,
            formatted_value=f"{intake.tax_rate * 100:.1f}% (Simples Nacional)",
            source="Configuração Fiscal",
            evidence_type=EvidenceType.FATO,
            confidence=100.0,
            layer="1. INTAKE & BRIEFING"
        )

        ctx.log("6. EVIDENCE_STORE", "DATA_STORED", "Dados do SKU validados e persistidos com rastreabilidade.")

        # -------------------------------------------------------------
        # 2. Execução dos Agentes Especialistas Paralelos (Camada 7)
        # -------------------------------------------------------------
        ctx.log("7. SPECIALISTS", "STARTING_PARALLEL", "Disparando agentes especialistas em paralelo.")
        
        prod_intel = SpecializedAgentsPipeline.run_product_intelligence(intake, ctx.evidence_store)
        mkt_intel = SpecializedAgentsPipeline.run_market_intelligence(intake, ctx.evidence_store)
        ml_spec = SpecializedAgentsPipeline.run_marketplace_specialist(intake, ctx.evidence_store)

        ctx.specialists_output = {
            "product_intelligence": prod_intel,
            "market_intelligence": mkt_intel,
            "marketplace_specialist": ml_spec
        }
        ctx.log("7. SPECIALISTS", "COMPLETED", "Análises de produto, concorrência e conformidade ML concluídas.")

        # -------------------------------------------------------------
        # 3. Motor Financeiro Determinístico (Camada 7.4)
        # -------------------------------------------------------------
        ideal_price = FinancialEngine.calculate_ideal_selling_price(
            cost_price=intake.cost_price,
            target_margin=intake.target_margin,
            weight_kg=intake.weight_kg,
            tax_rate=intake.tax_rate,
            packaging_cost=intake.packaging_cost,
            listing_type=ml_spec["listing_type_recommended"]
        )

        ctx.evidence_store.record_evidence(
            field="preco_venda_calculado",
            value=ideal_price,
            formatted_value=f"R$ {ideal_price:.2f}",
            source="Motor Financeiro Determinístico",
            evidence_type=EvidenceType.CALCULO,
            confidence=98.0,
            notes="Calculado para atingir a margem líquida alvo considerando as regras do Mercado Livre.",
            layer="7.4 FINANCIAL ENGINE"
        )
        ctx.log("7.4 FINANCIAL_ENGINE", "PRICE_COMPUTED", f"Preço ideal calculado deterministicamente: R$ {ideal_price:.2f}.")

        # -------------------------------------------------------------
        # 4. Stress-Test Engine & Cenários (Camada 9)
        # -------------------------------------------------------------
        scenarios = StressTestEngine.generate_all_scenarios(
            base_price=ideal_price,
            cost_price=intake.cost_price,
            weight_kg=intake.weight_kg,
            tax_rate=intake.tax_rate,
            packaging_cost=intake.packaging_cost,
            listing_type=ml_spec["listing_type_recommended"],
            base_ad_spend_unit=5.0,
            estimated_monthly_demand=intake.stock_quantity
        )
        ctx.log("9. STRESS_TEST", "SCENARIOS_GENERATED", "4 cenários gerados (Conservador, Base, Agressivo, Adverso).")

        # -------------------------------------------------------------
        # 5. Viability & Decision Gate (Camada 10 & 11)
        # -------------------------------------------------------------
        decision_gate = ViabilityDecisionGate.evaluate(
            scenarios=scenarios,
            target_margin_percent=intake.target_margin * 100.0
        )
        ctx.decision_gate_result = decision_gate
        ctx.log("10. DECISION_GATE", "VIABILITY_RATED", f"Classificação de viabilidade: {decision_gate.rating_label}.")

        # -------------------------------------------------------------
        # 6. Preparação da Listagem (Camadas 12.1 a 12.6)
        # -------------------------------------------------------------
        listing = SpecializedAgentsPipeline.generate_listing(
            intake=intake,
            suggested_price=ideal_price,
            store=ctx.evidence_store
        )
        ctx.prepared_listing = listing
        ctx.log("12. LISTING_PREP", "LISTING_READY", f"Anúncio preparado: Título '{listing.title_optimized}' ({len(listing.title_optimized)} chars).")

        # -------------------------------------------------------------
        # 7. Pausa para Aprovação Humana (Camada 12.7)
        # -------------------------------------------------------------
        ctx.status = "AWAITING_HUMAN_APPROVAL"
        ctx.log("12.7 HUMAN_APPROVAL", "PAUSED_FOR_REVIEW", "Pipeline pausado no portão de segurança aguardando aprovação do operador humano.")

        return ctx

    def process_human_decision(
        self,
        session_id: str,
        action: HumanApprovalAction,
        custom_price: Optional[float] = None,
        custom_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processa a decisão humana da etapa 12.7:
        - APROVADO: Prossegue para a Camada 13 (Execução Controlada com Guardrails).
        - AJUSTAR: Recalcula com os parâmetros ajustados pelo usuário.
        - REJEITADO: Aborta a publicação com segurança.
        """
        ctx = self.sessions.get(session_id)
        if not ctx:
            raise ValueError(f"Sessão {session_id} não encontrada.")

        if action == HumanApprovalAction.REJEITADO:
            ctx.status = "REJECTED"
            ctx.log("12.7 HUMAN_APPROVAL", "REJECTED", "Anúncio rejeitado pelo operador humano. Nenhuma ação será executada.")
            return {
                "status": "REJECTED",
                "message": "Operação cancelada pelo usuário. O anúncio não será publicado."
            }

        if action == HumanApprovalAction.AJUSTAR and custom_price:
            ctx.prepared_listing.suggested_price = custom_price
            if custom_title:
                ctx.prepared_listing.title_optimized = custom_title[:60]
            
            # Recalcula cenários com o novo preço
            scenarios = StressTestEngine.generate_all_scenarios(
                base_price=custom_price,
                cost_price=ctx.intake.cost_price,
                weight_kg=ctx.intake.weight_kg,
                tax_rate=ctx.intake.tax_rate,
                packaging_cost=ctx.intake.packaging_cost,
                listing_type=ctx.prepared_listing.listing_type
            )
            ctx.decision_gate_result = ViabilityDecisionGate.evaluate(
                scenarios=scenarios,
                target_margin_percent=ctx.intake.target_margin * 100.0
            )
            ctx.log("12.7 HUMAN_APPROVAL", "ADJUSTED", f"Preço ajustado manualmente pelo usuário para R$ {custom_price:.2f}.")

        # Se aprovado, executa a camada 13 com guardrails
        ctx.status = "APPROVED"
        ctx.log("12.7 HUMAN_APPROVAL", "APPROVED", "Anúncio aprovado pelo operador humano. Encaminhando para os Guardrails de Execução.")

        # -------------------------------------------------------------
        # Camada 13: Execução Controlada & Guardrails
        # -------------------------------------------------------------
        base_scenario = next((s for s in ctx.decision_gate_result.scenarios if s.name == "Base"), None)
        margin = base_scenario.net_margin_percent if base_scenario else 15.0

        idempotency_key = f"pub_{session_id}_{ctx.prepared_listing.sku}"
        
        try:
            # 13.2 Action Validator & 13.3 Bounded Autonomy
            self.guardrails.validate_action(
                action_name="PUBLICAR_ANUNCIO",
                target_price=ctx.prepared_listing.suggested_price,
                cost_price=ctx.intake.cost_price,
                net_margin_pct=margin,
                is_human_approved=True,
                idempotency_key=idempotency_key
            )
            ctx.log("13. GUARDRAILS", "PASSED", "Ação aprovada por todos os limites de segurança e autonomia.")

            # 13.1 Execution Layer (Mercado Livre em Modo Sandbox Seguro)
            exec_res = self.ml_adapter.publish_item(ctx.prepared_listing, is_sandbox=True)
            ctx.execution_result = exec_res
            ctx.status = "EXECUTED"
            ctx.log("13.1 EXECUTION_LAYER", "PUBLISHED", f"Publicação simulada concluída com sucesso! ID: {exec_res.get('item_id')}.")

            return {
                "status": "EXECUTED",
                "message": "Anúncio validado pelos Guardrails e executado no simulador de voo do Mercado Livre com sucesso!",
                "execution_result": exec_res
            }

        except GuardrailViolation as gv:
            ctx.log("13. GUARDRAILS", "BLOCKED", f"Execução bloqueada pelo guardrail: {gv.message}")
            return {
                "status": "BLOCKED_BY_GUARDRAIL",
                "message": str(gv)
            }


# Instância singleton do orquestrador
orchestrator_instance = MainOrchestrator()
