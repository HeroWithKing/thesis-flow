"""
Literature Summarizer Tool
Based on the enhanced report structure to prioritize core content and conclusions
"""
import logging
from typing import Dict, Any
from langchain_core.tools import BaseTool
from pydantic import Field
import os

logger = logging.getLogger(__name__)


class LiteratureSummarizerTool(BaseTool):
    """
    Tool that creates literature summaries with focus on core content and conclusions
    """
    name: str = Field(default="literature_summarizer")
    description: str = Field(default="Generates focused literature summaries emphasizing core content and conclusions from research papers")
    
    def _run(self, input_data: str) -> str:
        """Synchronous version of the tool."""
        try:
            # This would integrate with the LLM using the literature_summarizer.md prompt
            # For now, we'll return a message indicating the tool is configured
            return self._generate_literature_summary(input_data)
        except Exception as e:
            logger.error(f"Error in LiteratureSummarizerTool._run: {str(e)}")
            return f"Error: {str(e)}"
    
    async def _arun(self, input_data: str):
        """Asynchronous version of the tool."""
        try:
            return self._generate_literature_summary(input_data)
        except Exception as e:
            logger.error(f"Error in LiteratureSummarizerTool._arun: {str(e)}")
            return f"Error: {str(e)}"
    
    def _generate_literature_summary(self, input_data: str) -> str:
        """
        Generate literature summary with focus on core content and conclusions
        """
        # In a real implementation, this would call an LLM with the 
        # literature_summarizer.md prompt template
        summary = f"""
# Literature Summary Generated

This summary was created using the enhanced literature summarization approach, focusing on:

1. **Core Content & Conclusions**: The primary findings and conclusions from the research papers
2. **Key Results**: Essential experimental results and performance metrics
3. **Innovation Points**: Novel contributions and technical advances
4. **Comparative Analysis**: How the papers compare in methods and outcomes
5. **Research Gaps**: Identified opportunities for further research

Input processed: {input_data[:200]}...
        
For a full literature summary using the enhanced structure that emphasizes core content and conclusions, the system would process your input with the literature_summarizer prompt.
"""
        return summary


def create_literature_summarizer_tool():
    """Factory function to create the literature summarizer tool."""
    return LiteratureSummarizerTool()