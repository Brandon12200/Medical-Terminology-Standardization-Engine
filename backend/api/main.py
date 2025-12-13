from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
import sys
import os

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.v1.routers import terminology, batch, system, test_files
from app.utils.logger import setup_logger

# Setup logger
logger = setup_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Medical Terminology Standardization Engine API")
    
    # Initialize any resources here
    # For example: database connections, cache, etc.
    
    yield
    
    # Shutdown
    logger.info("Shutting down Medical Terminology Standardization Engine API")

# Create FastAPI app
app = FastAPI(
    title="Medical Terminology Standardization Engine API",
    description="API for mapping medical terms to standardized terminologies (SNOMED CT, LOINC, RxNorm)",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Configure CORS
from api.config import settings

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred"}
    )

# Include routers
app.include_router(terminology.router, prefix="/api/v1", tags=["terminology"])
app.include_router(batch.router, prefix="/api/v1", tags=["batch"])
app.include_router(system.router, prefix="/api/v1", tags=["system"])
app.include_router(test_files.router, prefix="/api/v1", tags=["test-files"])

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Medical Terminology Mapper API",
        "version": "1.0.0",
        "docs": "/api/docs"
    }

# Health check endpoints
@app.get("/health")
async def simple_health_check():
    return {"status": "healthy"}

@app.get("/api/v1/health", tags=["system"])
async def health_check():
    return {
        "status": "healthy",
        "service": "Medical Terminology Mapper API",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )