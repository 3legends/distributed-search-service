from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------ Documents

class DocumentCreate(BaseModel):
    title:    str            = Field(..., min_length=1, max_length=512,
                                     description="Document title")
    content:  str            = Field(..., min_length=1,
                                     description="Full document text to be indexed")
    metadata: Dict[str, Any] = Field(default_factory=dict,
                                     description="Arbitrary key-value metadata")
    tags:     List[str]      = Field(default_factory=list,
                                     description="Searchable tags / labels")

    @field_validator("tags")
    @classmethod
    def tags_max(cls, v: list) -> list:
        if len(v) > 50:
            raise ValueError("Maximum 50 tags per document")
        return [t.strip().lower() for t in v if t.strip()]


class DocumentUpdate(BaseModel):
    title:    Optional[str]            = Field(None, min_length=1, max_length=512)
    content:  Optional[str]            = Field(None, min_length=1)
    metadata: Optional[Dict[str, Any]] = None
    tags:     Optional[List[str]]      = None


class DocumentResponse(BaseModel):
    id:         str
    tenant_id:  str
    title:      str
    content:    str
    metadata:   Dict[str, Any]
    tags:       List[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentIndexed(BaseModel):
    """Returned immediately after a successful index request."""
    id:        str
    tenant_id: str
    indexed:   bool = True
    message:   str  = "Document queued for indexing"


# ------------------------------------------------------------------ Search

class SearchHit(BaseModel):
    id:              str
    title:           str
    content_snippet: str
    score:           float
    tags:            List[str]
    highlights:      Dict[str, List[str]] = Field(default_factory=dict)
    created_at:      Optional[datetime]   = None


class SearchResponse(BaseModel):
    query:     str
    tenant_id: str
    total:     int
    page:      int
    size:      int
    took_ms:   float
    cached:    bool
    results:   List[SearchHit]


# ------------------------------------------------------------------ Health

class DependencyStatus(BaseModel):
    status:     str          # "ok" | "degraded" | "down"
    latency_ms: float
    detail:     Optional[str] = None


class HealthResponse(BaseModel):
    status:       str   # "healthy" | "degraded" | "unhealthy"
    version:      str
    dependencies: Dict[str, DependencyStatus]


# ------------------------------------------------------------------ Tenant

class TenantCreate(BaseModel):
    id:   str  = Field(..., min_length=1, max_length=64,
                       pattern=r"^[a-zA-Z0-9_-]+$",
                       description="Unique tenant slug (alphanumeric, _ or -)")
    name: str  = Field(..., min_length=1, max_length=256)


class TenantResponse(BaseModel):
    id:         str
    name:       str
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ Common

class ErrorResponse(BaseModel):
    error:   str
    detail:  Optional[str] = None
    status:  int