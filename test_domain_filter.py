#!/usr/bin/env python3
"""
Test script to verify the enhanced arXiv search tool with domain filtering
"""
import sys
import os

# Add the thesis-flow src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ThesisFlow', 'src'))

from tools.arxiv_advanced import AiInspiredArxivToolWrapper


def test_domain_filtered_search():
    """Test the enhanced arXiv search tool with domain filtering."""
    print("Testing enhanced arXiv search tool with domain filtering...")
    
    # Create the tool instance
    tool = AiInspiredArxivToolWrapper(max_search_results=5)
    
    # Test search query related to AI4S in life sciences
    test_query = "AI for scientific discovery in life sciences"
    
    try:
        # Run the search
        results = tool._run(test_query)
        print(f"Search results for '{test_query}':")
        print("=" * 60)
        print(results)
        
        # Check if results are properly filtered
        if "Paper 1:" in results or "Result 1:" in results:
            print("\n✓ Search returned results with proper formatting")
            
            # Check if life science or AI related terms are present
            if any(term in results.lower() for term in ['biology', 'medicine', 'bio', 'genomic', 'drug', 'disease', 'ai', 'learning', 'neural', 'ai4s']):
                print("✓ Results contain life science or AI related terms")
            else:
                print("⚠ Results may not contain expected life science or AI terms")
        else:
            print("\n⚠ Search did not return properly formatted results")
            
        # Look for potentially irrelevant results like "Light-X" that were in the original problem
        if "Light - X" in results or "4D Video Rendering" in results:
            print("⚠ Found potentially irrelevant result (Light-X paper)")
        else:
            print("✓ No irrelevant results like 'Light-X' found")
            
    except Exception as e:
        print(f"Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()


def test_specific_query():
    """Test with the specific query from the issue."""
    print("\n" + "="*60)
    print("Testing with specific query from the issue...")
    
    tool = AiInspiredArxivToolWrapper(max_search_results=3)
    
    # Use the exact query that was problematic
    test_query = "Successful AI4S cases in life sciences including drug discovery, disease diagnosis, genomics research"
    
    try:
        results = tool._run(test_query)
        print(f"Search results for specific query:")
        print("=" * 60)
        print(results)
        
        # Verify the results are relevant
        has_life_science_content = any(term in results.lower() 
                                     for term in ['genomic', 'drug', 'disease', 'biology', 'medicine', 'bio', 'health'])
        has_ai_content = any(term in results.lower() 
                           for term in ['ai', 'learning', 'neural', 'algorithm', 'machine'])
                           
        if has_life_science_content and has_ai_content:
            print("\n✓ Results contain both life science and AI content")
        elif has_life_science_content:
            print("\n✓ Results contain life science content")
        elif has_ai_content:
            print("\n✓ Results contain AI content")
        else:
            print("\n⚠ Results may not contain expected life science or AI content")
        
        # Check for the problematic papers
        problematic_papers = ["Light - X", "4D Video Rendering", "Universal Weight Subspace"]
        found_problematic = [paper for paper in problematic_papers if paper in results]
        
        if found_problematic:
            print(f"⚠ Found problematic papers: {found_problematic}")
        else:
            print("✓ No problematic papers found")
            
    except Exception as e:
        print(f"Error during specific query testing: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_domain_filtered_search()
    test_specific_query()
    print("\nTesting completed.")
