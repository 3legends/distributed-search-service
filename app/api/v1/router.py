from fastapi import APIRouter
from .documents import router as documents_router
from .search import router as search_router
from .tenants import router as tenants_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(documents_router)
api_router.include_router(search_router)
api_router.include_router(tenants_router)
