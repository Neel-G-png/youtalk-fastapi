from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from api.routes import process_video, user_sessions, stream_responses
from api.models import HealthResponse
from config.settings import settings
from api.exception_handlers import global_exception_handler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Youtalk API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add global exception handler
app.add_exception_handler(Exception, global_exception_handler)

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    return {"status": "healthy", "env": settings.ENV}

# Include routes
app.include_router(process_video.router)
app.include_router(user_sessions.router)
app.include_router(stream_responses.router)