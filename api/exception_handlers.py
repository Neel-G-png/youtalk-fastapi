from fastapi import Request
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception):
    error_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.error(f"Unhandled error: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "error_id": error_id,
            "message": str(exc)
        },
    )