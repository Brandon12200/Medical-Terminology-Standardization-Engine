"""Fuzzy matching for medical terms."""

import os
import re
import json
import logging
import sqlite3
from typing import Dict, List, Optional, Any, Tuple, Union
from collections import defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
    logger.info("RapidFuzz library available for enhanced fuzzy matching")
except ImportError:
    logger.warning("RapidFuzz library not available, falling back to basic fuzzy matching")
    HAS_RAPIDFUZZ = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    HAS_SKLEARN = True
    logger.info("scikit-learn available for TF-IDF vectorization")
except ImportError:
    logger.warning("scikit-learn not available, TF-IDF vectorization will be disabled")
    HAS_SKLEARN = False

class FuzzyMatcher:
    """Fuzzy matcher for medical terminology."""
    
    def __init__(self, db_manager, config: Optional[Dict[str, Any]] = None):
        """Initialize with database manager and optional config."""
        self.config = config or {}
        self.db_manager = db_manager
        self.stopwords = self._load_stopwords()
        self.synonym_expander = None
        
        self.term_index = {
            "snomed": {},
            "loinc": {},
            "rxnorm": {}
        }
        
        self.term_lists = {
            "snomed": [],
            "loinc": [],
            "rxnorm": []
        }
        
        self.vectorizers = {}
        self.vector_matrices = {}
        
        self.synonyms = {}
        
        self.thresholds = {
            "ratio": self.config.get("ratio_threshold", 90),
            "partial_ratio": self.config.get("partial_ratio_threshold", 95),
            "token_sort_ratio": self.config.get("token_sort_ratio_threshold", 85),
            "levenshtein": self.config.get("levenshtein_threshold", 0.8),
            "jaccard": self.config.get("jaccard_threshold", 0.7),
            "cosine": self.config.get("cosine_threshold", 0.7)
        }
        
        self.common_replacements = {
            'disease': ['disorder', 'syndrome', 'condition'],
            'syndrome': ['disease', 'disorder', 'condition'],
            'disorder': ['disease', 'syndrome', 'condition'],
            'infection': ['disease', 'inflammatory'],
            'neoplasm': ['tumor', 'cancer', 'mass'],
            'tumor': ['neoplasm', 'cancer', 'mass'],
            'cancer': ['neoplasm', 'tumor', 'malignancy'],
            'medication': ['drug', 'medicine', 'pharmaceutical'],
            'drug': ['medication', 'medicine', 'pharmaceutical'],
            'examination': ['exam', 'assessment', 'evaluation'],
            'assessment': ['exam', 'examination', 'evaluation'],
            'abnormality': ['anomaly', 'defect', 'malformation'],
            'pain': ['ache', 'discomfort', 'soreness'],
            'inflammation': ['inflammatory', 'itis'],
            'insufficiency': ['deficiency', 'failure'],
            'test': ['assay', 'analysis', 'measurement'],
            'injury': ['trauma', 'wound', 'damage'],
            'chronic': ['persistent', 'long-term', 'ongoing'],
            'acute': ['sudden', 'severe', 'short-term'],
            'elevated': ['increased', 'high', 'raised'],
            'decreased': ['reduced', 'low', 'deficient']
        }
        
        self.abbreviations = {
            'MI': ['myocardial infarction', 'heart attack'],
            'HTN': ['hypertension', 'high blood pressure'],
            'DM': ['diabetes mellitus'],
            'T2DM': ['type 2 diabetes mellitus', 'diabetes type 2'],
            'COPD': ['chronic obstructive pulmonary disease'],
            'CHF': ['congestive heart failure', 'heart failure'],
            'CAD': ['coronary artery disease'],
            'CVA': ['cerebrovascular accident', 'stroke'],
            'UTI': ['urinary tract infection'],
            'GERD': ['gastroesophageal reflux disease', 'acid reflux'],
            'RA': ['rheumatoid arthritis'],
            'OA': ['osteoarthritis'],
            'CKD': ['chronic kidney disease'],
            'HLD': ['hyperlipidemia', 'high cholesterol'],
            'BPH': ['benign prostatic hyperplasia', 'enlarged prostate'],
            'DVT': ['deep vein thrombosis'],
            'PE': ['pulmonary embolism'],
            'ADHD': ['attention deficit hyperactivity disorder'],
            'IBD': ['inflammatory bowel disease'],
            'IBS': ['irritable bowel syndrome'],
            'HA': ['headache'],
            'SOB': ['shortness of breath'],
            'CP': ['chest pain'],
            'BP': ['blood pressure'],
            'Hb A1c': ['hemoglobin a1c', 'glycated hemoglobin']
        }
        
        self.medical_suffixes = {
            'itis': 'inflammation',
            'emia': 'blood condition',
            'oma': 'tumor',
            'osis': 'condition',
            'pathy': 'disease',
            'megaly': 'enlargement',
            'algia': 'pain',
            'dynia': 'pain',
            'ectomy': 'surgical removal',
            'plasty': 'surgical repair',
            'otomy': 'surgical incision',
            'ostomy': 'surgical opening',
            'scopy': 'visual examination',
            'graphy': 'imaging',
            'gram': 'record',
            'trophy': 'growth'
        }
        
        self._load_synonyms()
    
    def _load_stopwords(self) -> List[str]:
        """Get stopwords list."""
        stopwords = [
            'a', 'an', 'the', 'and', 'or', 'but', 'if', 'because', 'as', 'what',
            'when', 'where', 'how', 'who', 'which', 'this', 'that', 'these', 'those',
            'then', 'just', 'so', 'than', 'such', 'both', 'through', 'about', 'for',
            'is', 'of', 'while', 'during', 'to', 'from', 'in', 'out', 'on', 'off',
            'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
            'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
            'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
            'very', 's', 't', 'can', 'will', 'don', 'should', 'now', 'with', 'by'
        ]
        return stopwords
    
    def _load_synonyms(self):
        """Load custom synonym mappings if available."""
        try:
            synonyms_path = self.config.get("synonyms_path")
            if synonyms_path and os.path.exists(synonyms_path):
                with open(synonyms_path, 'r') as f:
                    self.synonyms = json.load(f)
                logger.info(f"Loaded {len(self.synonyms)} synonym sets from {synonyms_path}")
            else:
                self.synonyms = {}
        except Exception as e:
            logger.error(f"Error loading synonyms: {e}")
            self.synonyms = {}
    
    def initialize(self) -> bool:
        """Build indexes for fuzzy matching."""
        try:
            success = self._build_index("snomed")
            success = self._build_index("loinc") and success
            success = self._build_index("rxnorm") and success
            
            if HAS_SKLEARN:
                self._initialize_vectorizer()
            
            if success:
                logger.info("Fuzzy matcher initialized successfully")
            else:
                logger.warning("Fuzzy matcher initialization incomplete")
                
            return success
        except Exception as e:
            logger.error(f"Error initializing fuzzy matcher: {e}")
            return False
    
    def _build_index(self, system: str) -> bool:
        """Build index for given terminology system."""
        try:
            if system not in self.db_manager.connections:
                logger.warning(f"No database connection for {system}")
                return False
                
            conn = self.db_manager.connections[system]
            cursor = conn.cursor()
            table_name = f"{system}_concepts"
            
            cursor.execute(f"SELECT code, term, display FROM {table_name}")
            rows = cursor.fetchall()
            
            for code, term, display in rows:
                if not term:
                    continue
                    
                term_lower = term.lower()
                
                self.term_lists[system].append((code, term_lower, display))
                
                self.term_index[system][term_lower] = {
                    "code": code,
                    "display": display
                }
                
                variations = self._generate_term_variations(term_lower)
                for var in variations:
                    if var != term_lower:
                        self.term_index[system][var] = {
                            "code": code,
                            "display": display
                        }
            
            logger.info(f"Built index for {system} with {len(self.term_index[system])} terms")
            return True
        except Exception as e:
            logger.error(f"Error building index for {system}: {e}")
            return False
    
    def _initialize_vectorizer(self):
        """Initialize the TF-IDF vectorizer for cosine similarity matching."""
        if not HAS_SKLEARN:
            return
            
        try:
            # Build vector matrices for each terminology with separate vectorizers
            for system in ["snomed", "loinc", "rxnorm"]:
                if not self.term_lists[system]:
                    continue
                    
                # Extract just the terms
                terms = [term for _, term, _ in self.term_lists[system]]
                
                # Create system-specific vectorizer
                self.vectorizers[system] = TfidfVectorizer(
                    analyzer='word',
                    tokenizer=self._tokenize,
                    lowercase=True,
                    stop_words=self.stopwords,
                    ngram_range=(1, 2)  # Use unigrams and bigrams
                )
                
                # Build the document-term matrix
                try:
                    matrix = self.vectorizers[system].fit_transform(terms)
                    self.vector_matrices[system] = matrix
                    logger.info(f"Built TF-IDF matrix for {system} with shape {matrix.shape}")
                except Exception as e:
                    logger.error(f"Error building TF-IDF matrix for {system}: {e}")
        except Exception as e:
            logger.error(f"Error initializing vectorizer: {e}")
    
    def _generate_term_variations(self, term: str) -> List[str]:
        """
        Generate variations of a term for fuzzy matching.
        
        Args:
            term: The term to generate variations for
            
        Returns:
            List of term variations
        """
        variations = set([term])
        
        # Remove common prefixes
        prefixes = ["history of ", "chronic ", "acute ", "suspected ", "possible ", "recurrent "]
        for prefix in prefixes:
            if term.startswith(prefix):
                variations.add(term[len(prefix):])
        
        # Remove punctuation
        term_no_punct = re.sub(r'[^\w\s]', ' ', term)
        variations.add(term_no_punct)
        
        # Normalize whitespace
        term_norm = re.sub(r'\s+', ' ', term_no_punct).strip()
        variations.add(term_norm)
        
        # Check for abbreviation expansions
        for abbrev, expansions in self.abbreviations.items():
            if term.upper() == abbrev.upper():
                variations.update([exp.lower() for exp in expansions])
            else:
                # Check if term is an expansion
                for exp in expansions:
                    if term.lower() == exp.lower():
                        variations.add(abbrev.lower())
        
        # Check for word replacements
        words = term.split()
        for i, word in enumerate(words):
            word_lower = word.lower()
            if word_lower in self.common_replacements:
                for replacement in self.common_replacements[word_lower]:
                    new_words = words.copy()
                    new_words[i] = replacement
                    variations.add(' '.join(new_words))
        
        # Handle common medical suffixes
        for suffix, meaning in self.medical_suffixes.items():
            if term.endswith(suffix):
                variations.add(f"{term[:-len(suffix)]} {meaning}")
        
        # Add synonyms if available
        for syn_set in self.synonyms.values():
            if term in syn_set:
                variations.update([s.lower() for s in syn_set])
        
        # Remove duplicates and empty strings
        return [v for v in list(variations) if v]
    
    def find_fuzzy_match(self, term: str, system: str, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find the best fuzzy match for a term.
        
        Args:
            term: The term to find a match for
            system: The terminology system to search (snomed, loinc, rxnorm)
            context: Optional context to improve matching accuracy
            
        Returns:
            Dictionary with mapping information or None if no good match
        """
        if not term:
            return None
            
        # Normalize the term
        clean_term = term.lower()
        clean_term = re.sub(r'\s+', ' ', clean_term).strip()
        
        # Generate variations of the term
        variations = self._generate_term_variations(clean_term)
        
        # Try direct match with variations first
        for var in variations:
            if var in self.term_index[system]:
                match_info = self.term_index[system][var]
                return {
                    "code": match_info["code"],
                    "display": match_info["display"],
                    "system": self._get_system_uri(system),
                    "found": True,
                    "match_type": "variation",
                    "score": 100
                }
        
        # Determine which matching approach to use
        results = []
        
        # 1. Try RapidFuzz-based string matching if available
        if HAS_RAPIDFUZZ:
            string_match = self._find_rapidfuzz_match(clean_term, system, context)
            if string_match:
                results.append(string_match)
        else:
            # Fall back to simpler fuzzy matching
            basic_match = self._find_basic_fuzzy_match(clean_term, system, context)
            if basic_match:
                results.append(basic_match)
        
        # 2. Try TF-IDF cosine similarity matching if available
        if HAS_SKLEARN and hasattr(self, 'vectorizers') and self.vectorizers.get(system):
            cosine_match = self._find_cosine_match(clean_term, system)
            if cosine_match:
                results.append(cosine_match)
        
        # Find the best match from all results
        best_match = None
        best_score = 0
        
        for result in results:
            score = result.get("score", 0)
            if score > best_score:
                best_score = score
                best_match = result
        
        # Apply context-specific adjustments
        if best_match and context:
            best_match = self._adjust_for_context(best_match, term, context, system)
        
        return best_match
    
    def _find_rapidfuzz_match(self, term: str, system: str, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find the best match using RapidFuzz library.
        
        Args:
            term: The term to match
            system: The terminology system to search
            context: Optional context for better matching
            
        Returns:
            Dictionary with mapping information or None if no good match
        """
        if not self.term_index[system]:
            return None
            
        terms = list(self.term_index[system].keys())
        
        # 1. Simple ratio (overall similarity)
        ratio_matches = process.extractOne(
            term,
            terms,
            scorer=fuzz.ratio,
            score_cutoff=self.thresholds["ratio"]
        )
        
        # 2. Partial ratio (best partial string alignment)
        partial_matches = process.extractOne(
            term,
            terms,
            scorer=fuzz.partial_ratio,
            score_cutoff=self.thresholds["partial_ratio"]
        )
        
        # 3. Token sort ratio (order-independent similarity)
        token_matches = process.extractOne(
            term,
            terms,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=self.thresholds["token_sort_ratio"]
        )
        
        # 4. Token set ratio (considers only unique words)
        token_set_matches = process.extractOne(
            term,
            terms,
            scorer=fuzz.token_set_ratio,
            score_cutoff=self.thresholds["token_sort_ratio"]
        )
        
        # 5. Determine the best match
        best_match = None
        best_score = 0
        match_type = ""

        if ratio_matches and ratio_matches[1] > best_score:
            best_score = ratio_matches[1]
            best_match = ratio_matches[0]
            match_type = "ratio"

        # For partial_ratio, require that the matched term is at least 30% of the
        # query term length (or vice versa) to avoid matching short abbreviations
        # against long words (e.g., "ra" matching "pneumonoultramicroscopicsilicovolcanoconiosis")
        if partial_matches and partial_matches[1] > best_score:
            matched_term = partial_matches[0]
            len_ratio = min(len(matched_term), len(term)) / max(len(matched_term), len(term))
            if len_ratio >= 0.3:  # At least 30% length similarity
                best_score = partial_matches[1]
                best_match = matched_term
                match_type = "partial_ratio"
            
        if token_matches and token_matches[1] > best_score:
            best_score = token_matches[1]
            best_match = token_matches[0]
            match_type = "token_sort_ratio"
            
        if token_set_matches and token_set_matches[1] > best_score:
            best_score = token_set_matches[1]
            best_match = token_set_matches[0]
            match_type = "token_set_ratio"
        
        if best_match:
            # Get the code and display name
            match_info = self.term_index[system][best_match]
            
            return {
                "code": match_info["code"],
                "display": match_info["display"],
                "system": self._get_system_uri(system),
                "found": True,
                "match_type": match_type,
                "score": best_score
            }
            
        return None
    
    def _find_basic_fuzzy_match(self, term: str, system: str, context: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find the best match using built-in difflib when rapidfuzz is not available.
        
        Args:
            term: The term to match
            system: The terminology system to search
            context: Optional context for better matching
            
        Returns:
            Dictionary with mapping information or None if no good match
        """
        if not self.term_index[system]:
            return None
            
        # Tokenize the term
        term_tokens = set(self._tokenize(term))
        if not term_tokens:
            return None
            
        best_score = 0
        best_match = None
        best_match_type = ""
        
        # Try each term in the index
        for db_term, match_info in self.term_index[system].items():
            # Calculate Levenshtein similarity
            levenshtein_score = SequenceMatcher(None, term, db_term).ratio()
            
            # Calculate token similarity (Jaccard)
            db_tokens = set(self._tokenize(db_term))
            if not db_tokens:
                continue
                
            # Calculate Jaccard similarity
            intersection = len(term_tokens.intersection(db_tokens))
            union = len(term_tokens.union(db_tokens))
            jaccard_score = intersection / union if union > 0 else 0
            
            # Determine the best score
            if levenshtein_score >= self.thresholds["levenshtein"] and levenshtein_score > best_score:
                best_score = levenshtein_score
                best_match = db_term
                best_match_type = "levenshtein"
                
            if jaccard_score >= self.thresholds["jaccard"] and jaccard_score > best_score:
                best_score = jaccard_score
                best_match = db_term
                best_match_type = "jaccard"
        
        if best_match:
            # Get the code and display name
            match_info = self.term_index[system][best_match]
            
            return {
                "code": match_info["code"],
                "display": match_info["display"],
                "system": self._get_system_uri(system),
                "found": True,
                "match_type": best_match_type,
                "score": best_score * 100  # Convert to same scale as rapidfuzz
            }
            
        return None
    
    def _find_cosine_match(self, term: str, system: str) -> Optional[Dict[str, Any]]:
        """
        Find the best cosine similarity match using TF-IDF.
        
        Args:
            term: The term to match
            system: The terminology system to search
            
        Returns:
            Dictionary with mapping information or None if no good match
        """
        if not HAS_SKLEARN or system not in self.vector_matrices or system not in self.vectorizers:
            return None
            
        try:
            # Transform the query term using the system-specific vectorizer
            term_vector = self.vectorizers[system].transform([term])
            
            # Calculate cosine similarities
            similarities = cosine_similarity(term_vector, self.vector_matrices[system]).flatten()
            
            # Find the best match
            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]
            
            if best_score >= self.thresholds["cosine"]:
                code, _, display = self.term_lists[system][best_idx]
                
                return {
                    "code": code,
                    "display": display,
                    "system": self._get_system_uri(system),
                    "found": True,
                    "match_type": "cosine",
                    "score": float(best_score * 100)
                }
        except Exception as e:
            logger.error(f"Error finding cosine match for term '{term}': {e}")
            
        return None
    
    def _tokenize(self, text: str) -> List[str]:
        """
        Tokenize text for matching.
        
        Args:
            text: The text to tokenize
            
        Returns:
            List of tokens
        """
        # Remove punctuation
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Tokenize
        tokens = text.lower().split()
        
        # Remove stopwords
        tokens = [token for token in tokens if token not in self.stopwords]
        
        return tokens
    
    def _adjust_for_context(self, result: Dict[str, Any], term: str, context: str, system: str) -> Dict[str, Any]:
        """
        Adjust match results based on context.
        
        Args:
            result: The current match result
            term: The term being matched
            context: The context information
            system: The terminology system
            
        Returns:
            Adjusted match result
        """
        # Skip if no context or no result
        if not context or not result:
            return result
            
        # Convert context to lowercase for matching
        context = context.lower()
        
        # System-specific context adjustments
        if system == "snomed":
            # For medical conditions, check if context contains relevant keywords
            condition_contexts = {
                "diabetes": ["glucose", "sugar", "a1c", "metformin", "insulin", "glycemic"],
                "hypertension": ["blood pressure", "bp", "systolic", "diastolic", "mmhg"],
                "asthma": ["respiratory", "breathing", "wheeze", "inhaler", "bronchial"],
                "pneumonia": ["lung", "respiratory", "cough", "infection", "fever"],
                "heart": ["cardiac", "chest pain", "cardiovascular", "ecg", "ekg"]
            }
            
            # Adjust score based on contextual relevance
            display = result.get("display", "").lower()
            for keyword, contextual_terms in condition_contexts.items():
                if keyword in display:
                    # Check if any contextual terms are in the context
                    for contextual_term in contextual_terms:
                        if contextual_term in context:
                            # Increase score if context supports the match
                            if "score" in result:
                                result["score"] = min(100, result["score"] + 10)
                            result["context_enhanced"] = True
                            result["context_term"] = contextual_term
                            break
                            
        elif system == "loinc":
            # For lab tests, check if context contains relevant keywords
            lab_contexts = {
                "hemoglobin": ["blood", "cbc", "anemia", "diabetes"],
                "glucose": ["diabetes", "blood sugar", "fasting", "a1c"],
                "cholesterol": ["lipid", "hdl", "ldl", "cardiovascular"],
                "creatinine": ["kidney", "renal", "gfr", "bun"]
            }
            
            # Adjust score based on contextual relevance
            display = result.get("display", "").lower()
            for keyword, contextual_terms in lab_contexts.items():
                if keyword in display:
                    # Check if any contextual terms are in the context
                    for contextual_term in contextual_terms:
                        if contextual_term in context:
                            # Increase score if context supports the match
                            if "score" in result:
                                result["score"] = min(100, result["score"] + 10)
                            result["context_enhanced"] = True
                            result["context_term"] = contextual_term
                            break
                            
        elif system == "rxnorm":
            # For medications, check if context contains relevant keywords
            med_contexts = {
                "metformin": ["diabetes", "hypoglycemic", "glucose", "a1c"],
                "lisinopril": ["hypertension", "blood pressure", "ace inhibitor", "bp"],
                "aspirin": ["antiplatelet", "pain", "blood thinner", "heart", "stroke"],
                "atorvastatin": ["cholesterol", "statin", "lipid", "cardiovascular"]
            }
            
            # Adjust score based on contextual relevance
            display = result.get("display", "").lower()
            for keyword, contextual_terms in med_contexts.items():
                if keyword in display:
                    # Check if any contextual terms are in the context
                    for contextual_term in contextual_terms:
                        if contextual_term in context:
                            # Increase score if context supports the match
                            if "score" in result:
                                result["score"] = min(100, result["score"] + 10)
                            result["context_enhanced"] = True
                            result["context_term"] = contextual_term
                            break
        
        return result
    
    def fuzzy_search_db(self, term: str, db_connection: sqlite3.Connection, 
                      table: str, term_field: str = 'term', 
                      additional_fields: List[str] = None) -> List[Dict[str, Any]]:
        """
        Perform a fuzzy search directly in a database table.
        
        Args:
            term: The term to search for
            db_connection: SQLite database connection
            table: Name of the table to search
            term_field: Name of the field containing terms
            additional_fields: Additional fields to return
            
        Returns:
            List of matching terms with similarity scores
        """
        # Normalize the input term
        normalized_term = term.lower()
        normalized_term = re.sub(r'\s+', ' ', normalized_term).strip()
        
        # Generate variants for search
        variants = self._generate_term_variations(normalized_term)
        
        try:
            # Prepare the query
            fields = ['code', 'display', term_field]
            if additional_fields:
                fields.extend(additional_fields)
            
            fields_str = ', '.join(fields)
            
            # Get cursor
            cursor = db_connection.cursor()
            
            # Get potential matches using LIKE queries for each variant
            results = []
            for variant in variants:
                if len(variant) < 3:
                    continue  # Skip very short variants to avoid too many matches
                
                like_pattern = f"%{variant}%"
                query = f"SELECT {fields_str} FROM {table} WHERE {term_field} LIKE ? LIMIT 20"
                
                cursor.execute(query, (like_pattern,))
                db_results = cursor.fetchall()
                
                # Process results
                for result in db_results:
                    result_dict = {fields[i]: result[i] for i in range(len(fields))}
                    target_text = result_dict.get(term_field, '')
                    
                    # Calculate similarity
                    if HAS_RAPIDFUZZ:
                        similarity = fuzz.ratio(normalized_term, target_text.lower()) / 100.0
                    else:
                        similarity = SequenceMatcher(None, normalized_term, target_text.lower()).ratio()
                    
                    # If similarity meets threshold, add to results
                    if similarity >= self.thresholds["levenshtein"]:
                        result_dict['similarity'] = similarity * 100  # Convert to percentage
                        result_dict['match_type'] = 'fuzzy'
                        result_dict['confidence'] = similarity * 100
                        results.append(result_dict)
            
            # Remove duplicates (same code)
            unique_results = {}
            for result in results:
                code = result.get('code')
                if code not in unique_results or result['similarity'] > unique_results[code]['similarity']:
                    unique_results[code] = result
            
            # Sort by similarity (descending)
            sorted_results = sorted(unique_results.values(), key=lambda x: x['similarity'], reverse=True)
            
            return sorted_results[:10]  # Limit to top 10 results
            
        except Exception as e:
            logger.error(f"Error performing fuzzy database search: {e}")
            return []
    
    def add_synonym(self, term: str, synonyms: List[str]) -> bool:
        """
        Add synonyms for a term.
        
        Args:
            term: The primary term
            synonyms: List of synonyms for the term
            
        Returns:
            bool: True if synonyms were added successfully
        """
        try:
            # Create a unique set with the term and all synonyms
            syn_set = set([term.lower()] + [s.lower() for s in synonyms])
            
            # Check if this term is already in a synonym set
            for key, existing_set in self.synonyms.items():
                if term.lower() in existing_set:
                    # Add the new synonyms to the existing set
                    existing_set.update(syn_set)
                    self.synonyms[key] = list(existing_set)
                    
                    logger.info(f"Updated synonym set for '{term}' with {len(synonyms)} new synonyms")
                    
                    # Save the synonyms
                    self._save_synonyms()
                    return True
            
            # Create a new synonym set
            new_key = f"syn_set_{len(self.synonyms) + 1}"
            self.synonyms[new_key] = list(syn_set)
            
            logger.info(f"Created new synonym set for '{term}' with {len(synonyms)} synonyms")
            
            # Save the synonyms
            self._save_synonyms()
            return True
        except Exception as e:
            logger.error(f"Error adding synonyms for term '{term}': {e}")
            return False
    
    def _save_synonyms(self):
        """Save synonyms to the configured file."""
        try:
            synonyms_path = self.config.get("synonyms_path")
            if synonyms_path:
                # Ensure directory exists
                os.makedirs(os.path.dirname(synonyms_path), exist_ok=True)
                
                with open(synonyms_path, 'w') as f:
                    json.dump(self.synonyms, f, indent=2)
                    
                logger.info(f"Saved {len(self.synonyms)} synonym sets to {synonyms_path}")
        except Exception as e:
            logger.error(f"Error saving synonyms: {e}")
    
    def _get_system_uri(self, system: str) -> str:
        """Get the URI for a terminology system."""
        systems = {
            "snomed": "http://snomed.info/sct",
            "loinc": "http://loinc.org",
            "rxnorm": "http://www.nlm.nih.gov/research/umls/rxnorm"
        }
        return systems.get(system.lower(), "unknown")