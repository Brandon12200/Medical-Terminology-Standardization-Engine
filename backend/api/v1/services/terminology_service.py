import sys
import os
from typing import List, Dict, Optional, Any
import asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from api.v1.services.thread_safe_mapper import ThreadSafeTerminologyMapper
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class TerminologyService:
    def __init__(self):
        """Initialize terminology service."""
        try:
            self.mapper = ThreadSafeTerminologyMapper()
            
            # AI term extraction disabled - only fuzzy matching available
            self.term_extractor = None
            self.ai_enabled = False
            logger.info("Terminology service initialized (fuzzy matching only)")
                
            logger.info("Terminology service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize terminology service: {str(e)}")
            raise

    async def map_term(
        self,
        term: str,
        systems: List[str] = ["all"],
        context: Optional[str] = None,
        fuzzy_threshold: float = 0.7,
        fuzzy_algorithms: List[str] = ["all"],
        max_results: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Map term to standardized terminologies.
            context: Clinical context for better matching
            fuzzy_threshold: Minimum confidence for fuzzy matches
            fuzzy_algorithms: List of fuzzy algorithms to use
            max_results: Maximum results per system
            
        Returns:
            Dictionary mapping system names to lists of matches
        """
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            # Determine which systems to search
            if "all" in systems:
                target_systems = ["snomed", "loinc", "rxnorm"]
            else:
                target_systems = [s.lower() for s in systems]
            
            # Map term using thread-safe mapper
            results = await loop.run_in_executor(
                None,
                lambda: self.mapper.map_term(
                    term=term,
                    systems=target_systems,
                    fuzzy_threshold=fuzzy_threshold,
                    context=context,
                    max_results_per_system=max_results
                )
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Error mapping term '{term}': {str(e)}", exc_info=True)
            raise


    async def batch_map_terms(
        self,
        terms: List[str],
        systems: List[str] = ["all"],
        context: Optional[str] = None,
        fuzzy_threshold: float = 0.7,
        fuzzy_algorithms: List[str] = ["all"],
        max_results_per_term: int = 3,
        min_confidence: float = 0.6
    ) -> List[Dict[str, Any]]:
        """
        Map multiple terms in batch.

        Args:
            terms: List of medical terms to map
            systems: List of terminology systems to search
            context: Clinical context for better matching
            fuzzy_threshold: Minimum confidence for fuzzy matches
            fuzzy_algorithms: List of fuzzy algorithms to use
            max_results_per_term: Maximum results per term per system
            min_confidence: Minimum confidence threshold (filters out low-quality matches)
            
        Returns:
            List of mapping results for each term
        """
        try:
            logger.info(f"Processing {len(terms)} terms in batch mapping")
            
            # Process terms with optimized batching for better performance
            results = []
            batch_size = 5  # Process 5 terms at a time (reduced to prevent API timeout issues)
            delay_between_batches = 0.5  # 500ms delay between batches (increased to reduce API pressure)
            
            for i in range(0, len(terms), batch_size):
                batch_terms = terms[i:i + batch_size]
                logger.info(f"Processing batch {i//batch_size + 1}: terms {i+1}-{min(i+batch_size, len(terms))} of {len(terms)}")
                
                # Process current batch concurrently
                tasks = []
                for term in batch_terms:
                    task = self.map_term(
                        term=term,
                        systems=systems,
                        context=context,
                        fuzzy_threshold=fuzzy_threshold,
                        fuzzy_algorithms=fuzzy_algorithms,
                        max_results=max_results_per_term
                    )
                    tasks.append(task)
                
                # Wait for current batch to complete with individual error handling
                logger.info(f"Processing batch {i//batch_size + 1} with terms: {batch_terms}")
                
                # Use gather with return_exceptions=True to handle individual failures gracefully
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log individual term results within this batch
                for idx, (term, result) in enumerate(zip(batch_terms, batch_results)):
                    if isinstance(result, Exception):
                        logger.error(f"Term '{term}' failed with exception: {str(result)[:200]}")
                    else:
                        mappings_count = sum(len(mappings) for mappings in result.values()) if isinstance(result, dict) else 0
                        if mappings_count == 0:
                            logger.warning(f"Term '{term}' - APIs returned no mappings")
                        else:
                            logger.info(f"Term '{term}' - Found {mappings_count} mappings")
                
                # Log batch completion
                successful_in_batch = sum(1 for r in batch_results if not isinstance(r, Exception))
                failed_in_batch = len(batch_results) - successful_in_batch
                logger.info(f"Batch {i//batch_size + 1} completed: {successful_in_batch} successful, {failed_in_batch} failed")
                
                results.extend(batch_results)
                
                # Add delay between batches to avoid rate limiting
                if i + batch_size < len(terms):
                    await asyncio.sleep(delay_between_batches)
            
            # Format results with detailed logging
            formatted_results = []
            successful_count = 0
            error_count = 0
            
            for i, (term, result) in enumerate(zip(terms, results)):
                if isinstance(result, Exception):
                    error_count += 1
                    error_msg = str(result)[:200]  # Truncate long error messages
                    logger.error(f"Error mapping term '{term}' (#{i+1}/{len(terms)}): {error_msg}")
                    formatted_results.append({
                        "term": term,
                        "results": {},
                        "error": error_msg,
                        "status": "failed"
                    })
                else:
                    successful_count += 1
                    # Filter results by minimum confidence threshold
                    filtered_result = {}
                    if isinstance(result, dict):
                        for system, mappings in result.items():
                            filtered_mappings = [
                                m for m in mappings
                                if m.get("confidence", 0) >= min_confidence
                            ]
                            if filtered_mappings:
                                filtered_result[system] = filtered_mappings

                    # Count total mappings for this term
                    total_mappings = sum(len(mappings) for mappings in filtered_result.values())
                    if total_mappings > 0:
                        logger.info(f"Successfully mapped term '{term}' (#{i+1}/{len(terms)}): {total_mappings} mappings found")
                        status = "success"
                    else:
                        logger.warning(f"No mappings found for term '{term}' (#{i+1}/{len(terms)})")
                        status = "no_mappings"

                    formatted_results.append({
                        "term": term,
                        "results": filtered_result,
                        "status": status
                    })
            
            logger.info(f"Batch processing complete: {successful_count} successful, {error_count} errors out of {len(terms)} terms")
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error in batch mapping: {str(e)}", exc_info=True)
            raise

    def get_ai_status(self) -> Dict[str, Any]:
        """Get the status of AI capabilities."""
        return {
            "ai_enabled": self.ai_enabled,
            "model": "BioBERT (dmis-lab/biobert-base-cased-v1.2)" if self.ai_enabled else None,
            "capabilities": ["medical_term_extraction", "named_entity_recognition"] if self.ai_enabled else [],
            "status": "active" if self.ai_enabled else "disabled"
        }
    
    async def extract_and_map_terms(
        self,
        text: str,
        systems: List[str] = ["all"],
        fuzzy_threshold: float = 0.7,
        include_context: bool = True
    ) -> Dict[str, Any]:
        """
        Extract medical terms from text using AI and map them to terminologies.
        
        Args:
            text: Clinical text to extract terms from
            systems: Terminology systems to map to
            fuzzy_threshold: Minimum confidence for fuzzy matches
            include_context: Whether to use surrounding text as context
            
        Returns:
            Dictionary with extracted terms and their mappings
        """
        try:
            result = {
                "ai_enabled": self.ai_enabled,
                "extracted_terms": [],
                "mapped_terms": {}
            }
            
            # AI term extraction disabled - use pattern-based extraction as fallback
            logger.info("AI term extraction disabled - using pattern-based extraction")
            
            # Simple pattern matching for common medical terms
            import re
            medical_patterns = [
                r'\b(?:diabetes|hypertension|asthma|pneumonia|covid-19|coronavirus)\b',
                r'\b(?:glucose|hemoglobin|creatinine|cholesterol)\b',
                r'\b(?:metformin|insulin|aspirin|lisinopril)\b'
            ]
            
            for pattern in medical_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    term = match.group()
                    if term not in [t["text"] for t in result["extracted_terms"]]:
                        term_info = {
                            "text": term,
                            "entity_type": "PATTERN_MATCH",
                            "confidence": 0.7,
                            "start": match.start(),
                            "end": match.end()
                        }
                        result["extracted_terms"].append(term_info)
                        
                        # Map the term
                        mapping_result = await self.map_term(
                            term=term,
                            systems=systems,
                            fuzzy_threshold=fuzzy_threshold
                        )
                        
                        if mapping_result:
                            result["mapped_terms"][term] = mapping_result
            
            return result
            
        except Exception as e:
            logger.error(f"Error in extract_and_map_terms: {str(e)}")
            raise