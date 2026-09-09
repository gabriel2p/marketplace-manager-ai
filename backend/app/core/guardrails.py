"""
Action Validator, Bounded Autonomy & Execution Guardrails
Baseado na Camada 13 do diagrama: EXECUÇÃO CONTROLADA
- 13.2 ACTION VALIDATOR
- 13.3 BOUNDED AUTONOMY (GUARDRAILS)
- 13.4 EXECUTION CONTROLLER
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import hashlib


class GuardrailViolation(Exception):
    def __init__(self, rule_name: str, message: str):
        self.rule_name = rule_name
        self.message = message
        super().__init__(f"GUARDRAIL VIOLATION [{rule_name}]: {message}")


class ExecutionGuardrails:
    """
    Camada de proteção e autonomia limitada:
    Impede que o sistema execute ações fora dos limites de segurança comercial.
    """

    # Limites de autonomia delimitada (13.3 do diagrama)
    MAX_PRICE_VARIATION_PCT = 3.0      # Preço ±3%
    MAX_ADS_BUDGET_INCREASE_PCT = 10.0 # Budget Ads < 10%
    MIN_NET_MARGIN_FLOOR_PCT = 6.0     # Margem mínima absoluta inviolável
    REQUIRE_HUMAN_APPROVAL = True       # Sem publicar sem aprovação humana expressa

    def __init__(self):
        self.executed_idempotency_keys: set = set()
        self.audit_log: List[Dict[str, Any]] = []

    def validate_action(
        self,
        action_name: str,
        target_price: float,
        cost_price: float,
        net_margin_pct: float,
        is_human_approved: bool,
        idempotency_key: str,
        current_price: Optional[float] = None,
        ads_daily_budget: Optional[float] = None,
        max_daily_budget_limit: float = 100.0
    ) -> Dict[str, Any]:
        """
        13.2 Action Validator & 13.3 Bounded Autonomy:
        Valida se a ação pode ser executada ou se deve ser abortada imediatamente.
        """
        # 1. Verificação de Idempotência (evitar duplicar anúncios ou cobranças)
        if idempotency_key in self.executed_idempotency_keys:
            raise GuardrailViolation(
                "IDEMPOTENCY_DUPLICATE",
                f"Ação com chave de idempotência '{idempotency_key}' já foi executada anteriormente. Prevenção contra disparo duplicado."
            )

        # 2. Trava de Aprovação Humana (12.7)
        if action_name == "PUBLICAR_ANUNCIO" and not is_human_approved:
            raise GuardrailViolation(
                "HUMAN_APPROVAL_REQUIRED",
                "Tentativa de publicação bloqueada: O anúncio não possui aprovação humana expressa (Etapa 12.7)."
            )

        # 3. Trava de Margem Mínima
        if net_margin_pct < self.MIN_NET_MARGIN_FLOOR_PCT:
            raise GuardrailViolation(
                "MINIMUM_MARGIN_BREACH",
                f"Margem líquida de {net_margin_pct:.2f}% está abaixo do piso de segurança inegociável de {self.MIN_NET_MARGIN_FLOOR_PCT}%."
            )

        # 4. Trava de Variação de Preço Autônoma (±3%)
        if current_price and current_price > 0:
            price_change_pct = abs((target_price - current_price) / current_price) * 100.0
            if price_change_pct > self.MAX_PRICE_VARIATION_PCT:
                raise GuardrailViolation(
                    "PRICE_DELTA_EXCEEDED",
                    f"Variação de preço de {price_change_pct:.1f}% excede o limite de autonomia permitida de ±{self.MAX_PRICE_VARIATION_PCT}% sem aprovação."
                )

        # 5. Trava de Limite de Orçamento de Ads
        if ads_daily_budget and ads_daily_budget > max_daily_budget_limit:
            raise GuardrailViolation(
                "ADS_BUDGET_CAP",
                f"Orçamento diário de Ads (R$ {ads_daily_budget:.2f}) excede o teto diário autorizado de R$ {max_daily_budget_limit:.2f}."
            )

        # Registro no log de auditoria imutável (Transversal: Logs & Auditoria)
        audit_entry = {
            "idempotency_key": idempotency_key,
            "action": action_name,
            "target_price": target_price,
            "net_margin_pct": net_margin_pct,
            "timestamp": datetime.now().isoformat(),
            "status": "APPROVED_BY_GUARDRAILS"
        }
        self.audit_log.append(audit_entry)
        self.executed_idempotency_keys.add(idempotency_key)

        return {
            "status": "SUCCESS",
            "message": "Ação validada com sucesso por todos os guardrails de segurança.",
            "audit_entry": audit_entry
        }
