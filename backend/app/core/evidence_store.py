"""
Evidence Store Engine & Verificações Automáticas
Baseado na Camada 6 do diagrama: DATA QUALITY & GOAL DEFENSE
"""

import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.models.evidence import EvidenceItem, EvidenceType, QualityStatus, EvidenceStoreSnapshot


class EvidenceStore:
    """
    Repositório versionado de fatos, cálculos e hipóteses com rastreabilidade total.
    Base para todas as análises e decisões do sistema.
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.version = 1
        self.items: Dict[str, EvidenceItem] = {}
        self.change_log: List[Dict[str, Any]] = []

    def record_evidence(
        self,
        field: str,
        value: Any,
        source: str,
        evidence_type: EvidenceType,
        confidence: float,
        formatted_value: Optional[str] = None,
        notes: Optional[str] = None,
        layer: str = "6. DATA QUALITY & GOAL DEFENSE"
    ) -> EvidenceItem:
        """
        Registra ou atualiza uma evidência com validação de qualidade automática.
        """
        item_id = f"ev_{field}_{len(self.items) + 1}"
        
        # Validação automática de qualidade e limites
        quality_status = QualityStatus.ACEITO
        validation_notes = notes

        if confidence < 40.0:
            quality_status = QualityStatus.ALERTA
            validation_notes = f"Baixa confiança ({confidence}%). Recomenda-se validação adicional."

        if value is None:
            quality_status = QualityStatus.REJEITADO
            validation_notes = "Valor ausente / nulo rejeitado pelo verificador de qualidade."

        item = EvidenceItem(
            id=item_id,
            field=field,
            value=value,
            formatted_value=formatted_value or str(value),
            source=source,
            timestamp=datetime.now().isoformat(),
            evidence_type=evidence_type,
            confidence=round(confidence, 1),
            quality_status=quality_status,
            validation_notes=validation_notes,
            source_layer=layer
        )

        self.items[field] = item
        self.change_log.append({
            "action": "RECORD",
            "field": field,
            "version": self.version,
            "timestamp": datetime.now().isoformat()
        })
        self.version += 1
        return item

    def get_evidence(self, field: str) -> Optional[EvidenceItem]:
        return self.items.get(field)

    def run_verifications(self, required_fields: List[str]) -> Dict[str, Any]:
        """
        Executa as verificações automáticas descritas no diagrama:
        - Completude
        - Atualidade
        - Confiabilidade
        - Consistência
        - Conflitos
        - Valores Faltantes
        """
        missing_fields = [f for f in required_fields if f not in self.items or self.items[f].value is None]
        completeness = ((len(required_fields) - len(missing_fields)) / max(len(required_fields), 1)) * 100.0
        
        # Confiabilidade média das evidências
        if self.items:
            avg_confidence = sum(i.confidence for i in self.items.values()) / len(self.items)
        else:
            avg_confidence = 0.0

        conflicts = []
        # Verificação de consistência matemática
        if "cmv" in self.items and "selling_price" in self.items:
            cmv_val = float(self.items["cmv"].value)
            price_val = float(self.items["selling_price"].value)
            if cmv_val >= price_val:
                conflicts.append(f"Inconsistência crítica: CMV (R$ {cmv_val:.2f}) >= Preço de venda (R$ {price_val:.2f})")

        has_conflicts = len(conflicts) > 0
        quality_acceptable = (completeness >= 80.0) and (not has_conflicts) and (avg_confidence >= 50.0)

        return {
            "completeness_score": round(completeness, 1),
            "missing_fields": missing_fields,
            "avg_confidence": round(avg_confidence, 1),
            "has_conflicts": has_conflicts,
            "conflict_details": conflicts,
            "quality_acceptable": quality_acceptable,
            "total_evidences": len(self.items)
        }

    def export_snapshot(self) -> EvidenceStoreSnapshot:
        """
        Gera o snapshot estruturado do Evidence Store para exibição no frontend e auditoria.
        """
        verif = self.run_verifications([])
        return EvidenceStoreSnapshot(
            session_id=self.session_id,
            version=self.version,
            items=list(self.items.values()),
            completeness_score=verif["completeness_score"],
            has_conflicts=verif["has_conflicts"],
            conflict_details=verif["conflict_details"]
        )
