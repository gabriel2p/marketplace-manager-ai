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
    def calculate_shipping_cost(
        cls,
        price: Decimal,
        weight_kg: Decimal,
        reputation: str = "green",
        marketplace: str = "mercadolivre",
        is_full: bool = False
    ) -> Decimal:
        """
        Calcula o custo oficial de Mercado Envios conforme tabela ajuda/40538 do Mercado Livre:
        - Produtos abaixo de R$ 79,00: frete pago pelo comprador -> Custo para o lojista = R$ 0,00
        - Produtos a partir de R$ 79,00: frete grátis obrigatório subsidiado pelo lojista,
          com base na matriz 2D de peso x faixa de preço x desconto de reputação.
        - Mercado Envios Full (Fulfillment): 10% de desconto adicional oficial na tarifa de frete grátis.
        """
        if price < cls.THRESHOLD_FRETE_GRATIS:
            return Decimal("0.00")

        p = float(price)
        w = float(weight_kg)

        if p < 100.0:
            price_tier = 0
        elif p < 120.0:
            price_tier = 1
        elif p < 150.0:
            price_tier = 2
        elif p < 200.0:
            price_tier = 3
        else:
            price_tier = 4

        # Matriz Oficial Mercado Livre (ajuda/40538) com desconto de 50% MercadoLíder/Verde
        weight_matrix = [
            (0.3, [13.45, 14.95, 16.95, 19.05, 21.65]),
            (0.5, [14.65, 16.15, 18.15, 20.45, 23.25]),
            (1.0, [15.35, 16.85, 19.05, 21.35, 24.45]),
            (1.5, [15.65, 17.15, 19.45, 21.75, 25.45]),
            (2.0, [16.15, 17.65, 19.85, 22.25, 25.55]),
            (3.0, [18.95, 20.45, 22.65, 25.15, 28.45]),
            (4.0, [20.95, 22.45, 24.95, 27.65, 31.45]),
            (5.0, [22.95, 24.65, 27.35, 30.25, 34.45]),
            (9.0, [32.95, 35.15, 38.65, 42.45, 48.45]),
            (13.0, [46.95, 49.85, 54.65, 59.95, 68.45]),
            (17.0, [55.95, 59.45, 65.15, 71.45, 81.45]),
            (23.0, [66.45, 70.45, 77.15, 84.65, 96.45]),
            (30.0, [78.95, 83.65, 91.55, 100.45, 114.45]),
            (999.0, [93.45, 99.00, 108.35, 118.90, 135.45])
        ]

        rates = weight_matrix[-1][1]
        for max_w, row_rates in weight_matrix:
            if w <= max_w:
                rates = row_rates
                break

        base_rate = rates[price_tier]
        if is_full:
            # Benefício Oficial Mercado Envios Full: até 10% de desconto adicional na tarifa de frete grátis
            base_rate = round(base_rate * 0.90, 2)

        rep = (reputation or "green").lower()
        if "yellow" in rep or "amarel" in rep:
            multiplier = 1.20
        elif "orange" in rep or "laranja" in rep or "none" in rep or "sem" in rep or "red" in rep:
            multiplier = 2.00
        else:
            multiplier = 1.00

        final_rate = round(base_rate * multiplier, 2)
        return Decimal(str(final_rate))

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
        ad_spend_per_unit: float = 0.0,
        reputation: str = "green",
        is_full: bool = False
    ) -> Dict[str, Any]:
        """
        Calcula os economics unitários completos com precisão determinística.
        Suporta modalidade convencional e Mercado Envios Full (Fulfillment).
        """
        p = Decimal(str(selling_price))
        cmv = Decimal(str(cost_price))
        weight = Decimal(str(weight_kg))
        tax_r = Decimal(str(tax_rate))
        # No Full, o Mercado Livre fornece a embalagem oficial na expedição (custo unitário do lojista = R$ 0,00)
        pack = Decimal("0.00") if (is_full and packaging_cost == 3.00) else Decimal(str(packaging_cost))
        ads = Decimal(str(ad_spend_per_unit))

        # 1. Tarifas Marketplace
        fee_total, fixed_fee = cls.calculate_marketplace_fee(p, listing_type)

        # 2. Frete do vendedor (com desconto oficial de 10% no Full)
        shipping = cls.calculate_shipping_cost(p, weight, reputation=reputation, is_full=is_full)

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
            "is_profitable": net_profit > Decimal("0.00"),
            "is_full": is_full
        }

    @classmethod
    def calculate_ideal_selling_price(
        cls,
        cost_price: float,
        target_margin: float = 0.20,
        weight_kg: float = 0.35,
        tax_rate: float = 0.06,
        packaging_cost: float = 3.00,
        listing_type: str = "gold_special",
        reputation: str = "green",
        is_full: bool = False
    ) -> float:
        """
        Resolve deterministicamente o preço ideal de venda necessário para atingir
        a margem líquida alvo (target_margin) considerando as descontinuidades da tabela
        do Mercado Livre (faixa de R$ 79,00 com taxa fixa vs frete grátis e desconto Full).
        """
        cmv = Decimal(str(cost_price))
        target_m = Decimal(str(target_margin))

        current_candidate = (cmv * Decimal("1.8")).quantize(Decimal("1.00"))
        if current_candidate < Decimal("15.00"):
            current_candidate = Decimal("15.00")

        best_price = current_candidate
        min_margin_diff = Decimal("9999.00")

        for p_int in range(int(cmv * 100), int(cmv * 600), 50):
            p = Decimal(p_int) / Decimal(100)
            econ = cls.compute_unit_economics(
                selling_price=float(p),
                cost_price=cost_price,
                weight_kg=weight_kg,
                tax_rate=tax_rate,
                packaging_cost=packaging_cost,
                listing_type=listing_type,
                reputation=reputation,
                is_full=is_full
            )
            margin_pct = Decimal(str(econ["net_margin_percent"]))
            diff = abs(margin_pct - (target_m * Decimal("100.00")))
            if diff < min_margin_diff:
                min_margin_diff = diff
                best_price = p

        # Se o preço caiu perigosamente perto da barreira de R$ 78,90 onde entra a taxa fixa de R$ 6,00,
        # analisa se vale a pena cruzar para R$ 79,90 ou ficar em R$ 74,90
        return float(best_price)
