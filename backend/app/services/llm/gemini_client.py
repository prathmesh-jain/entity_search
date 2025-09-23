import os
from typing import Dict, List, Optional, Any, Union
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, RateLimitError, APITimeoutError
from dotenv import load_dotenv
import json
import asyncio
import logging
from datetime import datetime

from ...utils.api_key_rotator import get_gemini_rotator

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class GeminiClient:
    """Client for interacting with Google's Gemini API using OpenAI SDK."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Gemini client.
        
        Args:
            api_key: Optional API key. If not provided, will use rotating API keys from environment.
        """
        self.api_key_rotator = get_gemini_rotator()
        self.current_api_key = api_key or self.api_key_rotator.get_current_key()
        
        if not self.current_api_key:
            raise ValueError("Gemini API key is required. Set GEMINI_API_KEY environment variable.")
            
        self.client = AsyncOpenAI(
            api_key=self.current_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.model = "gemini-2.5-flash"  # Default model
    
    def _refresh_client_with_new_key(self):
        """Refresh the OpenAI client with a new API key from the rotator."""
        new_key = self.api_key_rotator.get_current_key()
        if new_key and new_key != self.current_api_key:
            self.current_api_key = new_key
            self.client = AsyncOpenAI(
                api_key=self.current_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            logger.info("Refreshed Gemini client with new API key")
    
    async def generate_search_queries(
        self,
        entity_name: str,
        entity_type: str,
        keywords: Optional[List[str]] = None,
        num_queries: int = 4
    ) -> List[str]:
        """
        Generate intelligent search queries using LLM for better entity research.
        
        Args:
            entity_name: Name of the entity to research
            entity_type: Type of entity ('individual' or 'company')
            keywords: Optional list of keywords to incorporate
            num_queries: Number of search queries to generate
            
        Returns:
            List of optimized search queries
        """
        try:
            logger.info(f"Generating LLM search queries for {entity_type}: {entity_name}")
            
            keywords_context = ""
            if keywords:
                keywords_context = f"\nUser-provided keywords: {', '.join(keywords)}"
            
            entity_context = "person" if entity_type == "individual" else "company/organization"
            
            prompt = f"""
            You are an expert search query generator for entity research. Generate {num_queries} highly effective search queries to find comprehensive information about a specific {entity_context}.
            
            TARGET {entity_type.upper()}: "{entity_name}"
            ENTITY TYPE: {entity_type}{keywords_context}
            
            QUERY GENERATION STRATEGY:
            
            For INDIVIDUALS:
            - Professional background and career information
            - Educational history and qualifications
            - Personal details and biographical information
            - Recent news, achievements, or controversies
            - Legal issues, criminal records, or court cases
            - Family connections and relationships
            - Location and residence information
            
            For COMPANIES:
            - Business registration and incorporation details
            - Financial information and market performance
            - Key executives, founders, and leadership team
            - Products, services, and business activities
            - Legal issues, lawsuits, or regulatory actions
            - Mergers, acquisitions, and partnerships
            - Industry reputation and news coverage
            - Headquarters location and office addresses
            
            SEARCH OPTIMIZATION RULES:
            1. Use varied search patterns (exact quotes, combinations, specific terms)
            2. Include location-based searches if keywords suggest geography
            3. Add professional context if keywords indicate occupation/industry
            4. Use both formal and informal name variations
            5. Include time-sensitive searches for recent information
            6. Add verification searches for identity confirmation
            7. Incorporate keyword context naturally into queries
            8. Avoid overly complex or lengthy search terms
            
            
            Generate exactly {num_queries} diverse, effective search queries. Return ONLY the queries, one per line, without numbering or formatting.
            """
            
            response = await self._chat_completion_with_retry(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,  # Slightly higher for creative query generation
                max_tokens=2000
            )
            
            if not response or not response.choices:
                logger.warning("Empty response from LLM query generation - API keys may be exhausted")
                return self._fallback_queries(entity_name, entity_type, keywords)
            
            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM returned None content for query generation")
                return self._fallback_queries(entity_name, entity_type, keywords)
            
            content = content.strip()
            queries = [q.strip() for q in content.split('\n') if q.strip()]
            
            # Filter out empty queries and ensure we have the right number
            queries = [q for q in queries if len(q) > 5]  # Minimum query length
            
            if len(queries) < num_queries:
                logger.warning(f"LLM generated only {len(queries)} queries, expected {num_queries}")
                # Add fallback queries if needed
                fallback = self._fallback_queries(entity_name, entity_type, keywords)
                queries.extend(fallback[:num_queries - len(queries)])
            
            queries = queries[:num_queries]  # Ensure exact number
            
            logger.info(f"Generated {len(queries)} LLM search queries for {entity_name}")
            return queries
            
        except Exception as e:
            logger.error(f"Error generating LLM search queries: {e}")
            return self._fallback_queries(entity_name, entity_type, keywords)
    
    def _fallback_queries(self, entity_name: str, entity_type: str, keywords: Optional[List[str]] = None) -> List[str]:
        """Generate fallback search queries when LLM generation fails."""
        base_queries = []
        
        if keywords:
            # Combine entity name with each keyword
            for keyword in keywords[:3]:  # Limit to avoid too many queries
                base_queries.append(f'{entity_name} {keyword}')
        
        # if entity_type == "individual":
        #     base_queries.extend([
        #         f'{entity_name} biography',
        #         f'{entity_name} profile background',
        #         f'{entity_name} news recent'
        #     ])
        # else:  # company
        #     base_queries.extend([
        #         f'{entity_name} company information',
        #         f'{entity_name} business registration',
        #         f'{entity_name} executives leadership'
        #     ])
        
        return base_queries[:4]  # Return up to 4 queries
    
    def _get_fields_for_entity_type(self, entity_type: str) -> List[str]:
        """Get appropriate extraction fields based on entity type."""
        if entity_type == "individual":
            return [
                "date_of_birth", "year_of_birth", "age", "gender", "nationality",
                "full_name", "aliases", "spouse_name", "family_members",
                "educational_background", "professional_background", "employment_history",
                "government_issued_unique_identifier", "social_security_number",
                "status_alive_deceased", "chinese_name_character", "maiden_name",
                "place_of_birth", "residence_location", "citizenship",
                "occupation", "job_title", "employer", "awards_honors",
                "criminal_record", "legal_issues", "political_affiliation",
                "contact_information"
            ]
        elif entity_type == "company":
            return [
                "date_of_incorporation", "year_established", "company_age",
                "legal_entity_identifier", "registration_number", "tax_id",
                "business_activity_type", "industry_sector", "company_size",
                "headquarters_location", "registered_address", "operating_locations",
                "ceo_founder", "key_executives", "board_members",
                "parent_company", "subsidiaries", "ownership_structure",
                "revenue", "market_capitalization", "employee_count",
                "stock_symbol", "exchange_listing", "financial_status",
                "legal_status", "business_license", "regulatory_compliance",
                "website", "contact_information", "products_services", "competitors", "partnerships",
                "mergers_acquisitions", "legal_issues", "bankruptcy_status"
            ]
        else:
            # Fallback to combined fields for unknown types
            return [
                "date_of_birth", "year_of_birth", "age", "gender", "nationality",
                "date_of_incorporation", "business_activity_type", "location",
                "full_name", "legal_entity_identifier", "status_alive_deceased"
            ]
        
    async def extract_entity_info(
        self,
        content: str,
        entity_name: str,
        entity_type: str,
        fields: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Extract structured information about an entity from the given content.
        
        Args:
            content: The text content to analyze
            entity_name: Name of the entity to extract information about
            entity_type: Type of entity ('individual' or 'company')
            fields: List of specific fields to extract (e.g., ['date_of_birth', 'education'])
            keywords: Optional list of keywords to refine extraction
            **kwargs: Additional parameters for the API call
            
        Returns:
            Dict containing the extracted information
        """
        if not fields:
            fields = self._get_fields_for_entity_type(entity_type)
        
        # Get current date for age calculations
        current_year = datetime.now().year
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        keywords_context = ""
        if keywords:
            keywords_context = f"\n\nUSER SEARCH KEYWORDS: {', '.join(keywords)}\nUse these keywords to help determine if this is the correct person and to extract relevant information."
            
        entity_context = "person" if entity_type == "individual" else "company/organization"
        
        prompt = f"""
        You are an expert information extraction system analyzing web content for a SPECIFIC {entity_context}.
        
        TARGET {entity_type.upper()}: '{entity_name}'
        ENTITY TYPE: {entity_type}
        CURRENT DATE: {current_date}
        CURRENT YEAR: {current_year}{keywords_context}
        
        CRITICAL MATCHING CRITERIA:
        1. EXACT NAME MATCHING: The entity name must be EXACTLY '{entity_name}' or extremely close variations
        2. STRICT NAME VALIDATION: 
           - Accept: Exact matches, minor spelling variations (1-2 character differences), titles (Dr., Mr., Ltd., Limited)
           - REJECT: Different company names, different first/last names, acronym mismatches
           - Calculate character-level similarity - must be ≥95% for same_as_input=true
        3. KEYWORD ALIGNMENT: If keywords provided, the entity's details should align with the search context
        4. CONTEXT VERIFICATION: Ensure extracted details are consistent with the search intent
        5. ULTRA-STRICT VALIDATION: Only extract if you're 100% confident this is the exact target entity
        
        ADVANCED EXTRACTION RULES:
        
        DATE, DOB, YOB & AGE NORMALIZATION (SIMPLE STRINGS ONLY):
        - If the article explicitly states an age with time context (e.g., "55" in 2024), set extracted_info.age to that FIXED value as a STRING, e.g., "55 (as of 2024)".
        - If DOB is found, compute the precise current age as of CURRENT DATE and set extracted_info.age to a STRING, e.g., "56 (as of {current_date})".
        - For YOB and DOB fields, return simple strings and include brief context inline when derived, e.g.,
          * year_of_birth: "1970 (from article)" or "1970 (calculated from 55 as of 2024)"
          * date_of_birth: "1970-05-12 (from article)"
        - If both original and calculated values are relevant, you may concatenate in the same field separated by "; ", e.g.,
          * age: "55 (as of 2024); 56 (as of {current_date})"
        
        
        CONTEXTUAL VALIDATION:
        - Cross-reference extracted info with search keywords for consistency
        - If location/profession in keywords doesn't match extracted data, lower confidence
        - Prioritize information that aligns with user's search intent
        
        ENHANCED FIELD EXTRACTION:
        - Extract article publication date when available
        - Note time context for all age-related information
        - Capture family member ages and relationships
        - Include employment periods and career timeline
        - Extract residence vs workplace locations separately
        
        ULTRA-STRICT NAME MATCHING ALGORITHM:
        - Calculate character-level similarity score (must be ≥0.95 for same_as_input=true)
        - MANDATORY CHECKS:
          a) Core name components must match
          b) Company suffixes are interchangeable
          c) Word order matters
          d) Acronym expansion: If target has acronym, found name must expand it correctly
        - AUTOMATIC REJECTION CRITERIA:
          * Different core business names
          * Missing key letters in acronyms
          * Completely different entity types
          * Geographic mismatches without clear connection
        - VALIDATION PROCESS:
          1. Remove common suffixes
          2. Compare core names character by character
          3. Check for acronym consistency
          4. Verify business context alignment
        
        Return STRICT JSON:
        {{
            "detected_entity_name": string | null,
            "aliases": string[],
            "same_as_input": boolean,
            "name_similarity_score": number (0-1),
            "confidence": number (0-1),
            "keyword_alignment_score": number (0-1),
            "extracted_info": {{
                {', '.join([f'"{field}": "value or null"' for field in fields])}
3. Check for acronym consistency
          4. Verify business context alignment
        
        Return STRICT JSON:
        {{
            "detected_entity_name": string | null,
            "aliases": string[],
            "same_as_input": boolean,
            "name_similarity_score": number (0-1),
            "confidence": number (0-1),
            "keyword_alignment_score": number (0-1),
            "extracted_info": {{
                {', '.join([f'"{field}": "value or null"' for field in fields])},
                "age_detail": {{
                  "original": {{ "value": number | null, "as_of": number | string | null }},
                  "calculated": {{ "value": number | null, "value_range": string | null, "as_of": string | null }}
                }},
                "yob_detail": {{
                  "original": {{ "value": number | null }},
                  "calculated": {{ "value": number | null, "as_of": number | null }}
                }},
                "dob_detail": {{
                  "original": {{ "value": string | null }}
                }}
            }},
            "article_publication_date": string | null,
            "extraction_notes": string
        }}

        Text to analyze:
        {content}

        Respond with ONLY the JSON object, no markdown fences."""
        
        try:
            logger.info(
                f"Gemini.extract_entity_info start | model={self.model} | entity='{entity_name}' | content_len={len(content or '')}"
            )
            response = await self._chat_completion_with_retry(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=8000,
                model=self.model,
            )
            
            if not response or not response.choices:
                logger.warning("Empty response from LLM extraction - API keys may be exhausted")
                return {
                    "entity_name": entity_name,
                    "extracted_info": {field: None for field in fields},
                    "field_sources": {},
                    "sources": [],
                    "error": "LLM API unavailable - all keys exhausted",
                    "confidence": 0.0
                }
            
            # Extract the JSON response
            result_text = response.choices[0].message.content
            
            # Clean the response to ensure it's valid JSON
            result_text = result_text.strip()
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
                
            logger.info(
                f"Gemini.extract_entity_info response received | len={len(result_text)} | preview={result_text[:300].replace('\n',' ')}"
            )
            result = json.loads(result_text)
            # Normalize minimal expected keys
            detected_name = result.get("detected_entity_name")
            aliases = result.get("aliases", []) or []
            same_as = bool(result.get("same_as_input"))
            confidence = float(result.get("confidence", 0.0) or 0.0)
            name_similarity = float(result.get("name_similarity_score", 0.0) or 0.0)
            keyword_alignment = float(result.get("keyword_alignment_score", 0.0) or 0.0)
            extracted_info = result.get("extracted_info", {}) or {}
            article_date = result.get("article_publication_date")
            extraction_notes = result.get("extraction_notes", "")
            
            # Build field-specific sources - each field that has data gets the source URL
            field_sources = {}
            # Get source URL from kwargs if provided, otherwise default to "web"
            source_url = kwargs.get("source_url", "web")
            
            for field_name, field_value in extracted_info.items():
                if field_value is not None and field_value != "":
                    field_sources[field_name] = [source_url]
            
            return {
                "query_name": entity_name,
                "detected_entity_name": detected_name,
                "aliases": aliases,
                "same_as_input": same_as,
                "name_similarity_score": name_similarity,
                "keyword_alignment_score": keyword_alignment,
                "extracted_info": extracted_info,
                "field_sources": field_sources,  # Sources tied to specific fields
                "article_publication_date": article_date,
                "extraction_notes": extraction_notes,
                "sources": [source_url],
                "confidence": confidence,
                "keywords_used": keywords or []
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            # Return a default response with null values if JSON parsing fails
            return {
                "entity_name": entity_name,
                "extracted_info": {field: None for field in fields},
                "field_sources": {},
                "sources": [],
                "error": f"Failed to parse response: {str(e)}",
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"Error in Gemini API call (extract_entity_info): {str(e)}")
            raise
    
    async def research_entity(
        self,
        entity_name: str,
        content_chunks: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Research an entity by analyzing multiple content chunks.
        
        Args:
            entity_name: Name of the entity to research
            content_chunks: List of text chunks to analyze
            **kwargs: Additional parameters for the API call
            
        Returns:
            Consolidated research results
        """
        if not content_chunks:
            return {
                "entity_name": entity_name,
                "extracted_info": {},
                "field_sources": {},
                "sources": [],
                "confidence": 0.0,
                "chunks_processed": 0,
                "error": "No content chunks provided"
            }

        tasks = []
        for chunk in content_chunks:
            if not chunk or not chunk.strip():
                continue
                
            tasks.append(
                self.extract_entity_info(
                    content=chunk,
                    entity_name=entity_name,
                    **kwargs
                )
            )
            
        if not tasks:
            return {
                "entity_name": entity_name,
                "extracted_info": {},
                "field_sources": {},
                "sources": [],
                "confidence": 0.0,
                "chunks_processed": 0,
                "error": "No valid content chunks to process"
            }
            
        # Process chunks in parallel
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Combine results
            combined = {
                "entity_name": entity_name,
                "extracted_info": {},
                "field_sources": {},
                "sources": [],
                "confidence": 0.0,
                "chunks_processed": 0,
                "errors": []
            }
            
            # Aggregate results from all chunks
            for result in results:
                if isinstance(result, Exception):
                    error_msg = str(result)
                    logger.warning(f"Error processing chunk: {error_msg}")
                    combined["errors"].append(error_msg)
                    continue
                    
                combined["chunks_processed"] += 1
                
                if "extracted_info" in result:
                    for key, value in result.get("extracted_info", {}).items():
                        if value is not None and (key not in combined["extracted_info"] or combined["extracted_info"][key] is None):
                            combined["extracted_info"][key] = value
                    
                    # Merge field-specific sources
                    if "field_sources" in result:
                        for field_name, field_sources in result.get("field_sources", {}).items():
                            if field_name not in combined["field_sources"]:
                                combined["field_sources"][field_name] = []
                            combined["field_sources"][field_name].extend(field_sources)
                    
                    if "sources" in result:
                        combined["sources"].extend([s for s in result["sources"] if s])
                    
                    if "confidence" in result:
                        combined["confidence"] = max(combined["confidence"], result["confidence"])
            
            # Clean up sources and field sources
            combined["sources"] = list(set(combined["sources"]))
            
            # Clean up field sources - remove duplicates for each field
            for field_name in combined["field_sources"]:
                combined["field_sources"][field_name] = list(set(combined["field_sources"][field_name]))
            
            # If we have no results but have errors, include them in the response
            if not combined["extracted_info"] and combined["errors"]:
                combined["error"] = " | ".join(combined["errors"][:3])  # Include first 3 errors
                
            return combined
            
        except Exception as e:
            logger.error(f"Error in research_entity: {str(e)}")
            return {
                "entity_name": entity_name,
                "extracted_info": {},
                "field_sources": {},
                "sources": [],
                "confidence": 0.0,
                "chunks_processed": 0,
                "error": f"Failed to process research: {str(e)}"
            }

    async def process_search_results(self, entity_name: str, search_results: List[Dict]) -> Dict[str, Any]:
        """
        Process search results to extract entity information.
        
        Args:
            entity_name: Name of the entity to search for
            search_results: List of search results from search engines
            
        Returns:
            Dictionary containing consolidated entity information
        """
        if not search_results:
            return {
                "entity_name": entity_name,
                "extracted_info": {},
                "field_sources": {},
                "sources": [],
                "error": "No search results provided"
            }
        
        try:
            # Extract content from search results
            contents = [
                f"Title: {result.get('title', '')}\nSnippet: {result.get('snippet', '')}"
                for result in search_results
                if result.get('title') or result.get('snippet')
            ]
            
            if not contents:
                return {
                    "entity_name": entity_name,
                    "extracted_info": {},
                    "field_sources": {},
                    "sources": [],
                    "error": "No valid content found in search results"
                }
            
            # Combine all content into a single text
            combined_content = "\n\n---\n\n".join(contents)
            
            # Extract information using the LLM
            return await self.extract_entity_info(
                content=combined_content,
                entity_name=entity_name
            )
            
        except Exception as e:
            logger.error(f"Error in process_search_results: {str(e)}")
            return {
                "entity_name": entity_name,
                "profiles": [],
                "field_sources": {},
                "sources": [],
                "error": f"Failed to process search results: {str(e)}"
            }

    async def consolidate_clusters(self, entity_name: str, entity_type: str, profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Final LLM pass to combine/segregate profiles into canonical entities.

        Args:
            entity_name: The original query name
            entity_type: Type of entity ('individual' or 'company')
            profiles: List of per-page profiles with keys: detected_entity_name, same_as_input, extracted_info, source_url, confidence

        Returns:
            Dict with 'entities': [ { canonical_name, same_as_query, combined_fields, member_profile_indexes } ]
        """
        try:
            logger.info(
                f"Gemini.consolidate_clusters start | model={self.model} | entity='{entity_name}' | profiles={len(profiles)}"
            )
            # Compact the profiles to reduce tokens
            compact = []
            for idx, p in enumerate(profiles):
                compact.append({
                    "index": idx,
                    "detected_entity_name": p.get("detected_entity_name"),
                    "same_as_input": bool(p.get("same_as_input")),
                    "confidence": float(p.get("confidence", 0.0) or 0.0),
                    "source_url": p.get("source_url"),
                    "extracted_info": p.get("extracted_info", {}) or {}
                })

            system_prompt = (
                "You are an expert at consolidating entity profiles for the same person. "
                "Given multiple profiles that may refer to the same or different people, "
                "group them into distinct entities and combine information appropriately. "
                "CRITICAL: Only merge profiles that clearly refer to the same person based on name similarity AND consistent non-null field values. "
                "If non-null values conflict significantly, treat as different people."
            )
            
            user_prompt = (
                f"Target person: '{entity_name}'\n\n"
                "ULTRA-STRICT CONSOLIDATION RULES:\n"
                "1. EXACT NAME MATCHING: Only merge profiles with ≥95% character-level similarity\n"
                "2. CORE NAME VALIDATION: \n"
                "   - Each letter in acronyms must match\n"
                "   - Company suffixes (Ltd/Limited/Inc) are interchangeable but core names must be identical\n"
                "3. DETAIL CONSISTENCY: Compare ALL non-null field values - any conflicts = different entities\n"
                "4. KEYWORD ALIGNMENT: Consider keyword_alignment_score - scores <0.8 suggest different entity\n"
                "5. GEOGRAPHIC CONSISTENCY: Different countries/regions require 99% confidence to merge\n"
                "6. TEMPORAL CONSISTENCY: Check age progression and timeline consistency\n"
                "7. BUSINESS CONTEXT: Different business types/industries require additional validation\n"
                "8. ULTRA-CONSERVATIVE: When ANY doubt exists, keep separate - precision over recall\n\n"
                "ENHANCED VALIDATION:\n"
                "- Name similarity must be calculated and ≥0.95 for merging\n"
                "- Core business name components must be identical\n"
                "- Location conflicts (e.g., USA vs Columbia) require additional validation\n"
                "- Age inconsistencies must be explained by article dates\n"
                "- Professional/educational backgrounds should align\n"
                "- Acronym letters must match exactly in business names\n\n"
                "Profiles (JSON):\n" + json.dumps(compact, ensure_ascii=False) + "\n\n"
                "Return STRICT JSON with key 'entities' array containing objects with:\n"
                "- canonical_name: string (best full name for the entity)\n"
                "- same_as_query: boolean (true if same person as input query)\n"
                "- name_similarity_to_query: number (0-1, calculated similarity to input name)\n"
                "- consolidation_confidence: number (0-1, confidence in merging decision)\n"
                "- combined_fields: object with merged non-conflicting values (null if unknown/conflicting)\n"
                "- member_profile_indexes: number[] (the 'index' values from input profiles for this entity)\n"
                "- consolidation_notes: string (explanation of merging/separation decisions)\n"
                "No markdown code fences."
            )

            response = await self._chat_completion_with_retry(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=8000,
                model=self.model,
            )

            content = response.choices[0].message.content
            if content is None:
                logger.error("Gemini response content is None")
                return {"entities": []}
            
            result_text = content.strip()
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]

            logger.info(
                f"Gemini.consolidate_clusters response received | len={len(result_text)} | preview={result_text[:200].replace('\n',' ')}"
            )
            data = json.loads(result_text)
            
            # Handle case where LLM returns a list directly instead of {"entities": [...]}
            if isinstance(data, list):
                entities = data
            elif isinstance(data, dict):
                entities = data.get("entities", [])
            else:
                logger.warning(f"Unexpected data type from LLM: {type(data)}")
                entities = []
            # Basic validation/normalization
            norm_entities = []
            for e in entities:
                norm_entities.append({
                    "canonical_name": e.get("canonical_name"),
                    "same_as_query": bool(e.get("same_as_query")),
                    "name_similarity_to_query": float(e.get("name_similarity_to_query", 0.0) or 0.0),
                    "consolidation_confidence": float(e.get("consolidation_confidence", 0.0) or 0.0),
                    "combined_fields": e.get("combined_fields", {}) or {},
                    "member_profile_indexes": e.get("member_profile_indexes", []) or [],
                    "consolidation_notes": e.get("consolidation_notes", "")
                })
            return {"entities": norm_entities}
        except Exception as e:
            logger.error(f"Error in consolidate_clusters: {str(e)}")
            return {"entities": []}

    async def _chat_completion_with_retry(
        self,
        *,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        model: Optional[str] = None,
    ):
        """Wrapper for chat.completions.create with robust retry logic.
        - Handles Gemini 429 with optional RetryInfo retryDelay
        - Retries transient timeouts/connection errors with exponential backoff
        - Tries all available API keys before giving up
        """
        if not self.client:
            raise RuntimeError("LLM client is not initialized")
        use_model = model or self.model

        attempts = 0
        max_attempts = 6
        backoff = 2.0
        key_rotation_attempts = 0
        max_key_rotations = len(self.api_key_rotator.keys) * 2  # Try each key twice

        while True:
            try:
                return await self.client.chat.completions.create(
                    model=use_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except RateLimitError as e:
                attempts += 1
                # Mark current key as failed and try rotating to next key
                self.api_key_rotator.mark_key_failed(self.current_api_key, f"Rate limit error: {str(e)}")
                
                # Check if we have any available keys left
                if not self.api_key_rotator.has_available_keys():
                    logger.error(f"All Gemini API keys exhausted after rate limit errors")
                    # Return None to indicate failure - let calling code handle graceful degradation
                    return None
                
                self._refresh_client_with_new_key()
                key_rotation_attempts += 1
                
                # If we've tried all keys multiple times, give up
                if key_rotation_attempts >= max_key_rotations:
                    logger.error(f"Exhausted all Gemini API keys after {key_rotation_attempts} rotations")
                    raise
                
                retry_sec = self._extract_retry_after_seconds(e)
                if retry_sec is None:
                    retry_sec = min(5.0, backoff)  # Reduced from 30s to 5s
                    backoff = min(15.0, backoff * 1.5)  # Reduced max backoff from 60s to 15s
                    
                logger.warning(f"ai.rate_limited retry_in_s={retry_sec:.1f} attempt={attempts} key_rotation={key_rotation_attempts}")
                await asyncio.wait_for(asyncio.sleep(retry_sec), timeout=min(retry_sec + 5.0, 35.0))
            except (APITimeoutError, APIConnectionError) as e:
                attempts += 1
                delay = min(3.0, backoff)  # Reduced from 10s to 3s
                backoff = min(15.0, backoff * 1.5)  # Reduced max backoff
                if attempts >= max_attempts:
                    logger.warning(f"ai.retry_exhausted event=transient_error attempts={attempts} last_error={e}")
                    raise
                logger.warning(f"ai.transient_error retry_in_s={delay:.1f} attempt={attempts}/{max_attempts} error={e}")
                await asyncio.wait_for(asyncio.sleep(delay), timeout=min(delay + 2.0, 12.0))
            except APIStatusError as e:
                status = getattr(e, "status_code", None)
                if status == 429:
                    attempts += 1
                    # Mark current key as failed and try rotating to next key
                    self.api_key_rotator.mark_key_failed(self.current_api_key, f"API Status 429 error: {str(e)}")
                    
                    # Check if we have any available keys left
                    if not self.api_key_rotator.has_available_keys():
                        logger.error(f"All Gemini API keys exhausted after 429 errors")
                        # Return None to indicate failure - let calling code handle graceful degradation
                        return None
                    
                    self._refresh_client_with_new_key()
                    key_rotation_attempts += 1
                    
                    # If we've tried all keys multiple times, give up
                    if key_rotation_attempts >= max_key_rotations:
                        logger.error(f"Exhausted all Gemini API keys after {key_rotation_attempts} rotations")
                        raise
                    
                    retry_sec = self._extract_retry_after_seconds(e)
                    if retry_sec is None:
                        retry_sec = min(5.0, backoff)  # Reduced from 30s
                        backoff = min(15.0, backoff * 1.5)  # Reduced max backoff
                    logger.warning(f"ai.rate_limited(APIStatus) retry_in_s={retry_sec:.1f} key_rotation={key_rotation_attempts}")
                    await asyncio.wait_for(asyncio.sleep(retry_sec), timeout=min(retry_sec + 5.0, 35.0))
                elif status in [401, 403]:
                    # Authentication/authorization errors - mark key as failed and rotate
                    self.api_key_rotator.mark_key_failed(self.current_api_key, f"Auth error {status}: {str(e)}")
                    
                    # Check if we have any available keys left
                    if not self.api_key_rotator.has_available_keys():
                        logger.error(f"All Gemini API keys exhausted after auth errors")
                        # Return None to indicate failure - let calling code handle graceful degradation
                        return None
                    
                    self._refresh_client_with_new_key()
                    key_rotation_attempts += 1
                    
                    # If we've tried all keys multiple times, give up
                    if key_rotation_attempts >= max_key_rotations:
                        logger.error(f"Exhausted all Gemini API keys after {key_rotation_attempts} rotations")
                        raise
                        
                    await asyncio.wait_for(asyncio.sleep(min(backoff, 5.0)), timeout=10.0)  # Cap at 5s
                    backoff = min(15.0, backoff * 1.5)  # Reduced max backoff
                else:
                    raise

    def _extract_retry_after_seconds(self, err: Exception) -> Optional[float]:
        """Try to extract retry delay seconds from OpenAI/Gemini error payload.
        Looks for Google RPC RetryInfo: details[{ '@type': '...RetryInfo', retryDelay: '19s' }]
        Returns float seconds or None when not available.
        """
        try:
            response = getattr(err, "response", None)
            if response is not None:
                try:
                    body = response.json()
                except Exception:
                    body = getattr(err, "body", None) or getattr(err, "error", None)
            else:
                body = getattr(err, "body", None)
        except Exception:
            body = None

        try:
            if isinstance(body, dict) and "error" in body:
                details = body["error"].get("details", [])
                for d in details:
                    if isinstance(d, dict) and str(d.get("@type", "")).endswith("RetryInfo"):
                        delay = d.get("retryDelay")
                        if isinstance(delay, str) and delay.endswith("s"):
                            return float(delay[:-1])
                        if isinstance(delay, (int, float)):
                            return float(delay)
        except Exception:
            pass
        return None
