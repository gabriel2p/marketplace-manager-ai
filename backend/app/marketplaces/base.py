"""
Interface Base para Adaptadores de Marketplaces
Garante arquitetura multi-marketplace extensível (Mercado Livre, Shopee, etc.)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from app.models.listing import PreparedListing


class BaseMarketplaceAdapter(ABC):
    
    @abstractmethod
    def get_marketplace_name(self) -> str:
        pass

    @abstractmethod
    def validate_listing_payload(self, listing: PreparedListing) -> Dict[str, Any]:
        """Valida se o anúncio atende às regras e schemas da API do marketplace."""
        pass

    @abstractmethod
    def publish_item(self, listing: PreparedListing, is_sandbox: bool = True) -> Dict[str, Any]:
        """Publica o anúncio no marketplace (modo sandbox ou produção)."""
        pass

    @abstractmethod
    def update_price(self, item_id: str, new_price: float, is_sandbox: bool = True) -> Dict[str, Any]:
        """Atualiza o preço de venda de um item ativo."""
        pass
