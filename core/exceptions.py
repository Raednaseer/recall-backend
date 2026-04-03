from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from utils.logger import get_logger

logger = get_logger(__name__)


async def global_exception_handler(request: Request, exc: Exception):
    """Catch any unhandled exceptions and return a clean JSON response."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


def register_exception_handlers(app: FastAPI):
    """Register global exception handlers on the app."""
    app.add_exception_handler(Exception, global_exception_handler)
