from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import FileResponse
from typing import Optional, List
import os
import sys
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from api.v1.models.batch import (
    BatchJobRequest, BatchJobStatus, BatchJobResult,
    BatchStatus, FileFormat
)
from api.v1.models.terminology import BatchMappingRequest, BatchMappingResponse
from api.v1.services.batch_service import BatchService
from app.utils.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)

# Initialize service
batch_service = BatchService()

@router.post(
    "/batch",
    response_model=BatchMappingResponse,
    summary="Batch map terms",
    description="Map multiple medical terms in a single request"
)
async def batch_map_terms(request: BatchMappingRequest):
    """
    Map multiple medical terms in a single request.
    
    - **terms**: List of medical terms to map (1-1000 terms)
    - **systems**: List of terminology systems to search
    - **context**: Clinical context for better matching
    - **fuzzy_threshold**: Minimum confidence for fuzzy matches
    - **fuzzy_algorithms**: List of fuzzy algorithms to use
    - **max_results_per_term**: Maximum results per term
    """
    try:
        results = await batch_service.batch_map_terms(request)
        return results
    except ValueError as e:
        logger.error(f"Value error in batch mapping: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in batch mapping: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing batch: {str(e)}"
        )

@router.post(
    "/batch/upload",
    response_model=BatchJobStatus,
    summary="Upload file for batch processing",
    description="Upload a file containing medical terms for batch processing"
)
async def upload_batch_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    file_format: FileFormat = Form(...),
    column_name: Optional[str] = Form(default="term"),
    systems: Optional[List[str]] = Form(default=["all"]),
    context: Optional[str] = Form(default=None),
    fuzzy_threshold: float = Form(default=0.7, ge=0.0, le=1.0),
    fuzzy_algorithms: Optional[List[str]] = Form(default=["all"]),
    max_results_per_term: int = Form(default=3, ge=1, le=50)
):
    """
    Upload a file for batch terminology mapping.
    
    Supported formats: CSV, JSON, Excel, TXT
    
    The file should contain medical terms to be mapped.
    For CSV/Excel, specify the column name containing the terms.
    """
    try:
        # Validate file format
        if file_format not in FileFormat:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_format}"
            )
        
        # Create batch job request
        job_request = BatchJobRequest(
            filename=file.filename,
            file_format=file_format,
            column_name=column_name,
            systems=systems,
            context=context,
            fuzzy_threshold=fuzzy_threshold,
            fuzzy_algorithms=fuzzy_algorithms,
            max_results_per_term=max_results_per_term
        )
        
        # Save file and create job
        job_status = await batch_service.create_batch_job(
            job_request, file, background_tasks
        )
        
        return job_status
        
    except Exception as e:
        logger.error(f"Error uploading batch file: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing upload: {str(e)}"
        )

@router.get(
    "/batch/status/{job_id}",
    response_model=BatchJobStatus,
    summary="Get batch job status",
    description="Get the status of a batch processing job"
)
async def get_batch_status(job_id: str):
    """
    Get the current status of a batch processing job.
    """
    try:
        status = await batch_service.get_job_status(job_id)
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Job not found: {job_id}"
            )
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving job status: {str(e)}"
        )

@router.get(
    "/batch/result/{job_id}",
    response_model=BatchJobResult,
    summary="Get batch job results",
    description="Get the results of a completed batch processing job"
)
async def get_batch_results(job_id: str, limit: int = 1000, offset: int = 0):
    """
    Get the results of a completed batch processing job.
    
    - **limit**: Maximum number of results to return
    - **offset**: Number of results to skip
    """
    try:
        results = await batch_service.get_job_results(job_id, limit, offset)
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Results not found for job: {job_id}"
            )
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job results: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving job results: {str(e)}"
        )

@router.get(
    "/batch/download/{job_id}.{format}",
    summary="Download batch results",
    description="Download batch processing results in specified format"
)
async def download_batch_results(job_id: str, format: str):
    """
    Download batch processing results.
    
    Supported formats: csv, json, excel
    """
    try:
        file_path = await batch_service.get_result_file(job_id, format)
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(
                status_code=404,
                detail=f"Results file not found for job: {job_id}"
            )
        
        return FileResponse(
            path=file_path,
            filename=f"terminology_mappings_{job_id}.{format}",
            media_type={
                "csv": "text/csv",
                "json": "application/json",
                "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }.get(format, "application/octet-stream")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading results: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading results: {str(e)}"
        )