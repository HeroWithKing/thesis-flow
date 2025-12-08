"""
Advanced ArXiv search tool based on AI-Researcher project search strategies.
This module implements enhanced search functionality inspired by AI-Researcher's approach.
"""

import arxiv
import logging
from typing import Dict, List, Any, Optional
from langchain_core.tools import BaseTool
from pydantic import Field
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)


class AiInspiredArxivToolWrapper(BaseTool):
    """
    Advanced ArXiv search tool wrapper based on AI-Researcher project strategies.
    Implements multi-strategy search with query expansion, category detection, and relevance scoring.
    """
    name: str = Field(default="ai_inspired_arxiv_search")
    description: str = Field(default="Advanced arXiv search tool with multi-strategy approach for academic papers")
    max_search_results: int = Field(default=5, description="Maximum number of search results to return")
    
    def __init__(self, max_search_results: int = 5):
        super().__init__()
        self.max_search_results = max_search_results

    def _run(self, query: str) -> str:
        """Synchronous version of the tool."""
        try:
            return self._perform_advanced_search(query)
        except Exception as e:
            logger.error(f"Error in AiInspiredArxivToolWrapper._run: {str(e)}")
            return f"Error: {str(e)}"

    async def _arun(self, query: str):
        """Asynchronous version of the tool."""
        try:
            return self._perform_advanced_search(query)
        except Exception as e:
            logger.error(f"Error in AiInspiredArxivToolWrapper._arun: {str(e)}")
            return f"Error: {str(e)}"

    def _perform_advanced_search(self, query: str) -> str:
        """
        Perform advanced search using multiple strategies inspired by AI-Researcher project.
        """
        logger.info(f"Performing advanced arXiv search for query: {query}")
        
        # Strategy 1: Direct keyword search with better arXiv-specific query syntax
        direct_results = self._search_by_keywords(query)
        
        # Strategy 2: Title-only search for more precision
        title_results = self._search_in_titles(query)
        
        # Strategy 3: Query expansion and vocabulary expansion
        expanded_results = self._search_with_expanded_query(query)
        
        # Strategy 4: Category-based search
        category_results = self._search_by_category(query)
        
        # Strategy 5: Recent papers search to get latest developments
        recent_results = self._search_recent_papers(query)
        
        # Combine and deduplicate results with improved scoring
        all_results = self._combine_and_deduplicate_results(
            direct_results, title_results, expanded_results, category_results, recent_results
        )
        
        # Filter results by relevance to life sciences and AI
        filtered_results = self._filter_by_domain_relevance(all_results, query)
        
        # Enhance relevance with computed scoring
        enhanced_results = self._compute_comprehensive_relevance(filtered_results, query)
        
        # Sort by relevance (computed score, then by date)
        sorted_results = sorted(enhanced_results, key=lambda x: (x.get('relevance_score', 0), x.get('published', '')), reverse=True)
        
        # Limit results to max_search_results
        limited_results = sorted_results[:self.max_search_results]
        
        if not limited_results:
            # Fallback to basic search if no results found
            fallback_results = self._basic_fallback_search(query)
            if fallback_results:
                limited_results = fallback_results[:self.max_search_results]
        
        if not limited_results:
            return f"No papers found for query: {query}"
        
        # Format results
        formatted_results = self._format_results(limited_results)
        return formatted_results

    def _search_by_keywords(self, query: str) -> List[Dict[str, Any]]:
        """Search using the original query with arXiv-specific syntax."""
        try:
            # Use arXiv syntax for better search
            search_query = query.strip()
            
            search = arxiv.Search(
                query=search_query,
                max_results=self.max_search_results,
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            client = arxiv.Client()
            results = []
            
            for result in client.results(search):
                paper_data = {
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,  # Truncate long summaries
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'primary_category': result.primary_category,
                    'arxiv_id': result.get_short_id(),
                    'relevance_score': 0.7  # Default relevance score
                }
                results.append(paper_data)
            
            logger.info(f"Direct keyword search found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error in _search_by_keywords: {str(e)}")
            return []

    def _search_in_titles(self, query: str) -> List[Dict[str, Any]]:
        """Search specifically in titles for better precision."""
        try:
            # Search in title using arXiv syntax
            search_query = f'ti:"{query}"'  # Search in title field
            
            search = arxiv.Search(
                query=search_query,
                max_results=max(3, self.max_search_results // 2),  # Use fewer results for title search
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            client = arxiv.Client()
            results = []
            
            for result in client.results(search):
                paper_data = {
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'primary_category': result.primary_category,
                    'arxiv_id': result.get_short_id(),
                    'relevance_score': 0.9  # Higher relevance score for title matches
                }
                results.append(paper_data)
            
            logger.info(f"Title-only search found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error in _search_in_titles: {str(e)}")
            return []

    def _search_with_expanded_query(self, query: str) -> List[Dict[str, Any]]:
        """Search with expanded vocabulary and related terms."""
        try:
            # Expand query with synonyms and related terms
            expanded_query = self._expand_academic_query(query)
            
            if expanded_query == query or not expanded_query:
                # If no meaningful expansion was possible, return empty list to avoid duplicates
                return []
            
            search = arxiv.Search(
                query=expanded_query,
                max_results=max(3, self.max_search_results // 2),  # Use fewer results for expanded search
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            client = arxiv.Client()
            results = []
            
            for result in client.results(search):
                paper_data = {
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'primary_category': result.primary_category,
                    'arxiv_id': result.get_short_id(),
                    'relevance_score': 0.6  # Standard relevance score
                }
                results.append(paper_data)
            
            logger.info(f"Expanded query search found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error in _search_with_expanded_query: {str(e)}")
            return []

    def _search_by_category(self, query: str) -> List[Dict[str, Any]]:
        """Search within relevant arXiv categories."""
        try:
            # Detect relevant categories based on the query
            relevant_categories = self._detect_relevant_arxiv_categories(query)
            
            if not relevant_categories:
                return []
            
            # Search in each relevant category
            results = []
            for category in relevant_categories[:2]:  # Limit to top 2 categories to avoid too many results
                search = arxiv.Search(
                    query=f"cat:{category} AND ({query})",
                    max_results=max(2, self.max_search_results // 3),
                    sort_by=arxiv.SortCriterion.Relevance
                )
                
                client = arxiv.Client()
                
                for result in client.results(search):
                    paper_data = {
                        'title': result.title,
                        'authors': [author.name for author in result.authors],
                        'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                        'published': result.published.strftime('%Y-%m-%d'),
                        'pdf_url': result.pdf_url,
                        'categories': result.categories,
                        'primary_category': result.primary_category,
                        'arxiv_id': result.get_short_id(),
                        'relevance_score': 0.65  # Good relevance for category-specific search
                    }
                    results.append(paper_data)
            
            logger.info(f"Category-based search found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error in _search_by_category: {str(e)}")
            return []

    def _search_recent_papers(self, query: str) -> List[Dict[str, Any]]:
        """Search for recent papers to get the latest developments."""
        try:
            # Search for papers from the last year to get latest developments
            one_year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            search_query = f'{query} AND submittedDate:[{one_year_ago} TO Now]'
            
            search = arxiv.Search(
                query=search_query,
                max_results=max(2, self.max_search_results // 3),
                sort_by=arxiv.SortCriterion.SubmittedDate
            )
            
            client = arxiv.Client()
            results = []
            
            for result in client.results(search):
                paper_data = {
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'primary_category': result.primary_category,
                    'arxiv_id': result.get_short_id(),
                    'relevance_score': 0.75  # High relevance for recent papers
                }
                results.append(paper_data)
            
            logger.info(f"Recent papers search found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error in _search_recent_papers: {str(e)}")
            # If date-based search fails, fallback to regular search
            try:
                search = arxiv.Search(
                    query=query,
                    max_results=max(2, self.max_search_results // 3),
                    sort_by=arxiv.SortCriterion.SubmittedDate
                )
                
                client = arxiv.Client()
                results = []
                
                for result in client.results(search):
                    paper_data = {
                        'title': result.title,
                        'authors': [author.name for author in result.authors],
                        'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                        'published': result.published.strftime('%Y-%m-%d'),
                        'pdf_url': result.pdf_url,
                        'categories': result.categories,
                        'primary_category': result.primary_category,
                        'arxiv_id': result.get_short_id(),
                        'relevance_score': 0.75  # High relevance for recent papers
                    }
                    results.append(paper_data)
                
                logger.info(f"Recent papers search (fallback) found {len(results)} results")
                return results
            except:
                return []

    def _basic_fallback_search(self, query: str) -> List[Dict[str, Any]]:
        """Fallback search with broader parameters."""
        try:
            # Simple search without constraints as a last resort
            search = arxiv.Search(
                query=query,
                max_results=self.max_search_results,
                sort_by=arxiv.SortCriterion.SubmittedDate  # Sort by recent to get latest research
            )
            
            client = arxiv.Client()
            results = []
            
            for result in client.results(search):
                paper_data = {
                    'title': result.title,
                    'authors': [author.name for author in result.authors],
                    'summary': result.summary[:500] + "..." if len(result.summary) > 500 else result.summary,
                    'published': result.published.strftime('%Y-%m-%d'),
                    'pdf_url': result.pdf_url,
                    'categories': result.categories,
                    'primary_category': result.primary_category,
                    'arxiv_id': result.get_short_id(),
                    'relevance_score': 0.3  # Lower relevance for fallback results
                }
                results.append(paper_data)
            
            logger.info(f"Fallback search found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"Error in _basic_fallback_search: {str(e)}")
            return []

    def _expand_academic_query(self, query: str) -> str:
        """Expand academic query with related terms and synonyms."""
        query_lower = query.lower()
        
        # More comprehensive academic term expansions
        expansions = {
            "liquid neural network": "liquid neural network OR liquid state machine OR reservoir computing OR echo state network OR LSM OR ESN OR neuromorphic",
            "machine learning": "machine learning OR ml OR algorithm OR artificial intelligence OR ai",
            "deep learning": "deep learning OR neural network OR cnn OR rnn OR lstm OR transformer OR dnn",
            "artificial intelligence": "artificial intelligence OR ai OR cognitive computing OR machine intelligence",
            "computer vision": "computer vision OR image processing OR object detection OR image recognition OR cv",
            "natural language processing": "natural language processing OR nlp OR text mining OR transformer OR bert OR gpt",
            "reinforcement learning": "reinforcement learning OR rl OR q-learning OR deep rl OR policy gradient",
            "data science": "data science OR big data OR data mining OR analytics OR statistical learning",
            "blockchain": "blockchain OR cryptocurrency OR bitcoin OR smart contract OR distributed ledger",
            "quantum computing": "quantum computing OR quantum algorithm OR qubit OR quantum information",
            "cryptocurrency": "cryptocurrency OR bitcoin OR blockchain OR digital currency OR ethereum",
            "neural architecture": "neural architecture OR topology OR network structure OR connectivity OR weights",
            "reservoir computing": "reservoir computing OR echo state network OR liquid state machine OR recurrent network"
        }
        
        # Find best matching expansion
        expanded_query = query
        for term, expansion in expansions.items():
            if term in query_lower:
                # Combine original query with expansion
                expanded_query = f'({query}) OR ({expansion})'
                break  # Use the first match for simplicity
        
        return expanded_query

    def _detect_relevant_arxiv_categories(self, query: str) -> List[str]:
        """Detect relevant arXiv categories based on query content."""
        query_lower = query.lower()
        
        # Academic domains to arXiv categories mapping
        domain_categories = {
            'liquid neural network': ['cs.NE', 'cs.LG', 'cs.AI'],  # Neural and Evolutionary Computing, Machine Learning, Artificial Intelligence
            'reservoir computing': ['cs.NE', 'cs.LG', 'nlin.AO'],  # Neural and Evolutionary Computing, Machine Learning, Adaptation and Self-Organizing Systems
            'echo state network': ['cs.NE', 'cs.LG'],
            'liquid state machine': ['cs.NE', 'cs.LG'],
            'neuromorphic': ['cs.NE', 'cs.AI'],
            'machine learning': ['cs.LG', 'stat.ML'],
            'artificial intelligence': ['cs.AI'],
            'computer vision': ['cs.CV'],
            'natural language': ['cs.CL'],
            'neural networks': ['cs.NE', 'cs.LG'],
            'algorithms': ['cs.DS'],
            'data science': ['cs.DB', 'cs.IR'],
            'bioinformatics': ['q-bio.BM'],
            'quantum': ['quant-ph'],
            'robotics': ['cs.RO'],
            'security': ['cs.CR'],
            'cryptography': ['cs.CR'],
            'mathematics': ['math.NA', 'math.ST'],
            'statistics': ['stat.TH', 'stat.ME'],
            'life science': ['q-bio', 'q-bio.BM', 'q-bio.GN', 'q-bio.MN', 'q-bio.NC', 'q-bio.OT', 'q-bio.PE', 'q-bio.QM', 'q-bio.SC', 'q-bio.TO'],
            'biology': ['q-bio', 'q-bio.BM', 'q-bio.GN', 'q-bio.MN', 'q-bio.NC', 'q-bio.OT', 'q-bio.PE', 'q-bio.QM', 'q-bio.SC', 'q-bio.TO'],
            'medicine': ['q-bio', 'q-bio.MN'],
            'genomic': ['q-bio.GN', 'q-bio.MN'],
            'biomedical': ['q-bio', 'q-bio.MN', 'eess.IV'],  # Biomedical Engineering, Image and Video Processing
            'drug': ['q-bio', 'q-bio.MN'],
            'pharma': ['q-bio', 'q-bio.MN'],
            'disease': ['q-bio', 'q-bio.MN'],
            'health': ['q-bio', 'eess.IV'],
            'healthcare': ['q-bio', 'eess.IV'],
            'clinical': ['q-bio', 'eess.IV'],
            'ai4s': ['cs.AI', 'cs.LG', 'cs.CE', 'physics.comp-ph'],  # AI, ML, Computational Engineering, Computational Physics
            'scientific discovery': ['cs.AI', 'cs.LG', 'physics.comp-ph', 'cs.CE'],
            'science': ['physics', 'physics.comp-ph', 'cs.CE', 'cs.AI']
        }
        
        relevant_categories = set()
        
        # Check domain mappings
        for domain, categories in domain_categories.items():
            if domain in query_lower:
                relevant_categories.update(categories)
        
        # If no specific categories found, use life science and AI/ML categories for AI4S queries
        if not relevant_categories and any(word in query_lower for word in 
                                         ['ai', 'artificial intelligence', 'machine learning', 'life science', 
                                         'biology', 'medicine', 'bio', 'genomic', 'drug', 'disease', 'health',
                                         'ai4s', 'scientific discovery', 'science']):
            relevant_categories.update(['q-bio', 'cs.AI', 'cs.LG', 'stat.ML', 'physics.comp-ph'])
        
        # If still no categories found, use general computer science
        if not relevant_categories and any(word in query_lower for word in 
                                         ['computer', 'software', 'algorithm', 'programming', 'code', 'network', 'neural']):
            relevant_categories.update(['cs.AI', 'cs.LG', 'cs.NE'])
        
        # Default to life science and AI categories for general AI4S queries
        if not relevant_categories:
            relevant_categories.update(['cs.AI', 'cs.LG', 'q-bio'])
        
        return list(relevant_categories)

    def _combine_and_deduplicate_results(self, *result_lists) -> List[Dict[str, Any]]:
        """Combine multiple result lists and remove duplicates."""
        all_results = []
        seen_ids = set()  # Use arxiv_id to identify duplicates
        seen_titles = set()  # Fallback to title if no id available
        
        for result_list in result_lists:
            for result in result_list:
                arxiv_id = result.get('arxiv_id', '')
                title = result.get('title', '').lower().strip()
                
                # Use arxiv_id for deduplication if available, otherwise use title
                if arxiv_id and arxiv_id not in seen_ids:
                    all_results.append(result)
                    seen_ids.add(arxiv_id)
                elif not arxiv_id and title not in seen_titles:
                    all_results.append(result)
                    seen_titles.add(title)
                elif arxiv_id and arxiv_id in seen_ids:
                    # Update relevance score if duplicate with higher score is found
                    for i, existing_result in enumerate(all_results):
                        if existing_result.get('arxiv_id', '') == arxiv_id:
                            if result.get('relevance_score', 0) > existing_result.get('relevance_score', 0):
                                all_results[i] = result  # Replace with higher relevance result
                                break
        
        return all_results

    def _compute_comprehensive_relevance(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """Compute a more comprehensive relevance score based on multiple factors."""
        query_lower = query.lower()
        
        for result in results:
            score = result.get('relevance_score', 0.5)
            title = result.get('title', '').lower()
            summary = result.get('summary', '').lower()
            
            # Boost score based on how well the query matches the content
            title_matches = len([word for word in query_lower.split() if word in title])
            summary_matches = len([word for word in query_lower.split() if word in summary])
            
            # Calculate match ratio
            query_words = query_lower.split()
            if query_words:
                title_ratio = title_matches / len(query_words)
                summary_ratio = summary_matches / len(query_words) 
                
                # Add relevance based on content matching
                content_relevance = (title_ratio * 0.4) + (summary_ratio * 0.2)
                score = min(1.0, score + content_relevance)
            
            # Boost recent papers slightly
            try:
                pub_date = datetime.strptime(result.get('published', '1900-01-01'), '%Y-%m-%d')
                years_diff = (datetime.now() - pub_date).days / 365.25
                if years_diff < 1:  # Papers from last year get boost
                    score = min(1.0, score + 0.1)
                elif years_diff < 2:  # Papers from last 2 years get slight boost
                    score = min(1.0, score + 0.05)
            except:
                pass  # If date parsing fails, continue without time-based boost
            
            result['relevance_score'] = score
        
        return results

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """Format search results into a readable string with emphasis on core content and conclusions."""
        if not results:
            return "No results found."
        
        formatted = []
        for i, result in enumerate(results, 1):
            formatted.append(f"Paper {i}:")
            formatted.append(f"Title: {result.get('title', 'N/A')}")
            authors = result.get('authors', [])
            if authors:
                formatted.append(f"Authors: {', '.join(authors[:3])}{'...' if len(authors) > 3 else ''}")  # Limit to first 3 authors
            formatted.append(f"Published: {result.get('published', 'N/A')}")
            formatted.append(f"ArXiv ID: {result.get('arxiv_id', 'N/A')}")
            formatted.append(f"Relevance Score: {result.get('relevance_score', 'N/A'):.2f}")
            
            # Extract core content and conclusions from summary
            summary = result.get('summary', 'N/A')
            formatted.append("Core Content Summary:")
            formatted.append(f"  {summary[:500]}...")  # Extend summary to include more content
            
            # Try to identify key conclusions, methods, and results from the summary
            self._extract_key_insights(formatted, summary)
            
            formatted.append(f"PDF URL: {result.get('pdf_url', 'N/A')}")
            formatted.append(f"Categories: {', '.join(result.get('categories', []))}")
            formatted.append("")  # Empty line for readability
        
        return "\n".join(formatted)

    def _extract_key_insights(self, formatted: List[str], summary: str):
        """Extract key insights like methods, results, and conclusions from the paper summary."""
        summary_lower = summary.lower()
        
        # Look for common patterns that indicate methods, results, conclusions
        import re
        
        # Extract sentences that might contain methods
        method_indicators = ['propose', 'present', 'introduce', 'method', 'approach', 'framework', 'algorithm', 'model', 'technique']
        result_indicators = ['result', 'achieve', 'performance', 'accuracy', 'improve', 'outperform', 'demonstrate', 'show', 'find', 'reveal']
        conclusion_indicators = ['conclude', 'conclusion', 'significant', 'important', 'key', 'main finding', 'future work', 'limitation']
        
        sentences = re.split(r'[.!?]+', summary)
        
        methods = []
        results = []
        conclusions = []
        
        for sentence in sentences:
            sentence_lower = sentence.lower().strip()
            if any(indicator in sentence_lower for indicator in method_indicators):
                methods.append(sentence.strip())
            if any(indicator in sentence_lower for indicator in result_indicators):
                results.append(sentence.strip())
            if any(indicator in sentence_lower for indicator in conclusion_indicators):
                conclusions.append(sentence.strip())
        
        # Add extracted content to formatted output
        if methods:
            formatted.append("  Methods/Approach:")
            for method in methods[:2]:  # Limit to top 2 method sentences
                if len(method) > 10:  # Only include substantial sentences
                    formatted.append(f"    - {method}")
        
        if results:
            formatted.append("  Key Results:")
            for result in results[:2]:  # Limit to top 2 result sentences
                if len(result) > 10:  # Only include substantial sentences
                    formatted.append(f"    - {result}")
        
        if conclusions:
            formatted.append("  Conclusions/Future Work:")
            for conclusion in conclusions[:2]:  # Limit to top 2 conclusion sentences
                if len(conclusion) > 10:  # Only include substantial sentences
                    formatted.append(f"    - {conclusion}")

    def _filter_by_domain_relevance(self, results: List[Dict[str, Any]], original_query: str) -> List[Dict[str, Any]]:
        """Filter results by relevance to life sciences and AI domains."""
        if not results:
            return results
            
        # Define life science and AI related keywords
        life_science_keywords = [
            'biology', 'biological', 'medicine', 'medical', 'bio', 'genomic', 'genome', 
            'protein', 'dna', 'rna', 'cell', 'disease', 'drug', 'pharma', 'neuroscience', 
            'brain', 'cancer', 'therapy', 'treatment', 'diagnosis', 'health', 'healthcare',
            'clinical', 'epidemiology', 'pathology', 'toxicology', 'pharmacology', 'immunology',
            'microbiology', 'neurology', 'cardiology', 'oncology', 'radiology', 'pathogen',
            'therapeutic', 'biomarker', 'biotechnology', 'bioinformatics', 'systems biology',
            'molecular', 'physiology', 'anatomy', 'pediatrics', 'geriatrics', 'surgery',
            'ophthalmology', 'dermatology', 'psychiatry', 'neurology', 'endocrinology'
        ]
        
        ai_keywords = [
            'artificial intelligence', 'ai', 'machine learning', 'deep learning', 'neural',
            'algorithm', 'computer vision', 'natural language processing', 'nlp',
            'reinforcement learning', 'supervised learning', 'unsupervised learning',
            'semi-supervised learning', 'transfer learning', 'few-shot learning',
            'zero-shot learning', 'large language model', 'llm', 'transformer',
            'convolutional', 'recurrent', 'lstm', 'gru', 'gpt', 'bert', 'attention',
            'ai4s', 'scientific discovery', 'automated reasoning', 'knowledge graph',
            'graph neural', 'representation learning', 'foundation model', 'multimodal'
        ]
        
        # Additional keywords that indicate AI for science applications
        ai4s_keywords = [
            'ai for science', 'ai4science', 'ai4s', 'scientific discovery', 
            'computational science', 'science ai', 'scientific ai', 'automated science',
            'intelligent science', 'science automation', 'scientific research ai'
        ]
        
        # Combine all keywords for comprehensive filtering
        domain_keywords = life_science_keywords + ai_keywords
        
        # Also include the original query terms for context
        query_terms = original_query.lower().split()
        
        filtered_results = []
        
        for result in results:
            title = result.get('title', '').lower()
            summary = result.get('summary', '').lower()
            categories = [cat.lower() for cat in result.get('categories', [])]
            
            # Check if it's related to life sciences or AI
            has_life_science = any(keyword in title or keyword in summary for keyword in life_science_keywords)
            has_ai = any(keyword in title or keyword in summary for keyword in ai_keywords)
            has_ai4s = any(keyword in title or keyword in summary for keyword in ai4s_keywords)
            
            # Also check for query-specific terms
            has_query_terms = any(term in title or term in summary for term in query_terms if len(term) > 2)
            
            # Check arXiv categories for life science relevance
            has_life_science_category = any(
                cat.startswith('q-bio') or  # Quantitative Biology
                cat.startswith('stat.ap') or  # Applications (Statistics)
                cat.startswith('eess')  # Electrical Engineering and Systems Science (some bio applications)
                for cat in categories
            )
            
            # Include the result if it matches any of the criteria
            if has_life_science or has_ai or has_ai4s or has_life_science_category or has_query_terms:
                # Apply additional scoring based on relevance
                relevance_score = result.get('relevance_score', 0.0)
                
                # Boost score if it has both life science and AI elements
                if has_life_science and has_ai:
                    relevance_score = min(1.0, relevance_score + 0.2)
                elif has_life_science:
                    relevance_score = min(1.0, relevance_score + 0.1)
                elif has_ai4s:
                    relevance_score = min(1.0, relevance_score + 0.15)
                elif has_life_science_category:
                    relevance_score = min(1.0, relevance_score + 0.1)
                
                result['relevance_score'] = relevance_score
                filtered_results.append(result)
        
        logger.info(f"Domain relevance filter reduced results from {len(results)} to {len(filtered_results)}")
        return filtered_results


def create_advanced_arxiv_tool(max_search_results: int = 5):
    """Factory function to create the advanced arXiv search tool."""
    return AiInspiredArxivToolWrapper(max_search_results=max_search_results)


if __name__ == "__main__":
    # Example usage
    tool = create_advanced_arxiv_tool(max_search_results=3)
    results = tool._run("liquid neural networks")
    print(results)