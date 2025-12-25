import json
import sys
from typing import Dict, List, Set
from collections import defaultdict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def load_works_dump(works_file: str) -> Dict[str, Set[str]]:
    """
    Load the works dump and create a mapping of author_id -> set of work_ids.
    
    Args:
        works_file: Path to the ol_dump_works_*.txt file
        
    Returns:
        Dictionary mapping author_id to set of work_ids they're associated with
    """
    logging.info(f"Loading works dump to count author appearances: {works_file}")
    
    author_to_works = defaultdict(set)
    total_lines = 0
    
    try:
        with open(works_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num % 100000 == 0:
                    logging.info(f"  Processed {line_num:,} lines...")
                
                total_lines += 1
                
                try:
                    parts = line.strip().split('\t')
                    if len(parts) < 5:
                        continue
                    
                    type_str = parts[0]
                    work_key = parts[1]
                    json_str = parts[4]
                    
                    if type_str != '/type/work':
                        continue
                    
                    json_data = json.loads(json_str)
                    
                    # Extract all author IDs from this work
                    if 'authors' in json_data and json_data['authors']:
                        for author_entry in json_data['authors']:
                            author_key = None
                            
                            if isinstance(author_entry, dict):
                                if 'author' in author_entry and isinstance(author_entry['author'], dict):
                                    author_key = author_entry['author'].get('key')
                                elif 'key' in author_entry:
                                    author_key = author_entry.get('key')
                            
                            if author_key:
                                author_to_works[author_key].add(work_key)
                
                except Exception as e:
                    logging.debug(f"Error parsing line {line_num}: {e}")
                    continue
        
        logging.info(f"Processed {total_lines:,} lines. Found {len(author_to_works):,} unique authors")
        return dict(author_to_works)
    
    except FileNotFoundError:
        logging.error(f"Works file not found: {works_file}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error loading works dump: {e}", exc_info=True)
        sys.exit(1)


def filter_single_work_duplicates(input_json: str, author_to_works: Dict[str, Set[str]], 
                                   output_json: str):
    """
    Filter works to only those where ALL duplicate authors have only ONE work.
    
    Args:
        input_json: Path to works_with_duplicate_authors.json
        author_to_works: Dictionary mapping author_id to set of work_ids
        output_json: Path to output filtered JSON
    """
    logging.info(f"Loading duplicate works from: {input_json}")
    
    with open(input_json, 'r', encoding='utf-8') as f:
        all_works = json.load(f)
    
    logging.info(f"Loaded {len(all_works):,} works with duplicate authors")
    
    # Filter works
    filtered_works = []
    
    for work in all_works:
        work_id = work['work_id']
        all_duplicates_single_work = True
        
        # Check each duplicate author group
        for dup_group in work['duplicate_authors']:
            # Check if ALL authors in this duplicate group only have 1 work
            for author in dup_group['authors']:
                author_id = author['author_id']
                
                # Get the number of works this author appears in
                num_works = len(author_to_works.get(author_id, set()))
                
                # If this author appears in more than 1 work, skip this work
                if num_works > 1:
                    all_duplicates_single_work = False
                    break
            
            if not all_duplicates_single_work:
                break
        
        # If all duplicate authors only have this one work, include it
        if all_duplicates_single_work:
            # Add work count info to the output
            work_with_counts = work.copy()
            for dup_group in work_with_counts['duplicate_authors']:
                for author in dup_group['authors']:
                    author_id = author['author_id']
                    author['num_works'] = len(author_to_works.get(author_id, set()))
            
            filtered_works.append(work_with_counts)
    
    # Sort by number of duplicate authors (most duplicates first)
    filtered_works.sort(key=lambda x: sum(d['count'] for d in x['duplicate_authors']), reverse=True)
    
    # Save filtered results
    logging.info(f"Saving filtered results to: {output_json}")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(filtered_works, f, indent=2, ensure_ascii=False)
    
    # Print statistics
    print("\n" + "="*70)
    print("FILTERING RESULTS")
    print("="*70)
    print(f"Total works with duplicate authors: {len(all_works):,}")
    print(f"Works where ALL duplicates only have 1 work: {len(filtered_works):,}")
    print(f"Percentage: {len(filtered_works)/len(all_works)*100:.2f}%")
    print(f"Results saved to: {output_json}")
    print("="*70)
    
    # Show sample
    if filtered_works:
        print("\nSample of filtered works (first 5):")
        print("-" * 70)
        for work in filtered_works[:5]:
            print(f"\nWork ID: {work['work_id']}")
            print(f"Title: {work['work_title']}")
            for dup in work['duplicate_authors']:
                print(f"  Duplicate name: {dup['display_name']} (appears {dup['count']} times)")
                for author in dup['authors']:
                    print(f"    - {author['author_id']}: {author['name']} (has {author['num_works']} work(s))")
    
    return len(filtered_works)


def filter_from_existing_json(input_json: str, output_json: str):
    """
    Filter works using only the existing JSON (simpler version without re-scanning).
    This assumes each author only appears in the current work being analyzed.
    
    Args:
        input_json: Path to works_with_duplicate_authors.json
        output_json: Path to output filtered JSON
    """
    logging.info(f"Loading duplicate works from: {input_json}")
    
    with open(input_json, 'r', encoding='utf-8') as f:
        all_works = json.load(f)
    
    logging.info(f"Loaded {len(all_works):,} works with duplicate authors")
    
    # Since we need to check if authors appear in other works,
    # we need to build a map of author_id -> list of work_ids from our JSON
    author_to_works_in_json = defaultdict(set)
    
    for work in all_works:
        work_id = work['work_id']
        for dup_group in work['duplicate_authors']:
            for author in dup_group['authors']:
                author_id = author['author_id']
                author_to_works_in_json[author_id].add(work_id)
    
    # Filter works where all duplicate authors only appear in that one work
    filtered_works = []
    
    for work in all_works:
        work_id = work['work_id']
        all_duplicates_single_work = True
        
        for dup_group in work['duplicate_authors']:
            for author in dup_group['authors']:
                author_id = author['author_id']
                
                # Check if this author appears in multiple works (within our filtered set)
                num_works = len(author_to_works_in_json[author_id])
                
                if num_works > 1:
                    all_duplicates_single_work = False
                    break
            
            if not all_duplicates_single_work:
                break
        
        if all_duplicates_single_work:
            # Add work count info
            work_with_counts = work.copy()
            for dup_group in work_with_counts['duplicate_authors']:
                for author in dup_group['authors']:
                    author_id = author['author_id']
                    author['num_works_in_duplicate_set'] = len(author_to_works_in_json[author_id])
            
            filtered_works.append(work_with_counts)
    
    # Sort by number of duplicate authors
    filtered_works.sort(key=lambda x: sum(d['count'] for d in x['duplicate_authors']), reverse=True)
    
    # Save results
    logging.info(f"Saving filtered results to: {output_json}")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(filtered_works, f, indent=2, ensure_ascii=False)
    
    # Print statistics
    print("\n" + "="*70)
    print("FILTERING RESULTS (JSON-ONLY METHOD)")
    print("="*70)
    print(f"Total works with duplicate authors: {len(all_works):,}")
    print(f"Works where ALL duplicates appear in only this work: {len(filtered_works):,}")
    print(f"Percentage: {len(filtered_works)/len(all_works)*100:.2f}%")
    print(f"Results saved to: {output_json}")
    print("="*70)
    print("\nNOTE: This only checks within the set of works that have duplicates.")
    print("For complete accuracy, use METHOD 1 which scans the full works dump.")
    
    # Show sample
    if filtered_works:
        print("\nSample of filtered works (first 5):")
        print("-" * 70)
        for work in filtered_works[:5]:
            print(f"\nWork ID: {work['work_id']}")
            print(f"Title: {work['work_title']}")
            for dup in work['duplicate_authors']:
                print(f"  Duplicate name: {dup['display_name']} (appears {dup['count']} times in this work)")
                for author in dup['authors']:
                    print(f"    - {author['author_id']}: {author['name']}")
    
    return len(filtered_works)


def main():
    """Main function with two methods."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Filter works to find those where all duplicate authors only have one work')
    parser.add_argument('--method', type=int, choices=[1, 2], default=2,
                       help='Method 1: Scan full works dump (accurate but slow). Method 2: Use existing JSON only (fast but limited)')
    parser.add_argument('--input', type=str, default='works_with_duplicate_authors.json',
                       help='Input JSON file with works that have duplicate authors')
    parser.add_argument('--output', type=str, default='works_single_work_duplicates.json',
                       help='Output JSON file for filtered results')
    parser.add_argument('--works-dump', type=str, default='./123/ol_dump_works_2025-09-30.txt',
                       help='Path to works dump file (only needed for method 1)')
    
    args = parser.parse_args()
    
    print("="*70)
    print("Filter Works with Single-Work Duplicate Authors")
    print("="*70)
    print(f"Input file: {args.input}")
    print(f"Output file: {args.output}")
    print(f"Method: {args.method}")
    print("="*70)
    print()
    
    if args.method == 1:
        print("METHOD 1: Scanning full works dump for accurate work counts")
        print("This will take time but gives accurate results...\n")
        
        # Load works dump to get accurate author->works mapping
        author_to_works = load_works_dump(args.works_dump)
        
        # Filter the works
        filter_single_work_duplicates(args.input, author_to_works, args.output)
    
    else:
        print("METHOD 2: Using existing JSON only (faster but limited)")
        print("Note: This only checks within works that have duplicates...\n")
        
        # Filter using only the JSON data
        filter_from_existing_json(args.input, args.output)
    
    logging.info("\nFiltering completed successfully!")


if __name__ == "__main__":
    main()