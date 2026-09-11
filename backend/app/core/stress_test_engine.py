"""
Scenario & Stress-Test Engine
Baseado na Camada 9 do diagrama: SCENARIO & STRESS-TEST ENGINE
Gera os 4 cenários: Conservador, Base, Agressivo e Adverso (com testes de sensibilidade)
"""

from decimal import Decimal
from typing import List
from app.core.financial_engine import FinancialEngine
from app.models.listing import ScenarioResult


class StressTestEngine:
    """
    Executa testes de estresse e modelagem de cenários econômicos com precisão determinística.
    Testes suportados: preço -10%, custo +10%, CAC +30%, demanda -30%, devoluções maiores.
    """

    @classmethod
    def generate_all_scenarios(
        cls,
        base_price: float,
        cost_price: float,
        weight_kg: float = 0.35,
        tax_rate: float = 0.06,
        packaging_cost: float = 3.00,
        listing_type: str = "gold_special",
        base_ad_spend_unit: float = 5.00,
        estimated_monthly_demand: int = 80,
        reputation: str = "green",
        is_full: bool = False
    ) -> List[ScenarioResult]:
        scenarios = []

        # ==========================================
        # 1. CENÁRIO CONSERVADOR
        # "Segurança e margem máxima"
        # Preço +8%, Ads menor (-40%), Volume menor (-25%)
        # ==========================================
        p_cons = round(base_price * 1.08, 2)
        ads_cons = round(base_ad_spend_unit * 0.6, 2)
        vol_cons = max(int(estimated_monthly_demand * 0.75), 1)
        econ_cons = FinancialEngine.compute_unit_economics(
            selling_price=p_cons,
            cost_price=cost_price,
            weight_kg=weight_kg,
            tax_rate=tax_rate,
            packaging_cost=packaging_cost,
            listing_type=listing_type,
            ad_spend_per_unit=ads_cons,
            reputation=reputation,
            is_full=is_full
        )
        rev_cons = round(p_cons * vol_cons, 2)
        profit_cons = round(econ_cons["net_profit"] * vol_cons, 2)
        scenarios.append(ScenarioResult(
            name="Conservador",
            description="Prioriza margem máxima por unidade e segurança financeira, com menor dependência de Ads.",
            selling_price=p_cons,
            cmv=econ_cons["cmv"],
            marketplace_fee=econ_cons["marketplace_fee"],
            shipping_cost=econ_cons["shipping_cost"],
            tax_amount=econ_cons["tax_amount"],
            packaging_cost=econ_cons["packaging_cost"],
            estimated_ad_cost_per_unit=ads_cons,
            net_profit_unit=econ_cons["net_profit"],
            net_margin_percent=econ_cons["net_margin_percent"],
            roi_percent=econ_cons["roi_percent"],
            projected_monthly_units=vol_cons,
            projected_monthly_revenue=rev_cons,
            projected_monthly_profit=profit_cons,
            break_even_units=max(int(100 / max(econ_cons["net_profit"], 1)), 1),
            stress_factors={
                "preço": "+8% acima do preço base",
                "ads": "Apenas 60% do CAC padrão",
                "foco": "Garantia de margem unitária alta"
            }
        ))

        # ==========================================
        # 2. CENÁRIO BASE
        # "Equilíbrio entre margem e volume"
        # Preço nominal ideal, Ads padrão, Demanda esperada
        # ==========================================
        p_base = round(base_price, 2)
        ads_base = round(base_ad_spend_unit, 2)
        vol_base = estimated_monthly_demand
        econ_base = FinancialEngine.compute_unit_economics(
            selling_price=p_base,
            cost_price=cost_price,
            weight_kg=weight_kg,
            tax_rate=tax_rate,
            packaging_cost=packaging_cost,
            listing_type=listing_type,
            ad_spend_per_unit=ads_base,
            reputation=reputation,
            is_full=is_full
        )
        rev_base = round(p_base * vol_base, 2)
        profit_base = round(econ_base["net_profit"] * vol_base, 2)
        scenarios.append(ScenarioResult(
            name="Base",
            description="Cenário de equilíbrio com precificação competitiva, tráfego regular e margem saudável.",
            selling_price=p_base,
            cmv=econ_base["cmv"],
            marketplace_fee=econ_base["marketplace_fee"],
            shipping_cost=econ_base["shipping_cost"],
            tax_amount=econ_base["tax_amount"],
            packaging_cost=econ_base["packaging_cost"],
            estimated_ad_cost_per_unit=ads_base,
            net_profit_unit=econ_base["net_profit"],
            net_margin_percent=econ_base["net_margin_percent"],
            roi_percent=econ_base["roi_percent"],
            projected_monthly_units=vol_base,
            projected_monthly_revenue=rev_base,
            projected_monthly_profit=profit_base,
            break_even_units=max(int(100 / max(econ_base["net_profit"], 1)), 1),
            stress_factors={
                "preço": "Preço ideal de mercado",
                "ads": "Orçamento de tráfego equilibrado",
                "foco": "Sustentabilidade operacional"
            }
        ))

        # ==========================================
        # 3. CENÁRIO AGRESSIVO
        # "Máximo volume e crescimento"
        # Preço -7% (penetração/ranking), Ads +40%, Volume +60%
        # ==========================================
        p_agr = round(base_price * 0.93, 2)
        ads_agr = round(base_ad_spend_unit * 1.4, 2)
        vol_agr = int(estimated_monthly_demand * 1.6)
        econ_agr = FinancialEngine.compute_unit_economics(
            selling_price=p_agr,
            cost_price=cost_price,
            weight_kg=weight_kg,
            tax_rate=tax_rate,
            packaging_cost=packaging_cost,
            listing_type=listing_type,
            ad_spend_per_unit=ads_agr,
            reputation=reputation,
            is_full=is_full
        )
        rev_agr = round(p_agr * vol_agr, 2)
        profit_agr = round(econ_agr["net_profit"] * vol_agr, 2)
        scenarios.append(ScenarioResult(
            name="Agressivo",
            description="Estratégia de escala e ganho de medalha MercadoLíder. Foco em volume acelerado.",
            selling_price=p_agr,
            cmv=econ_agr["cmv"],
            marketplace_fee=econ_agr["marketplace_fee"],
            shipping_cost=econ_agr["shipping_cost"],
            tax_amount=econ_agr["tax_amount"],
            packaging_cost=econ_agr["packaging_cost"],
            estimated_ad_cost_per_unit=ads_agr,
            net_profit_unit=econ_agr["net_profit"],
            net_margin_percent=econ_agr["net_margin_percent"],
            roi_percent=econ_agr["roi_percent"],
            projected_monthly_units=vol_agr,
            projected_monthly_revenue=rev_agr,
            projected_monthly_profit=profit_agr,
            break_even_units=max(int(100 / max(econ_agr["net_profit"], 1)), 1),
            stress_factors={
                "preço": "-7% desconto de penetração",
                "ads": "+40% investimento em Product Ads",
                "foco": "Velocidade de vendas e Buy Box"
            }
        ))

        # ==========================================
        # 4. CENÁRIO ADVERSO (STRESS-TEST)
        # "Piores cenários e riscos"
        # Preço -10%, Custo +10%, CAC +30%, Demanda -30%, Devoluções 5%
        # ==========================================
        p_adv = round(base_price * 0.90, 2)
        cost_adv = round(cost_price * 1.10, 2)
        ads_adv = round(base_ad_spend_unit * 1.30, 2)
        vol_adv = max(int(estimated_monthly_demand * 0.70), 1)
        
        econ_adv = FinancialEngine.compute_unit_economics(
            selling_price=p_adv,
            cost_price=cost_adv,
            weight_kg=weight_kg,
            tax_rate=tax_rate,
            packaging_cost=packaging_cost,
            listing_type=listing_type,
            ad_spend_per_unit=ads_adv,
            reputation=reputation,
            is_full=is_full
        )
        
        # Custo de devolução estimado de 5% sobre as vendas
        return_impact_per_unit = round(p_adv * 0.05, 2)
        stressed_net_profit = round(econ_adv["net_profit"] - return_impact_per_unit, 2)
        stressed_net_margin = round((stressed_net_profit / p_adv) * 100, 2) if p_adv > 0 else 0.0

        rev_adv = round(p_adv * vol_adv, 2)
        profit_adv = round(stressed_net_profit * vol_adv, 2)
        scenarios.append(ScenarioResult(
            name="Adverso",
            description="Simulação extrema de estresse: concorrência agressiva, aumento de CMV e custos de leilão de Ads.",
            selling_price=p_adv,
            cmv=cost_adv,
            marketplace_fee=econ_adv["marketplace_fee"],
            shipping_cost=econ_adv["shipping_cost"],
            tax_amount=econ_adv["tax_amount"],
            packaging_cost=econ_adv["packaging_cost"],
            estimated_ad_cost_per_unit=ads_adv,
            net_profit_unit=stressed_net_profit,
            net_margin_percent=stressed_net_margin,
            roi_percent=round((stressed_net_profit / cost_adv) * 100, 2) if cost_adv > 0 else 0.0,
            projected_monthly_units=vol_adv,
            projected_monthly_revenue=rev_adv,
            projected_monthly_profit=profit_adv,
            break_even_units=999 if stressed_net_profit <= 0 else max(int(100 / stressed_net_profit), 1),
            stress_factors={
                "preço": "-10% forçado por guerra de preços",
                "cmv": "+10% inflação de matéria-prima/fornecedor",
                "cac": "+30% leilão de Ads mais concorrido",
                "demanda": "-30% retração de mercado",
                "devoluções": "5% taxa de trocas/arrependimento"
            }
        ))

        return scenarios
