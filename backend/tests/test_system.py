"""
Testes Unitários e de Confiabilidade
Valida o Financial Engine Determinístico e os Guardrails de Execução
"""

import unittest
from decimal import Decimal
from app.core.financial_engine import FinancialEngine
from app.core.stress_test_engine import StressTestEngine
from app.core.viability_gate import ViabilityDecisionGate
from app.core.guardrails import ExecutionGuardrails, GuardrailViolation
from app.agents.orchestrator import MainOrchestrator
from app.models.intake import ProductIntakeRequest
from app.models.listing import HumanApprovalAction


class TestMarketplaceManagerAI(unittest.TestCase):

    def test_financial_engine_below_threshold(self):
        """Produtos abaixo de R$ 79,00 devem ter taxa fixa de R$ 6,00 e frete R$ 0,00 para o vendedor."""
        econ = FinancialEngine.compute_unit_economics(
            selling_price=50.00,
            cost_price=20.00,
            weight_kg=0.30,
            tax_rate=0.06,
            packaging_cost=2.00,
            listing_type="gold_special"
        )
        # Comissão 13% de 50.00 = 6.50 + taxa fixa 6.00 = 12.50
        self.assertEqual(econ["marketplace_fee"], 12.50)
        self.assertEqual(econ["shipping_cost"], 0.00)
        self.assertEqual(econ["tax_amount"], 3.00)
        # Lucro líquido: 50.00 - (20.00 + 12.50 + 0 + 3.00 + 2.00) = 12.50
        self.assertEqual(econ["net_profit"], 12.50)
        self.assertEqual(econ["net_margin_percent"], 25.00)

    def test_financial_engine_above_threshold(self):
        """Produtos a partir de R$ 79,00 devem ter taxa fixa R$ 0,00 e frete grátis custeado pelo vendedor."""
        econ = FinancialEngine.compute_unit_economics(
            selling_price=120.00,
            cost_price=40.00,
            weight_kg=0.35,
            tax_rate=0.06,
            packaging_cost=3.00,
            listing_type="gold_special"
        )
        self.assertEqual(econ["marketplace_fixed_fee"], 0.00)
        self.assertGreater(econ["shipping_cost"], 0.00)
        self.assertTrue(econ["is_profitable"])

    def test_stress_test_generates_4_scenarios(self):
        scenarios = StressTestEngine.generate_all_scenarios(
            base_price=99.90,
            cost_price=35.00,
            weight_kg=0.40
        )
        names = [s.name for s in scenarios]
        self.assertListEqual(names, ["Conservador", "Base", "Agressivo", "Adverso"])

    def test_guardrails_prevent_unapproved_publishing(self):
        """A publicação DEVE ser bloqueada se não houver aprovação humana expressa (12.7)."""
        guard = ExecutionGuardrails()
        with self.assertRaises(GuardrailViolation):
            guard.validate_action(
                action_name="PUBLICAR_ANUNCIO",
                target_price=99.90,
                cost_price=35.00,
                net_margin_pct=18.0,
                is_human_approved=False,  # NÃO aprovado
                idempotency_key="key_1"
            )

    def test_guardrails_prevent_margin_below_floor(self):
        """A publicação DEVE ser bloqueada se a margem for menor que o piso inegociável."""
        guard = ExecutionGuardrails()
        with self.assertRaises(GuardrailViolation):
            guard.validate_action(
                action_name="PUBLICAR_ANUNCIO",
                target_price=40.00,
                cost_price=38.00,
                net_margin_pct=2.0,  # Abaixo do piso de 6%
                is_human_approved=True,
                idempotency_key="key_2"
            )

    def test_end_to_end_orchestrator_pipeline(self):
        """Testa o ciclo de vida completo do orquestrador."""
        orchestrator = MainOrchestrator()
        req = ProductIntakeRequest(
            sku="TWS-PRO-01",
            title_raw="Fone de Ouvido Bluetooth Sem Fio TWS",
            brand="SoundTech",
            category_hint="Áudio & Fones de Ouvido",
            cost_price=32.00,
            stock_quantity=80,
            weight_kg=0.25,
            target_margin=0.22,
            key_features=["Cancelamento de Ruído Ativo (ANC)", "Bateria de 28 horas com case", "Bluetooth 5.3"]
        )
        # Inicia pipeline
        ctx = orchestrator.start_pipeline(req)
        self.assertEqual(ctx.status, "AWAITING_HUMAN_APPROVAL")
        self.assertIsNotNone(ctx.prepared_listing)
        self.assertLessEqual(len(ctx.prepared_listing.title_optimized), 60)
        self.assertIsNotNone(ctx.decision_gate_result)

        # Simula Aprovação Humana (12.7)
        res = orchestrator.process_human_decision(
            session_id=ctx.session_id,
            action=HumanApprovalAction.APROVADO
        )
        self.assertEqual(res["status"], "EXECUTED")
        self.assertEqual(ctx.status, "EXECUTED")


if __name__ == "__main__":
    unittest.main()
