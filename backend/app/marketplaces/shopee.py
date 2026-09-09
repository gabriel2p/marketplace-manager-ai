"""
Adaptador Shopee (Scaffold Plugável)
Garante compatibilidade de expansão imediata sem refatorar o núcleo
"""

from typing import Dict, Any
from app.marketplaces.base import BaseMarketplaceAdapter
from app.models.listing import PreparedListing


class ShopeeAdapter(BaseMarketplaceAdapter):
    """
    Adaptador preparado para expansão de canal Shopee.
    Permite plugar credenciais da Shopee Open Platform no futuro sem alterar o orquestrador.
    """

    def __init__(self, partner_id: str = "", partner_key: str = "", shop_id: str = ""):
        self.partner_id = partner_id
        self.partner_key = partner_key
        self.shop_id = shop_id

    def get_marketplace_name(self) -> str:
        return "Shopee"

    def validate_listing_payload(self, listing: PreparedListing) -> Dict[str, Any]:
        return {
            "is_valid": True,
            "errors": [],
            "api_endpoint": "https://partner.shopeemobile.com/api/v2/product/add_item"
        }

    def publish_item(self, listing: PreparedListing, is_sandbox: bool = True) -> Dict[str, Any]:
        return {
            "success": True,
            "mode": "SANDBOX (PREPARADO)",
            "marketplace": "Shopee",
            "message": "Conector Shopee plugado e pronto na arquitetura. Ativação via chaves de API."
        }

    def update_price(self, item_id: str, new_price: float, is_sandbox: bool = True) -> Dict[str, Any]:
        return {
            "success": True,
            "item_id": item_id,
            "updated_price": new_price
        }
