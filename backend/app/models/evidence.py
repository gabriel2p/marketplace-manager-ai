"""
Evidence Store - Modelos de Dados e Rastreabilidade
Baseado na Camada 6 do diagrama: Data Quality & Goal Defense
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class EvidenceType(str, Enum):
    FATO = "FATO"               # Dados brutos verificados (ex: preço de custo fornecido, taxas oficiais da tabela)
    CALCULO = "CALCULO"         # Derivação matemática determinística (ex: margem líquida, break-even)
    ESTIMATIVA = "ESTIMATIVA"   # Projeção baseada em histórico de mercado (ex: volume mensal de vendas)
    INFERENCIA = "INFERENCIA"   # Dedução de modelo de IA (ex: público-alvo, pontos de diferenciação)


class QualityStatus(str, Enum):
    ACEITO = "ACEITO"
    REJEITADO = "REJEITADO"
    PENDENTE = "PENDENTE"
    ALERTA = "ALERTA"


class EvidenceItem(BaseModel):
    id: str = Field(description="Identificador único da evidência")
    field: str = Field(description="Nome do campo ou métrica (ex: 'cmv', 'taxa_ml', 'demanda_mensal')")
    value: Any = Field(description="Valor registrado")
    formatted_value: Optional[str] = Field(default=None, description="Valor formatado para exibição visual")
    source: str = Field(description="Origem do dado (ex: 'Briefing Usuário', 'Tabela Oficial ML', 'Motor Financeiro')")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="Data e hora do registro")
    evidence_type: EvidenceType = Field(description="Classificação metodológica do dado")
    confidence: float = Field(ge=0.0, le=100.0, description="Nível de confiança de 0 a 100%")
    quality_status: QualityStatus = Field(default=QualityStatus.ACEITO, description="Status de qualidade após validação")
    validation_notes: Optional[str] = Field(default=None, description="Observações de consistência ou conflitos")
    source_layer: str = Field(default="6. DATA QUALITY & GOAL DEFENSE")


class EvidenceStoreSnapshot(BaseModel):
    session_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: int = 1
    items: List[EvidenceItem] = Field(default_factory=list)
    completeness_score: float = Field(default=100.0, description="Índice de completude dos dados obrigatórios (%)")
    freshness_hours: float = Field(default=0.0, description="Idade máxima dos dados em horas")
    has_conflicts: bool = False
    conflict_details: List[str] = Field(default_factory=list)
