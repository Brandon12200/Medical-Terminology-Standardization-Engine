"""Thread-safe terminology mapper for use with FastAPI."""
import threading
from typing import Dict, List, Optional, Any
from app.standards.terminology.mapper import TerminologyMapper
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class ThreadSafeTerminologyMapper:
    """Thread-safe wrapper for TerminologyMapper that creates new instances per thread."""
    
    def __init__(self):
        self._local = threading.local()
        self._lock = threading.Lock()
    
    def _get_mapper(self) -> TerminologyMapper:
        """Get or create a mapper instance for the current thread."""
        if not hasattr(self._local, 'mapper'):
            with self._lock:
                if not hasattr(self._local, 'mapper'):
                    logger.info(f"Creating new mapper instance for thread {threading.current_thread().ident}")
                    self._local.mapper = TerminologyMapper()
        return self._local.mapper
    
    def map_term(
        self,
        term: str,
        systems: List[str] = None,
        fuzzy_threshold: float = 0.7,
        context: Optional[str] = None,
        include_fuzzy: bool = True,
        max_results_per_system: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Thread-safe term mapping."""
        mapper = self._get_mapper()
        
        # Map term for each system
        all_results = {}
        if systems is None or 'all' in systems:
            systems = ['snomed', 'loinc', 'rxnorm']
            
        for system in systems:
            try:
                system_results = []
                
                # Try to get multiple results from APIs first
                if hasattr(mapper, 'external_service') and mapper.external_service:
                    try:
                        logger.debug(f"Starting API search for '{term}' in {system}")
                        if system == 'snomed':
                            # Use improved SNOMED API search
                            api_results = mapper.external_service.search_snomed_browser(term, max_results=max_results_per_system)
                        elif system == 'loinc':
                            api_results = mapper.external_service.search_clinical_tables(term, 'loinc', max_results=max_results_per_system)
                        elif system == 'rxnorm':
                            # Try RxNorm API first with timeout protection
                            try:
                                api_results = mapper.external_service.search_rxnorm(term, max_results=max_results_per_system)
                            except Exception as rxnorm_error:
                                logger.warning(f"RxNorm API failed for '{term}': {str(rxnorm_error)[:100]}")
                                api_results = []
                            
                            if not api_results:
                                # Fallback to Clinical Tables
                                try:
                                    api_results = mapper.external_service.search_clinical_tables(term, 'rxterms', max_results=max_results_per_system)
                                except Exception as clinical_error:
                                    logger.warning(f"Clinical Tables RxNorm fallback failed for '{term}': {str(clinical_error)[:100]}")
                                    api_results = []
                        else:
                            api_results = []
                        
                        # Format API results
                        for result in api_results:
                            system_results.append({
                                "code": result.get("code", ""),
                                "display": result.get("display", ""),
                                "system": system,
                                "confidence": 0.95,
                                "match_type": "api",
                                "source": result.get("source", "external_api")
                            })
                            
                        logger.info(f"Found {len(system_results)} API results for '{term}' in {system}")
                        
                    except Exception as e:
                        logger.warning(f"API search failed for '{term}' in system '{system}': {str(e)}")
                        # Continue to local fallback instead of failing completely
                
                # If no API results, fallback to local database
                if not system_results:
                    local_result = mapper.map_term(
                        term=term,
                        system=system,
                        context=context
                    )
                    
                    if local_result and local_result.get("found", False):
                        # Convert score (0-100) to confidence (0-1) if confidence not present
                        confidence = local_result.get("confidence")
                        if confidence is None:
                            score = local_result.get("score", 100)
                            confidence = score / 100 if score <= 100 else score / 1000

                        system_results = [{
                            "code": local_result.get("code", ""),
                            "display": local_result.get("display", ""),
                            "system": system,
                            "confidence": confidence,
                            "match_type": local_result.get("match_type", "local"),
                            "source": "local_database"
                        }]
                        logger.info(f"Found local fallback result for '{term}' in {system}")
                
                if system_results:
                    all_results[system] = system_results
                        
            except Exception as e:
                logger.warning(f"Error mapping term '{term}' in system '{system}': {str(e)}")
                
        return all_results
    
    def get_systems_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about available terminology systems."""
        mapper = self._get_mapper()
        return mapper.get_systems_info()