#!/usr/bin/env python3
"""
Script to merge duplicate authors from the safe-to-merge JSON file.

This script:
1. Reads the safe-to-merge JSON file
2. Extracts unique author pairs that need merging
3. Fetches the latest data for each author from the API
4. Performs the merge operation via the Open Library merge endpoint
5. Handles redirects (already merged authors)
6. Outputs results to log files

Usage:
    python merge_duplicate_authors.py --input works_duplicate_authors_SAFE_TO_MERGE.json \
                                      --base-url http://localhost:8080 \
                                      --username your_username \
                                      --password your_password

For production:
    python merge_duplicate_authors.py --input works_duplicate_authors_SAFE_TO_MERGE.json \
                                      --base-url https://openlibrary.org \
                                      --username your_username \
                                      --password your_password
"""

import json
import requests
import argparse
import time
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OpenLibrarySession:
    """Manages authentication and requests to Open Library."""
    
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._login()
    
    def _login(self):
        """Authenticate with Open Library and get session cookie."""
        login_url = f"{self.base_url}/account/login"
        
        # First, get the login page to establish a session
        response = self.session.get(login_url)
        response.raise_for_status()
        
        # Now post the login credentials
        login_data = {
            'username': self.username,
            'password': self.password,
            'redirect': '/'
        }
        
        response = self.session.post(login_url, data=login_data)
        response.raise_for_status()
        
        # Verify login was successful
        if 'session' not in self.session.cookies:
            raise Exception("Login failed - no session cookie received")
        
        logger.info(f"Successfully logged in as {self.username}")
    
    def get_author(self, author_key: str) -> Optional[Dict]:
        """
        Fetch author data from the API.
        
        Args:
            author_key: Author key like '/authors/OL123A'
        
        Returns:
            Author data as dict, or None if author doesn't exist or was redirected
        """
        url = f"{self.base_url}{author_key}.json"
        
        try:
            response = self.session.get(url, allow_redirects=False)
            
            # Handle redirects (author was already merged)
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_location = response.headers.get('Location', '')
                logger.info(f"Author {author_key} was already merged/redirected to {redirect_location}")
                return None
            
            if response.status_code == 404:
                logger.warning(f"Author {author_key} not found (404)")
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching author {author_key}: {e}")
            return None
    
    def merge_authors(self, master_key: str, duplicate_keys: List[str]) -> Tuple[bool, str]:
        """
        Merge duplicate authors into the master author.
        
        Args:
            master_key: The author key to keep (e.g., '/authors/OL123A')
            duplicate_keys: List of author keys to merge into master
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        merge_url = f"{self.base_url}/authors/merge"
        
        # Prepare the merge data
        merge_data = {
            'master': master_key,
            'duplicates': ','.join(duplicate_keys)
        }
        
        try:
            response = self.session.post(merge_url, data=merge_data, allow_redirects=True)
            
            if response.status_code == 200:
                return True, f"Successfully merged {duplicate_keys} into {master_key}"
            else:
                return False, f"Merge failed with status {response.status_code}: {response.text[:200]}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Error during merge: {str(e)}"


class AuthorMerger:
    """Handles the logic of processing and merging duplicate authors."""
    
    def __init__(self, ol_session: OpenLibrarySession, rate_limit_delay: float = 0.5):
        self.ol_session = ol_session
        self.rate_limit_delay = rate_limit_delay
        self.results = {
            'successful_merges': [],
            'failed_merges': [],
            'skipped_already_merged': [],
            'skipped_conflicts': []
        }
    
    def extract_unique_author_groups(self, data: List[Dict]) -> Dict[str, Set[str]]:
        """
        Extract unique groups of duplicate authors from the input data.
        
        Returns a dict mapping normalized_name to a set of author_ids that need merging.
        """
        author_groups = defaultdict(set)
        
        for work in data:
            for dup_group in work.get('duplicate_authors', []):
                normalized_name = dup_group['normalized_name']
                author_ids = {author['author_id'] for author in dup_group['authors']}
                
                # Only process if there are actually multiple unique authors
                if len(author_ids) > 1:
                    author_groups[normalized_name].update(author_ids)
        
        # Filter out groups with only one author
        author_groups = {name: ids for name, ids in author_groups.items() if len(ids) > 1}
        
        logger.info(f"Found {len(author_groups)} unique author groups to process")
        total_authors = sum(len(ids) for ids in author_groups.values())
        logger.info(f"Total author pairs/groups: {total_authors}")
        
        return author_groups
    
    def validate_and_prepare_merge(self, author_ids: Set[str]) -> Optional[Tuple[str, List[str]]]:
        """
        Validate authors can be merged by fetching latest data.
        
        Returns:
            Tuple of (master_key, duplicate_keys) if valid, None otherwise
        """
        # Fetch current data for all authors
        author_data = {}
        for author_id in author_ids:
            data = self.ol_session.get_author(author_id)
            if data is None:
                # Author was redirected or doesn't exist
                logger.info(f"Skipping {author_id} - already merged or doesn't exist")
                continue
            author_data[author_id] = data
            time.sleep(self.rate_limit_delay)
        
        # If we have less than 2 authors remaining, nothing to merge
        if len(author_data) < 2:
            return None
        
        # Check for conflicts in the fetched data
        conflicts = self._check_for_conflicts(author_data)
        if conflicts:
            logger.warning(f"Conflicts found: {conflicts}")
            self.results['skipped_conflicts'].append({
                'author_ids': list(author_ids),
                'conflicts': conflicts
            })
            return None
        
        # Choose the oldest author as master (lowest numeric ID)
        sorted_ids = sorted(author_data.keys(), key=lambda x: int(x.split('OL')[1].rstrip('A')))
        master_key = sorted_ids[0]
        duplicate_keys = sorted_ids[1:]
        
        return master_key, duplicate_keys
    
    def _check_for_conflicts(self, author_data: Dict[str, Dict]) -> List[str]:
        """
        Check if there are conflicts in the author data that would prevent merging.
        
        Returns list of conflict descriptions.
        """
        conflicts = []
        
        # Fields to check for conflicts (excluding key, created, last_modified, type)
        fields_to_check = ['name', 'personal_name', 'birth_date', 'death_date', 
                          'bio', 'wikipedia', 'website', 'alternate_names',
                          'links', 'photos', 'remote_ids']
        
        for field in fields_to_check:
            values = set()
            for author_id, data in author_data.items():
                if field in data:
                    value = data[field]
                    # Convert to string for comparison
                    if isinstance(value, (list, dict)):
                        value = json.dumps(value, sort_keys=True)
                    elif value:  # Only add non-empty values
                        value = str(value).strip()
                        if value:
                            values.add(value)
            
            if len(values) > 1:
                conflicts.append(f"{field}: {len(values)} different values")
        
        return conflicts
    
    def process_all_merges(self, author_groups: Dict[str, Set[str]]):
        """Process all author groups and perform merges."""
        total_groups = len(author_groups)
        
        for idx, (normalized_name, author_ids) in enumerate(author_groups.items(), 1):
            logger.info(f"Processing group {idx}/{total_groups}: {normalized_name} ({len(author_ids)} authors)")
            
            # Validate and prepare the merge
            merge_info = self.validate_and_prepare_merge(author_ids)
            
            if merge_info is None:
                logger.info(f"Skipping merge for {normalized_name}")
                continue
            
            master_key, duplicate_keys = merge_info
            
            # Perform the merge
            success, message = self.ol_session.merge_authors(master_key, duplicate_keys)
            
            if success:
                logger.info(message)
                self.results['successful_merges'].append({
                    'normalized_name': normalized_name,
                    'master': master_key,
                    'merged': duplicate_keys,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                logger.error(message)
                self.results['failed_merges'].append({
                    'normalized_name': normalized_name,
                    'master': master_key,
                    'duplicates': duplicate_keys,
                    'error': message,
                    'timestamp': datetime.now().isoformat()
                })
            
            # Rate limiting
            time.sleep(self.rate_limit_delay)
    
    def save_results(self, output_prefix: str = "merge_results"):
        """Save merge results to JSON files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save successful merges
        successful_file = f"{output_prefix}_successful_{timestamp}.json"
        with open(successful_file, 'w') as f:
            json.dump(self.results['successful_merges'], f, indent=2)
        logger.info(f"Saved {len(self.results['successful_merges'])} successful merges to {successful_file}")
        
        # Save failed merges
        if self.results['failed_merges']:
            failed_file = f"{output_prefix}_failed_{timestamp}.json"
            with open(failed_file, 'w') as f:
                json.dump(self.results['failed_merges'], f, indent=2)
            logger.info(f"Saved {len(self.results['failed_merges'])} failed merges to {failed_file}")
        
        # Save skipped (conflicts)
        if self.results['skipped_conflicts']:
            conflicts_file = f"{output_prefix}_conflicts_{timestamp}.json"
            with open(conflicts_file, 'w') as f:
                json.dump(self.results['skipped_conflicts'], f, indent=2)
            logger.info(f"Saved {len(self.results['skipped_conflicts'])} skipped (conflicts) to {conflicts_file}")
        
        # Save summary
        summary_file = f"{output_prefix}_summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write(f"Author Merge Summary - {timestamp}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Successful merges: {len(self.results['successful_merges'])}\n")
            f.write(f"Failed merges: {len(self.results['failed_merges'])}\n")
            f.write(f"Skipped (conflicts): {len(self.results['skipped_conflicts'])}\n")
            f.write(f"Skipped (already merged): {len(self.results['skipped_already_merged'])}\n")
        
        logger.info(f"Saved summary to {summary_file}")
        
        # Print summary
        print("\n" + "=" * 50)
        print("MERGE SUMMARY")
        print("=" * 50)
        print(f"Successful merges: {len(self.results['successful_merges'])}")
        print(f"Failed merges: {len(self.results['failed_merges'])}")
        print(f"Skipped (conflicts): {len(self.results['skipped_conflicts'])}")
        print(f"Skipped (already merged): {len(self.results['skipped_already_merged'])}")
        print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(description='Merge duplicate Open Library authors')
    parser.add_argument('--input', required=True, help='Input JSON file (safe-to-merge)')
    parser.add_argument('--base-url', default='http://localhost:8080', 
                       help='Open Library base URL (default: http://localhost:8080)')
    parser.add_argument('--username', required=True, help='Open Library username')
    parser.add_argument('--password', required=True, help='Open Library password')
    parser.add_argument('--output-prefix', default='merge_results', 
                       help='Prefix for output files (default: merge_results)')
    parser.add_argument('--rate-limit', type=float, default=0.5,
                       help='Delay between API calls in seconds (default: 0.5)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Perform validation only, do not actually merge')
    
    args = parser.parse_args()
    
    # Load input data
    logger.info(f"Loading data from {args.input}")
    with open(args.input, 'r') as f:
        data = json.load(f)
    logger.info(f"Loaded {len(data)} works with duplicate authors")
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No merges will be performed")
    
    # Initialize Open Library session
    ol_session = OpenLibrarySession(args.base_url, args.username, args.password)
    
    # Initialize merger
    merger = AuthorMerger(ol_session, rate_limit_delay=args.rate_limit)
    
    # Extract unique author groups
    author_groups = merger.extract_unique_author_groups(data)
    
    if not author_groups:
        logger.warning("No author groups found to merge!")
        return
    
    # Process merges (unless dry run)
    if not args.dry_run:
        merger.process_all_merges(author_groups)
        merger.save_results(args.output_prefix)
    else:
        logger.info(f"Dry run complete. Would have processed {len(author_groups)} author groups")


if __name__ == '__main__':
    main()