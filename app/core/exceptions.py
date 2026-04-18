from fastapi import HTTPException, status


class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentNotFoundError(AppError):
    def __init__(self, document_id: str):
        super().__init__(f"Document '{document_id}' not found", status_code=404)


class TenantNotFoundError(AppError):
    def __init__(self, tenant_id: str):
        super().__init__(f"Tenant '{tenant_id}' not found", status_code=404)


class TenantMissingError(AppError):
    def __init__(self):
        super().__init__(
            "Tenant ID is required. Provide it via X-Tenant-ID header.",
            status_code=400,
        )


class RateLimitExceededError(AppError):
    def __init__(self, tenant_id: str, retry_after: int):
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for tenant '{tenant_id}'. Retry after {retry_after}s.",
            status_code=429,
        )


class SearchServiceError(AppError):
    def __init__(self, detail: str):
        super().__init__(f"Search service error: {detail}", status_code=503)


class IndexingError(AppError):
    def __init__(self, detail: str):
        super().__init__(f"Indexing error: {detail}", status_code=500)
