"""
Intake & Briefing Models
Baseado na Camada 1 (Intake / Briefing) e Camada 3 (Requirement Engine)
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ProductIntakeRequest(BaseModel):
    # Identificação básica
    sku: str = Field(description="Código SKU interno ou identificador do produto")
    title_raw: str = Field(description="Título preliminar ou nome comercial do produto")
    brand: Optional[str] = Field(default="Genérica", description="Marca do produto")
    category_hint: str = Field(description="Categoria sugerida (ex: Áudio, Casa & Cozinha, Acessórios)")
    
    # Custos e Margem Alvo (Camada 1 do diagrama)
    cost_price: float = Field(gt=0, description="Custo da mercadoria vendida (CMV unitário em R$)")
    target_margin: float = Field(default=0.20, ge=0.01, le=0.80, description="Margem líquida desejada (ex: 0.20 = 20%)")
    tax_rate: float = Field(default=0.06, ge=0.0, le=0.30, description="Alíquota de impostos (ex: 0.06 para 6% no Simples Nacional)")
    packaging_cost: float = Field(default=3.00, ge=0.0, description="Custo unitário de embalagem e etiquetagem (R$)")
    
    # Estoque e Logística
    stock_quantity: int = Field(default=50, ge=1, description="Quantidade disponível em estoque")
    weight_kg: float = Field(default=0.35, gt=0, description="Peso bruto do pacote em kg")
    dimensions_cm: dict = Field(
        default_factory=lambda: {"height": 10, "width": 15, "length": 20},
        description="Dimensões da embalagem (altura, largura, comprimento em cm)"
    )
    
    # Objetivos e Estratégia
    objective: str = Field(
        default="EQUILIBRIO",
        description="Objetivo principal: 'LUCRO_MAXIMO', 'VOLUME_CRESCIMENTO' ou 'EQUILIBRIO'"
    )
    ad_budget_daily: float = Field(default=30.0, ge=0.0, description="Orçamento diário para anúncios (R$)")
    marketplaces: List[str] = Field(default=["mercadolivre"], description="Marketplaces de destino")
    
    # Detalhes e Diferenciais informados pelo usuário
    key_features: List[str] = Field(default_factory=list, description="Lista de diferenciais informados pelo lojista")
    warranty_days: int = Field(default=90, description="Garantia legal ou do fabricante em dias")
