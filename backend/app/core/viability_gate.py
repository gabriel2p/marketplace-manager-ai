"""
Viability & Decision Gate + Alternative Engine
Baseado nas Camadas 10 e 11 do diagrama:
10. VIABILITY & DECISION GATE (A: Viável, B: Viável com Condições, C: Testar em Escala Reduzida, D: Não Viável)
11. ALTERNATIVE ENGINE (Negociar custo, Ajustar produto, Novo preço, Kit / Combo, Abandonar)
"""

from typing import List
from app.models.listing import ViabilityRating, DecisionGateResult, ScenarioResult


class ViabilityDecisionGate:
    """
    Classifica a viabilidade econômica do anúncio a partir dos cenários de estresse
    e formula caminhos alternativos caso a viabilidade esteja ameaçada.
    """

    @classmethod
    def evaluate(
        cls,
        scenarios: List[ScenarioResult],
        target_margin_percent: float = 20.0
    ) -> DecisionGateResult:
        base_scenario = next((s for s in scenarios if s.name == "Base"), scenarios[0])
        adverse_scenario = next((s for s in scenarios if s.name == "Adverso"), scenarios[-1])

        base_margin = base_scenario.net_margin_percent
        adverse_margin = adverse_scenario.net_margin_percent
        adverse_profit = adverse_scenario.net_profit_unit

        reasons = []
        conditions = []
        alternatives = []

        # -------------------------------------------------------------
        # Avaliação das Regras do Decision Gate
        # -------------------------------------------------------------
        if base_margin >= target_margin_percent and adverse_profit > 0:
            rating = ViabilityRating.A_VIAVEL
            rating_label = "A - VIÁVEL (Recomendação Sólida)"
            summary = "O produto apresenta excelente robustez financeira. Mesmo sob forte estresse de mercado, a operação se mantém lucrativa."
            reasons.append(f"Margem no cenário base de {base_margin:.1f}% atinge ou supera a meta ({target_margin_percent:.1f}%).")
            reasons.append(f"Resistência a estresse comprovada: Lucro unitário positivo de R$ {adverse_profit:.2f} no pior cenário simulado.")
            reasons.append(f"ROI projetado no cenário base de {base_scenario.roi_percent:.1f}%.")

        elif base_margin >= 10.0 and adverse_profit >= -2.0:
            rating = ViabilityRating.B_VIAVEL_COM_CONDICOES
            rating_label = "B - VIÁVEL COM CONDIÇÕES (Ajustes Recomendados)"
            summary = "Operação rentável no cenário base, porém vulnerável a guerras de preço ou aumento de CAC. Exige controle de custos e Ads."
            reasons.append(f"Margem base de {base_margin:.1f}% está abaixo da meta desejada ({target_margin_percent:.1f}%), mas dentro da faixa aceitável.")
            
            if adverse_profit <= 0:
                reasons.append("Alerta: Em cenário adverso com concorrência agressiva e aumento de CAC, o lucro unitário zera.")
                conditions.append("Limitar o ACOS de campanhas de Ads em no máximo 15% para proteger a margem.")
                conditions.append("Optar por anúncio Clássico no início para economizar 5% de taxa do Mercado Livre.")
                alternatives.append("Criar Kit/Combo com 2 unidades para diluir o custo de envio e embalagem.")

        elif base_margin > 4.0:
            rating = ViabilityRating.C_TESTAR_ESCALA_REDUZIDA
            rating_label = "C - TESTAR EM ESCALA REDUZIDA (Piloto)"
            summary = "Margem unitária apertada. Recomendado validar aceitação e taxa de conversão real com lote de teste reduzido."
            reasons.append(f"Margem base de {base_margin:.1f}% oferece pouca folga para imprevistos e devoluções.")
            reasons.append("Risco de queima de margem em caso de disputas de Buy Box.")
            conditions.append("Limitar estoque inicial a 15-25 unidades para teste piloto.")
            conditions.append("Não ativar tráfego pago agressivo antes de validar a conversão orgânica.")
            alternatives.append("Renegociar custo de aquisição (CMV) com o fornecedor em pelo menos 10%.")
            alternatives.append("Adicionar acessório de baixo custo e alto valor percebido para justificar preço superior.")

        else:
            rating = ViabilityRating.D_NAO_VIAVEL
            rating_label = "D - NÃO VIÁVEL (Risco/Margem Inadequados)"
            summary = "A estrutura atual de custos e taxas inviabiliza a venda lucrativa individual deste SKU no Mercado Livre."
            reasons.append(f"Margem líquida no cenário base ({base_margin:.1f}%) é insuficiente para cobrir riscos operacionais.")
            reasons.append("Cenário adverso resulta em prejuízo financeiro direto.")
            alternatives.append("NEGOCIAR CUSTO: Reduzir o CMV com o fornecedor.")
            alternatives.append("KIT / COMBO: Vender em packs de 2 ou 3 unidades (elimina a taxa fixa de R$ 6,00 e dilui despesas).")
            alternatives.append("AJUSTAR PRODUTO: Selecionar variação com maior valor percebido ou menor peso/cubagem.")
            alternatives.append("ABANDONAR SKU: Redirecionar capital para produtos com margem líquida superior a 18%.")

        return DecisionGateResult(
            rating=rating,
            rating_label=rating_label,
            summary=summary,
            key_reasons=reasons,
            conditions=conditions,
            alternative_suggestions=alternatives,
            scenarios=scenarios
        )
