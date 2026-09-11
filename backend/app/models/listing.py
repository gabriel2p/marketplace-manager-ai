"""
Listing, Scenarios & Decision Models
Baseado nas Camadas 9 (Stress-Test), 10 (Decision Gate), 12 (Execução Preparada) e 13 (Execução Controlada)
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ViabilityRating(str, Enum):
    A_VIAVEL = "A_VIAVEL"                           # Recomendação sólida
    B_VIAVEL_COM_CONDICOES = "B_VIAVEL_COM_CONDICOES" # Dependências ou ajustes necessários
    C_TESTAR_ESCALA_REDUZIDA = "C_TESTAR_ESCALA_REDUZIDA" # Recomendação piloto
    D_NAO_VIAVEL = "D_NAO_VIAVEL"                   # Risco/margem inadequados


class ScenarioResult(BaseModel):
    name: str = Field(description="Nome do cenário: Conservador, Base, Agressivo ou Adverso")
    description: str
    selling_price: float = Field(description="Preço de venda simulado")
    cmv: float
    marketplace_fee: float
    shipping_cost: float
    tax_amount: float
    packaging_cost: float
    estimated_ad_cost_per_unit: float
    net_profit_unit: float = Field(description="Lucro líquido unitário em R$")
    net_margin_percent: float = Field(description="Margem líquida percentual")
    roi_percent: float = Field(description="Retorno sobre investimento (%)")
    projected_monthly_units: int = Field(description="Volume projetado de vendas/mês")
    projected_monthly_revenue: float
    projected_monthly_profit: float
    break_even_units: int = Field(description="Ponto de equilíbrio em unidades")
    stress_factors: Dict[str, str] = Field(default_factory=dict, description="Fatores de estresse aplicados")


class PhotoScriptItem(BaseModel):
    order: int
    photo_type: str  # ex: "Foto 1 (Principal)", "Foto 2 (Ângulos e Acabamento)", etc.
    description: str
    requirement: str
    badge: str


class PreparedListing(BaseModel):
    # 12.2 Listing Intelligence
    sku: str
    marketplace: str = "mercadolivre"
    title_optimized: str = Field(description="Título otimizado para SEO com até 60 caracteres no ML")
    listing_type: str = "gold_special"  # Clássico ou Premium (gold_pro)
    logistics_type: str = "mercado_envios"
    is_full: bool = False
    suggested_price: float
    min_price_floor: float
    max_price_ceiling: float
    
    # Atributos e Conteúdo
    category_id: str
    category_name: str
    attributes: Dict[str, str] = Field(default_factory=dict)
    description_formatted: str
    faq_items: List[Dict[str, str]] = Field(default_factory=list)
    key_selling_points: List[str] = Field(default_factory=list)
    
    # 12.3 Creative & Visual Strategy
    photo_scripts: List[PhotoScriptItem] = Field(default_factory=list)
    
    # 12.4 Ads & Growth Strategy
    target_acos: float = 0.15
    target_roas: float = 6.67
    daily_ads_budget: float = 30.0
    recommended_keywords: List[str] = Field(default_factory=list)
    negative_keywords: List[str] = Field(default_factory=list)
    
    # 12.6 Policy & Quality Gate
    policy_checks: Dict[str, bool] = Field(default_factory=dict)
    ready_for_review: bool = True


class DecisionGateResult(BaseModel):
    rating: ViabilityRating
    rating_label: str
    summary: str
    key_reasons: List[str]
    conditions: List[str] = Field(default_factory=list)
    alternative_suggestions: List[str] = Field(default_factory=list)
    scenarios: List[ScenarioResult]


class HumanApprovalAction(str, Enum):
    APROVADO = "APROVADO"
    AJUSTAR = "AJUSTAR"
    REJEITADO = "REJEITADO"


class HumanApprovalRequest(BaseModel):
    session_id: str
    action: HumanApprovalAction
    custom_price: Optional[float] = None
    custom_title: Optional[str] = None
    custom_notes: Optional[str] = None
