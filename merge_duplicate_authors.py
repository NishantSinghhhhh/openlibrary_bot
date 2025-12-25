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

Dependencies:
    pip install requests

Usage:
    # For local development server:
    python merge_duplicate_authors.py

    Then follow the interactive prompts or edit the CONFIGURATION section in main()
"""

import json
import requests
import time
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'merge_run_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class OpenLibraryMergeBot:
    """Bot to merge duplicate authors on Open Library."""
    
    def __init__(self, username: str, password: str, base_url: str = "http://localhost:8080", dry_run: bool = True):
        """
        Initialize the Open Library merge bot.
        
        Args:
            username: Bot account username
            password: Bot account password
            base_url: Open Library base URL
            dry_run: If True, only simulate changes without actually merging
        """
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip('/')
        self.dry_run = dry_run
        self.session = requests.Session()
        self.logged_in = False
        
        # Statistics
        self.stats = {
            'total_groups': 0,
            'successful_merges': 0,
            'failed_merges': 0,
            'skipped_already_merged': 0,
            'skipped_conflicts': 0,
            'total_authors_merged': 0
        }
        
        # Results storage
        self.results = {
            'successful_merges': [],
            'failed_merges': [],
            'skipped_already_merged': [],
            'skipped_conflicts': []
        }
    
    def login(self) -> bool:
        """Login to Open Library with bot credentials."""
        logger.info(f"Attempting to login as {self.username}...")
        
        login_url = f"{self.base_url}/account/login"
        
        # First, get the login page to establish a session
        try:
            response = self.session.get(login_url)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Error accessing login page: {e}")
            return False
        
        # Post login credentials
        login_data = {
            'username': self.username,
            'password': self.password,
            'redirect': '/'
        }
        
        try:
            response = self.session.post(login_url, data=login_data)
            response.raise_for_status()
            
            # Verify login was successful
            if 'session' not in self.session.cookies:
                logger.error("Login failed - no session cookie received")
                return False
            
            self.logged_in = True
            logger.info("Login successful!")
            return True
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def get_author(self, author_key: str) -> Optional[Dict]:
        """
        Fetch author data from the API.
        
        Args:
            author_key: Author key like '/authors/OL123A' or 'OL123A'
        
        Returns:
            Author data as dict, or None if author doesn't exist or was redirected
        """
        # Normalize to full path
        if not author_key.startswith('/authors/'):
            author_key = f"/authors/{author_key}"
        
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
            master_key: The author key to keep (e.g., '/authors/OL123A' or 'OL123A')
            duplicate_keys: List of author keys to merge into master
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        # Normalize keys to full paths
        if not master_key.startswith('/authors/'):
            master_key = f"/authors/{master_key}"
        
        normalized_duplicates = []
        for key in duplicate_keys:
            if not key.startswith('/authors/'):
                normalized_duplicates.append(f"/authors/{key}")
            else:
                normalized_duplicates.append(key)
        
        if self.dry_run:
            message = f"[DRY RUN] Would merge {normalized_duplicates} into {master_key}"
            logger.info(message)
            return True, message
        
        merge_url = f"{self.base_url}/authors/merge"
        
        # Prepare the merge data
        merge_data = {
            'master': master_key,
            'duplicates': ','.join(normalized_duplicates)
        }
        
        try:
            response = self.session.post(merge_url, data=merge_data, allow_redirects=True)
            
            if response.status_code == 200:
                return True, f"Successfully merged {normalized_duplicates} into {master_key}"
            else:
                return False, f"Merge failed with status {response.status_code}: {response.text[:200]}"
                
        except requests.exceptions.RequestException as e:
            return False, f"Error during merge: {str(e)}"
    
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
    
    def validate_and_prepare_merge(self, author_ids: Set[str], rate_limit_delay: float = 0.5) -> Optional[Tuple[str, List[str]]]:
        """
        Validate authors can be merged by fetching latest data.
        
        Returns:
            Tuple of (master_key, duplicate_keys) if valid, None otherwise
        """
        # Fetch current data for all authors
        author_data = {}
        for author_id in author_ids:
            data = self.get_author(author_id)
            if data is None:
                # Author was redirected or doesn't exist
                logger.info(f"Skipping {author_id} - already merged or doesn't exist")
                self.results['skipped_already_merged'].append(author_id)
                self.stats['skipped_already_merged'] += 1
                continue
            author_data[author_id] = data
            time.sleep(rate_limit_delay)
        
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
            self.stats['skipped_conflicts'] += 1
            return None
        
        # Choose the oldest author as master (lowest numeric ID)
        def extract_numeric_id(key):
            # Remove '/authors/' prefix if present
            if key.startswith('/authors/'):
                key = key.replace('/authors/', '')
            # Extract number between 'OL' and 'A'
            return int(key.split('OL')[1].rstrip('A'))
        
        sorted_ids = sorted(author_data.keys(), key=extract_numeric_id)
        master_key = sorted_ids[0]
        duplicate_keys = sorted_ids[1:]
        
        return master_key, duplicate_keys
    
    def _check_for_conflicts(self, author_data: Dict[str, Dict]) -> List[str]:
        """
        Check if there are conflicts in the author data that would prevent merging.
        
        Returns list of conflict descriptions.
        """
        conflicts = []
        
        # Fields to check for conflicts (excluding key, created, last_modified, type, revision)
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
    
    def process_author_group(self, normalized_name: str, author_ids: Set[str], rate_limit_delay: float = 0.5) -> bool:
        """
        Process a single author group and perform merge.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"\nProcessing: {normalized_name} ({len(author_ids)} authors)")
        
        # Validate and prepare the merge
        merge_info = self.validate_and_prepare_merge(author_ids, rate_limit_delay)
        
        if merge_info is None:
            logger.info(f"Skipping merge for {normalized_name}")
            return False
        
        master_key, duplicate_keys = merge_info
        
        # Perform the merge
        success, message = self.merge_authors(master_key, duplicate_keys)
        
        if success:
            logger.info(message)
            self.results['successful_merges'].append({
                'normalized_name': normalized_name,
                'master': master_key,
                'merged': duplicate_keys,
                'timestamp': datetime.now().isoformat()
            })
            self.stats['successful_merges'] += 1
            self.stats['total_authors_merged'] += len(duplicate_keys)
        else:
            logger.error(message)
            self.results['failed_merges'].append({
                'normalized_name': normalized_name,
                'master': master_key,
                'duplicates': duplicate_keys,
                'error': message,
                'timestamp': datetime.now().isoformat()
            })
            self.stats['failed_merges'] += 1
        
        return success
    
    def process_all_merges(self, json_file: str, rate_limit_delay: float = 0.5, max_groups: int = None):
        """
        Process all author groups from the JSON file.
        
        Args:
            json_file: Path to the JSON file with duplicate authors
            rate_limit_delay: Delay in seconds between API calls
            max_groups: Maximum number of groups to process (None = all)
        """
        logger.info(f"Loading duplicate authors from {json_file}...")
        
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading JSON file: {e}")
            return
        
        logger.info(f"Loaded {len(data)} works with duplicate authors")
        
        # Extract unique author groups
        author_groups = self.extract_unique_author_groups(data)
        
        if not author_groups:
            logger.warning("No author groups found to merge!")
            return
        
        self.stats['total_groups'] = len(author_groups)
        
        # Limit groups if specified
        if max_groups:
            items = list(author_groups.items())[:max_groups]
            author_groups = dict(items)
            logger.info(f"Processing first {max_groups} groups only (test mode)")
        
        logger.info(f"Mode: {'DRY RUN (no actual changes)' if self.dry_run else 'LIVE (will make changes)'}")
        logger.info("Starting processing...\n")
        
        # Process each author group
        for idx, (normalized_name, author_ids) in enumerate(author_groups.items(), 1):
            logger.info(f"Progress: {idx}/{len(author_groups)}")
            
            self.process_author_group(normalized_name, author_ids, rate_limit_delay)
            
            # Rate limiting between groups
            if idx < len(author_groups):
                time.sleep(rate_limit_delay)
        
        # Save results and print statistics
        self.save_results()
        self.print_statistics()
    
    def save_results(self):
        """Save merge results to JSON files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save successful merges
        if self.results['successful_merges']:
            successful_file = f"merge_results_successful_{timestamp}.json"
            with open(successful_file, 'w') as f:
                json.dump(self.results['successful_merges'], f, indent=2)
            logger.info(f"Saved {len(self.results['successful_merges'])} successful merges to {successful_file}")
        
        # Save failed merges
        if self.results['failed_merges']:
            failed_file = f"merge_results_failed_{timestamp}.json"
            with open(failed_file, 'w') as f:
                json.dump(self.results['failed_merges'], f, indent=2)
            logger.info(f"Saved {len(self.results['failed_merges'])} failed merges to {failed_file}")
        
        # Save skipped (conflicts)
        if self.results['skipped_conflicts']:
            conflicts_file = f"merge_results_conflicts_{timestamp}.json"
            with open(conflicts_file, 'w') as f:
                json.dump(self.results['skipped_conflicts'], f, indent=2)
            logger.info(f"Saved {len(self.results['skipped_conflicts'])} skipped (conflicts) to {conflicts_file}")
        
        # Save skipped (already merged)
        if self.results['skipped_already_merged']:
            already_merged_file = f"merge_results_already_merged_{timestamp}.json"
            with open(already_merged_file, 'w') as f:
                json.dump(self.results['skipped_already_merged'], f, indent=2)
            logger.info(f"Saved {len(self.results['skipped_already_merged'])} already merged to {already_merged_file}")
        
        # Save summary
        summary_file = f"merge_results_summary_{timestamp}.txt"
        with open(summary_file, 'w') as f:
            f.write(f"Author Merge Summary - {timestamp}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Total groups processed: {self.stats['total_groups']}\n")
            f.write(f"Successful merges: {self.stats['successful_merges']}\n")
            f.write(f"Failed merges: {self.stats['failed_merges']}\n")
            f.write(f"Skipped (conflicts): {self.stats['skipped_conflicts']}\n")
            f.write(f"Skipped (already merged): {self.stats['skipped_already_merged']}\n")
            f.write(f"Total authors merged: {self.stats['total_authors_merged']}\n")
        
        logger.info(f"Saved summary to {summary_file}")
    
    def print_statistics(self):
        """Print final statistics about the bot run."""
        logger.info("\n" + "="*50)
        logger.info("FINAL STATISTICS")
        logger.info("="*50)
        logger.info(f"Total groups processed: {self.stats['total_groups']}")
        logger.info(f"Successful merges: {self.stats['successful_merges']}")
        logger.info(f"Failed merges: {self.stats['failed_merges']}")
        logger.info(f"Skipped (conflicts): {self.stats['skipped_conflicts']}")
        logger.info(f"Skipped (already merged): {self.stats['skipped_already_merged']}")
        logger.info(f"Total authors merged: {self.stats['total_authors_merged']}")
        logger.info("="*50)


def main():
    """Main function to run the bot."""
    
    # CONFIGURATION - UPDATE THESE VALUES
    BOT_USERNAME = "nishant_singh614"              # TODO: Replace with your bot username
    BOT_PASSWORD = "nishant1703."        # TODO: Replace with your bot password
    BASE_URL = "https://openlibrary.org/"             # Use "https://openlibrary.org" for production
    JSON_FILE = "works_duplicate_authors_SAFE_TO_MERGE.json"  # Path to the JSON file
    DRY_RUN = True                                 # Set to False to make actual changes
    RATE_LIMIT_DELAY = 0.5                         # Seconds between API calls
    MAX_GROUPS_TO_PROCESS = 10                     # Set to None to process all, or a number for testing
    
    print("="*70)
    print("Open Library Duplicate Authors Merge Bot")
    print("="*70)
    print(f"Mode: {'DRY RUN (simulation only)' if DRY_RUN else 'LIVE MODE (will make changes)'}")
    print(f"Base URL: {BASE_URL}")
    print(f"JSON File: {JSON_FILE}")
    print(f"Max groups to process: {MAX_GROUPS_TO_PROCESS if MAX_GROUPS_TO_PROCESS else 'All'}")
    print("="*70)
    
    if not DRY_RUN:
        response = input("\nYou are in LIVE MODE. This will make actual changes. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return
    
    # Create bot instance
    bot = OpenLibraryMergeBot(
        username=BOT_USERNAME,
        password=BOT_PASSWORD,
        base_url=BASE_URL,
        dry_run=DRY_RUN
    )
    
    # Login
    if not bot.login():
        print("Failed to login. Please check credentials.")
        return
    
    # Process all merges
    bot.process_all_merges(
        json_file=JSON_FILE,
        rate_limit_delay=RATE_LIMIT_DELAY,
        max_groups=MAX_GROUPS_TO_PROCESS
    )
    
    print("\nBot execution completed!")


if __name__ == "__main__":
    main()