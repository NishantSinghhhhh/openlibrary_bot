import json
import requests
import time
from typing import Dict, List, Set
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'bot_run_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)

class OpenLibraryBot:
    def __init__(self, username: str, password: str, dry_run: bool = True):
        """
        Initialize the Open Library bot.
        
        Args:
            username: Bot account username
            password: Bot account password
            dry_run: If True, only simulate changes without actually updating
        """
        self.username = username
        self.password = password
        self.dry_run = dry_run
        self.base_url = "https://openlibrary.org"
        self.session = requests.Session()
        self.logged_in = False
        
        # Statistics
        self.stats = {
            'total_works': 0,
            'successful_updates': 0,
            'failed_updates': 0,
            'skipped_works': 0,
            'authors_removed': 0
        }
    
    def login(self) -> bool:
        """Login to Open Library with bot credentials."""
        logging.info(f"Attempting to login as {self.username}...")
        
        login_url = f"{self.base_url}/account/login"
        
        login_data = {
            'username': self.username,
            'password': self.password,
            'redirect': '/'
        }
        
        try:
            response = self.session.post(login_url, data=login_data)
            
            if response.status_code == 200 and self.username.lower() in response.text.lower():
                self.logged_in = True
                logging.info("Login successful!")
                return True
            else:
                logging.error("Login failed!")
                return False
                
        except Exception as e:
            logging.error(f"Login error: {e}")
            return False
    
    def get_work(self, work_id: str) -> Dict:
        """
        Fetch work data from Open Library.
        
        Args:
            work_id: The work ID (e.g., 'OL39584341W' or '/works/OL39584341W')
            
        Returns:
            Dictionary containing work data
        """
        # Clean up work_id - remove /works/ prefix if present
        if work_id.startswith('/works/'):
            work_id = work_id.replace('/works/', '')
        
        url = f"{self.base_url}/works/{work_id}.json"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Error fetching work {work_id}: {e}")
            return None
    
    def remove_duplicate_authors(self, authors: List[Dict]) -> tuple[List[Dict], int]:
        """
        Remove duplicate authors from the authors list.
        
        Args:
            authors: List of author dictionaries with 'author' key containing {'key': '/authors/OL123A'}
            
        Returns:
            Tuple of (cleaned authors list, number of duplicates removed)
        """
        seen_authors = set()
        cleaned_authors = []
        duplicates_removed = 0
        
        for author_entry in authors:
            # Handle different author formats
            if isinstance(author_entry, dict):
                if 'author' in author_entry:
                    author_key = author_entry['author'].get('key', '')
                elif 'key' in author_entry:
                    author_key = author_entry.get('key', '')
                else:
                    continue
            else:
                continue
            
            if author_key and author_key not in seen_authors:
                seen_authors.add(author_key)
                cleaned_authors.append(author_entry)
            elif author_key in seen_authors:
                duplicates_removed += 1
                logging.debug(f"Removing duplicate author: {author_key}")
        
        return cleaned_authors, duplicates_removed
    
    def update_work(self, work_id: str, work_data: Dict, comment: str) -> bool:
        """
        Update a work on Open Library.
        
        Args:
            work_id: The work ID (without /works/ prefix)
            work_data: Updated work data
            comment: Edit comment explaining the change
            
        Returns:
            True if update successful, False otherwise
        """
        # Clean up work_id
        if work_id.startswith('/works/'):
            work_id = work_id.replace('/works/', '')
        
        if self.dry_run:
            logging.info(f"[DRY RUN] Would update work {work_id}")
            return True
        
        url = f"{self.base_url}/works/{work_id}.json"
        
        # Add edit comment
        work_data['_comment'] = comment
        
        try:
            response = self.session.put(
                url,
                json=work_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logging.info(f"Successfully updated work {work_id}")
                return True
            else:
                logging.error(f"Failed to update work {work_id}: Status {response.status_code}")
                logging.error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            logging.error(f"Error updating work {work_id}: {e}")
            return False
    
    def process_work(self, work_id: str) -> bool:
        """
        Process a single work to remove duplicate authors.
        
        Args:
            work_id: The work ID to process (can include /works/ prefix)
            
        Returns:
            True if successful, False otherwise
        """
        # Clean work_id for display
        display_id = work_id.replace('/works/', '') if work_id.startswith('/works/') else work_id
        
        logging.info(f"\nProcessing work: {display_id}")
        
        # Fetch current work data
        work_data = self.get_work(work_id)
        
        if not work_data:
            logging.warning(f"Could not fetch work {display_id}, skipping...")
            self.stats['skipped_works'] += 1
            return False
        
        # Check if work has authors
        if 'authors' not in work_data or not work_data['authors']:
            logging.warning(f"Work {display_id} has no authors field, skipping...")
            self.stats['skipped_works'] += 1
            return False
        
        original_author_count = len(work_data['authors'])
        logging.info(f"Original author count: {original_author_count}")
        
        # Remove duplicates
        cleaned_authors, duplicates_removed = self.remove_duplicate_authors(work_data['authors'])
        
        if duplicates_removed == 0:
            logging.info(f"No duplicates found in work {display_id}, skipping...")
            self.stats['skipped_works'] += 1
            return False
        
        logging.info(f"Removed {duplicates_removed} duplicate author(s)")
        logging.info(f"New author count: {len(cleaned_authors)}")
        
        # Update work data
        work_data['authors'] = cleaned_authors
        
        # Update the work
        comment = f"Removed {duplicates_removed} duplicate author entry(ies) - Bot automated cleanup"
        
        success = self.update_work(work_id, work_data, comment)
        
        if success:
            self.stats['successful_updates'] += 1
            self.stats['authors_removed'] += duplicates_removed
        else:
            self.stats['failed_updates'] += 1
        
        return success
    
    def process_all_works(self, json_file: str, delay: float = 2.0, max_works: int = None):
        """
        Process all works from the duplicate authors JSON file.
        
        Args:
            json_file: Path to the JSON file with duplicate authors
            delay: Delay in seconds between requests (rate limiting)
            max_works: Maximum number of works to process (None = all)
        """
        logging.info(f"Loading duplicate authors from {json_file}...")
        
        try:
            with open(json_file, 'r') as f:
                duplicate_data = json.load(f)
        except Exception as e:
            logging.error(f"Error loading JSON file: {e}")
            return
        
        # Handle list format (which is what you have)
        if not isinstance(duplicate_data, list):
            logging.error(f"Expected JSON to be a list, got {type(duplicate_data)}")
            return
        
        logging.info(f"Loaded {len(duplicate_data)} entries from JSON")
        
        # Extract work IDs from the list
        work_ids = []
        for item in duplicate_data:
            if 'work_id' in item:
                work_ids.append(item['work_id'])
            else:
                logging.warning(f"Entry missing 'work_id' field: {item}")
        
        self.stats['total_works'] = len(work_ids)
        
        if max_works:
            work_ids = work_ids[:max_works]
            logging.info(f"Processing first {max_works} works only (test mode)")
        
        logging.info(f"Found {len(work_ids)} works to process")
        logging.info(f"Mode: {'DRY RUN (no actual changes)' if self.dry_run else 'LIVE (will make changes)'}")
        logging.info("Starting processing...\n")
        
        for idx, work_id in enumerate(work_ids, 1):
            logging.info(f"Progress: {idx}/{len(work_ids)}")
            
            self.process_work(work_id)
            
            # Rate limiting
            if idx < len(work_ids):  # Don't delay after last work
                time.sleep(delay)
        
        # Print final statistics
        self.print_statistics()
    
    def print_statistics(self):
        """Print final statistics about the bot run."""
        logging.info("\n" + "="*50)
        logging.info("FINAL STATISTICS")
        logging.info("="*50)
        logging.info(f"Total works processed: {self.stats['total_works']}")
        logging.info(f"Successful updates: {self.stats['successful_updates']}")
        logging.info(f"Failed updates: {self.stats['failed_updates']}")
        logging.info(f"Skipped works: {self.stats['skipped_works']}")
        logging.info(f"Total duplicate authors removed: {self.stats['authors_removed']}")
        logging.info("="*50)


def main():
    """Main function to run the bot."""
    
    # CONFIGURATION - UPDATE THESE VALUES
    BOT_USERNAME = "your_bot_username_here"  # TODO: Replace with your bot username
    BOT_PASSWORD = "your_bot_password_here"  # TODO: Replace with your bot password
    JSON_FILE = "duplicate_authors.json"      # Path to the JSON file
    DRY_RUN = True                            # Set to False to make actual changes
    DELAY_BETWEEN_REQUESTS = 2.0              # Seconds between requests
    MAX_WORKS_TO_PROCESS = 10                 # Set to None to process all, or a number for testing
    
    print("="*70)
    print("Open Library Duplicate Authors Removal Bot")
    print("="*70)
    print(f"Mode: {'DRY RUN (simulation only)' if DRY_RUN else 'LIVE MODE (will make changes)'}")
    print(f"JSON File: {JSON_FILE}")
    print(f"Max works to process: {MAX_WORKS_TO_PROCESS if MAX_WORKS_TO_PROCESS else 'All'}")
    print("="*70)
    
    if not DRY_RUN:
        response = input("\nYou are in LIVE MODE. This will make actual changes. Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return
    
    # Create bot instance
    bot = OpenLibraryBot(
        username=BOT_USERNAME,
        password=BOT_PASSWORD,
        dry_run=DRY_RUN
    )
    
    # Login
    if not bot.login():
        print("Failed to login. Please check credentials.")
        return
    
    # Process all works
    bot.process_all_works(
        json_file=JSON_FILE,
        delay=DELAY_BETWEEN_REQUESTS,
        max_works=MAX_WORKS_TO_PROCESS
    )
    
    print("\nBot execution completed!")


if __name__ == "__main__":
    main()