"""Inventory API - Placeholder."""

from fastapi import APIRouter

inventory_router = APIRouter(prefix="/inventory", tags=["inventory"])


@inventory_router.get("/status")
async def get_inventory_status():
    """Get inventory status."""
    return {"status": "ok", "message": "Inventory service placeholder"}
