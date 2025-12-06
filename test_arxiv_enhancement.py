#!/usr/bin/env python3
"""
Test script to verify the enhanced arXiv search tool functionality
"""
import sys
import os

# Add the thesis-flow src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ThesisFlow', 'src'))

from tools.arxiv_advanced import AiInspiredArxivToolWrapper


def test_arxiv_tool():
    """Test the enhanced arXiv search tool."""
    print("Testing enhanced arXiv search tool...")
    
    # Create the tool instance
    tool = AiInspiredArxivToolWrapper(max_search_results=3)
    
    # Test search query
    test_query = "machine learning"
    
    try:
        # Run the search
        results = tool._run(test_query)
        print(f"Search results for '{test_query}':")
        print(results)
        
        # Check if key sections are present in the output
        if "Core Content Summary:" in results:
            print("\n✓ Core Content Summary section found")
        else:
            print("\n✗ Core Content Summary section NOT found")
            
        if "Methods/Approach:" in results:
            print("✓ Methods/Approach section found")
        else:
            print("✗ Methods/Approach section NOT found")
            
        if "Key Results:" in results:
            print("✓ Key Results section found")
        else:
            print("✗ Key Results section NOT found")
            
        if "Conclusions/Future Work:" in results:
            print("✓ Conclusions/Future Work section found")
        else:
            print("✗ Conclusions/Future Work section NOT found")
            
    except Exception as e:
        print(f"Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_arxiv_tool()
