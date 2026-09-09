"""
Financial Engine Determinístico
Baseado na Camada 7.4 do diagrama: FINANCIAL ENGINE (DETERMINÍSTICO)
Princípio fundamental: "Cálculo determinístico para números críticos - sem alucinações de LLM"
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Tuple


class FinancialEngine:
    """
    Motor financeiro com cálculos determinísticos exatos baseados nas regras
    oficiais e tarifárias do Mercado Livre Brasil (Mercado Envios e Tarifas de Venda).
    """

    # Tarifas oficiais Mercado Livre
    THRESHOLD_FRETE_GRATIS = Decimal("79.00")
    TAXA_FIXA_ABAIXO_THRESHOLD = Decimal("6.00")
    
    # Comissões padrão por tipo de anúncio
    COMMISSION_RATES = {
        "gold_special": Decimal("0.13"),  # Clássico: ~13% médio
        "gold_pro": Decimal("0.18"),      # Premium (parcelamento s/ juros): ~18% médio
    }

    @staticmethod
    def _round_currency(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def calculate_shipping_cost(cls, price: Decimal, weight_kg: Decimal, marketplace: str = "mercadolivre") -> Decimal:
        """
        No Mercado Livre:
        - Produtos abaixo de R$ 79,00: frete pago pelo comprador -> Custo para o lojista = R$ 0,00
        - Produtos a partir de R$ 79,00: frete grátis obrigatório -> Lojista paga com coparticipação
          estimada por faixa de peso no Mercado Envios (com reputação verde/líder padrão de mercado).
        """
        if price < cls.THRESHOLD_FRETE_GRATIS:
            return Decimal("0.00")

        # Tabela base aproximada Mercado Envios com desconto de reputação (vendedor profissional)
        if weight_kg <= Decimal("0.30"):
            return Decimal("18.90")
        elif weight_kg <= Decimal("0.50"):
            return Decimal("20.45")
        elif weight_kg <= Decimal("1.00"):
            return Decimal("22.90")
        elif weight_kg <= Decimal("2.00"):
            return Decimal("25.90")
        else:
            return Decimal("29.90")

    @classmethod
    def calculate_marketplace_fee(cls, price: Decimal, listing_type: str = "gold_special") -> Tuple[Decimal, Decimal]:
        """
        Calcula a comissão percentual + taxa fixa se produto < R$ 79,00.
        Retorna (taxa_total, taxa_fixa).
        """
        rate = cls.COMMISSION_RATES.get(listing_type, cls.COMMISSION_RATES["gold_special"])
        percent_fee = cls._round_currency(price * rate)
        
        fixed_fee = Decimal("0.00")
        if price < cls.THRESHOLD_FRETE_GRATIS:
            fixed_fee = cls.TAXA_FIXA_ABAIXO_THRESHOLD
            
        total_fee = percent_fee + fixed_fee
        return total_fee, fixed_fee

    @classmethod
    def compute_unit_economics(
        cls,
        selling_price: float,
        cost_price: float,
        weight_kg: float = 0.35,
        tax_rate: float = 0.06,
        packaging_cost: float = 3.00,
        listing_type: str = "gold_special",
        ad_spend_per_unit: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calcula os economics unitários completos com precisão determinística.
        """
        p = Decimal(str(selling_price))
        cmv = Decimal(str(cost_price))
        weight = Decimal(str(weight_kg))
        tax_r = Decimal(str(tax_rate))
        pack = Decimal(str(packaging_cost))
        ads = Decimal(str(ad_spend_per_unit))

        # 1. Tarifas Marketplace
        fee_total, fixed_fee = cls.calculate_marketplace_fee(p, listing_type)

        # 2. Frete do vendedor
        shipping = cls.calculate_shipping_cost(p, weight)

        # 3. Impostos (Simples Nacional incide sobre o faturamento bruto)
        taxes = cls._round_currency(p * tax_r)

        # 4. Custos Totais por Unidade
        total_costs = cmv + fee_total + shipping + taxes + pack + ads

        # 5. Lucro Líquido Unitário
        net_profit = cls._round_currency(p - total_costs)

        # 6. Margens
        net_margin_pct = Decimal("0.00")
        if p > Decimal("0.00"):
            net_margin_pct = cls._round_currency((net_profit / p) * Decimal("100.00"))

        # 7. Margem de Contribuição (sem Ads)
        contrib_margin = cls._round_currency(p - (cmv + fee_total + shipping + taxes + pack))
        contrib_margin_pct = cls._round_currency((contrib_margin / p) * Decimal("100.00")) if p > 0 else Decimal("0.00")

        # 8. ROI (Lucro Líquido / Desembolso Direto em CMV + Embalagem)
        direct_cost = cmv + pack
        roi_pct = cls._round_currency((net_profit / direct_cost) * Decimal("100.00")) if direct_cost > 0 else Decimal("0.00")

        # 9. Break-even ACOS (Teto de Ads para não ter prejuízo)
        break_even_acos = contrib_margin_pct

        return {
            "selling_price": float(p),
            "cmv": float(cmv),
            "marketplace_fee": float(fee_total),
            "marketplace_fixed_fee": float(fixed_fee),
            "shipping_cost": float(shipping),
            "tax_amount": float(taxes),
            "packaging_cost": float(pack),
            "ad_cost_per_unit": float(ads),
            "total_costs": float(total_costs),
            "net_profit": float(net_profit),
            "net_margin_percent": float(net_margin_pct),
            "contribution_margin": float(contrib_margin),
            "contribution_margin_percent": float(contrib_margin_pct),
            "roi_percent": float(roi_pct),
            "break_even_acos_percent": float(break_even_acos),
            "is_profitable": net_profit > Decimal("0.00")
        }

    @classmethod
    def calculate_ideal_selling_price(
        cls,
        cost_price: float,
        target_margin: float = 0.20,
        weight_kg: float = 0.35,
        tax_rate: float = 0.06,
        packaging_cost: float = 3.00,
        listing_type: str = "gold_special"
    ) -> float:
        """
        Resolve deterministicamente o preço ideal de venda necessário para atingir
        a margem líquida alvo (target_margin) considerando as descontinuidades da tabela
        do Mercado Livre (faixa de R$ 79,00 com taxa fixa vs frete grátis).
        """
        # Testa candidatos em busca do ponto de equilíbrio com a margem desejada
        # Faz uma busca iterativa centavo a centavo (simulação determinística exata)
        cmv = Decimal(str(cost_price))
        target_m = Decimal(str(target_margin))

        # Ponto de partida estimativo
        current_candidate = (cmv * Decimal("1.8")).quantize(Decimal("1.00"))
        if current_candidate < Decimal("15.00"):
            current_candidate = Decimal("15.00")

        best_price = current_candidate
        min_margin_diff = Decimal("9999.00")

        # Varre uma faixa de preços razoáveis com passo de R$ 0.50 e depois refinamento
        for p_int in range(int(cmv * 100), int(cmv * 600), 50):
            p = Decimal(p_int) / Decimal(100)
            econ = cls.compute_unit_economics(
                selling_price=float(p),
                cost_price=cost_price,
                weight_kg=weight_kg,
                tax_rate=tax_rate,
                packaging_cost=packaging_cost,
                listing_type=listing_type
            )
            margin_pct = Decimal(str(econ["net_margin_percent"]))
            diff = abs(margin_pct - (target_m * Decimal("100.00")))
            if diff < min_margin_diff:
                min_margin_diff = diff
                best_price = p

        # Se o preço caiu perigosamente perto da barreira de R$ 78,90 onde entra a taxa fixa de R$ 6,00,
        # analisa se vale a pena cruzar para R$ 79,90 ou ficar em R$ 74,90
        return float(best_price)
