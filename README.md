# Open Library Duplicate Author Removal Bot

A Python bot that automatically identifies and removes duplicate author entries from works in the Open Library database.

## 📋 Overview

This bot addresses a data quality issue in Open Library where some works have the same author listed multiple times. The bot:
- Processes a JSON file containing works with duplicate authors
- Fetches each work's data from Open Library
- Removes duplicate author entries while preserving the original order
- Updates the works with cleaned author lists
- Provides detailed logging and statistics

## 🎯 Problem Statement

Open Library works sometimes contain duplicate author IDs in their authors field. For example:
- **Work**: [OL39584341W - Waarheen met Brussel?](https://openlibrary.org/works/OL39584341W/Waarheen_met_Brussel)
- **Issue**: The same author appears twice in the authors list

This bot was created to clean up approximately **3,949 affected works** identified through data analysis.

## 🚀 Features

- ✅ **Dry Run Mode**: Test without making actual changes
- ✅ **Rate Limiting**: Respects server resources with configurable delays
- ✅ **Comprehensive Logging**: Both console and file logging
- ✅ **Progress Tracking**: Real-time progress updates
- ✅ **Error Handling**: Gracefully handles API errors and edge cases
- ✅ **Statistics**: Detailed summary of operations performed
- ✅ **Batch Processing**: Process all works or limit to a test batch

## 📦 Installation

### Prerequisites
- Python 3.7+
- Virtual environment (recommended)

### Setup

1. **Clone the repository**
```bash
   git clone https://github.com/yourusername/openlibrary_bot.git
   cd openlibrary_bot
```

2. **Create and activate virtual environment**
```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
   pip install requests
```

4. **Add your data file**
   - Place `duplicate_authors.json` in the project root
   - This file should contain the list of works with duplicate authors

## 🔧 Configuration

Edit the configuration section in `remove_duplicate_authors.py`:
```python
# Bot credentials
BOT_USERNAME = "YourBotUsername"      # Your Open Library bot account
BOT_PASSWORD = "YourBotPassword"      # Your bot account password

# File paths
JSON_FILE = "duplicate_authors.json"  # Path to your data file

# Execution settings
DRY_RUN = True                        # True = simulation only, False = make actual changes
MAX_WORKS_TO_PROCESS = 10             # Number of works to process (None = all)
DELAY_BETWEEN_REQUESTS = 2.0          # Seconds between API calls
```

## 📊 Input Data Format

The bot expects a JSON file with the following structure:
```json
[
  {
    "work_id": "/works/OL26463951W",
    "duplicate_author_ids": [
      "/authors/OL3308154A"
    ],
    "all_authors": [
      "/authors/OL3308154A",
      "/authors/OL3308154A"
    ]
  },
  ...
]
```

## 🎮 Usage

### Step 1: Test in Dry Run Mode (Recommended)

Test with a small batch without making any changes:
```bash
python remove_duplicate_authors.py
```

This will:
- Process the first 10 works (configurable)
- Show what changes would be made
- Generate a log file with detailed information
- **NOT make any actual updates**

### Step 2: Review the Logs

Check the generated log file (e.g., `bot_run_20251017_005159.log`):
- Verify the bot is detecting duplicates correctly
- Check for any errors or warnings
- Review the statistics

### Step 3: Run a Small Live Test

After verifying dry run results:
```python
DRY_RUN = False
MAX_WORKS_TO_PROCESS = 5  # Test with just 5 works
```
```bash
python remove_duplicate_authors.py
```

Manually verify the changes on Open Library.

### Step 4: Full Production Run

Once confident everything works:
```python
DRY_RUN = False
MAX_WORKS_TO_PROCESS = None  # Process all works
```
```bash
python remove_duplicate_authors.py
```

## 📝 Example Output
```
======================================================================
Open Library Duplicate Authors Removal Bot
======================================================================
Mode: DRY RUN (simulation only)
JSON File: duplicate_authors.json
Max works to process: 10
======================================================================

2025-10-17 00:51:59 - INFO - Attempting to login as DuplicateRemoverBot...
2025-10-17 00:52:02 - INFO - Login successful!
2025-10-17 00:52:02 - INFO - Loaded 3949 entries from JSON
2025-10-17 00:52:02 - INFO - Processing first 10 works only (test mode)
2025-10-17 00:52:02 - INFO - Found 10 works to process
2025-10-17 00:52:02 - INFO - Starting processing...

2025-10-17 00:52:02 - INFO - Progress: 1/10
2025-10-17 00:52:02 - INFO - Processing work: OL26463951W
2025-10-17 00:52:02 - INFO - Original author count: 2
2025-10-17 00:52:02 - INFO - Removed 1 duplicate author(s)
2025-10-17 00:52:02 - INFO - New author count: 1
2025-10-17 00:52:02 - INFO - [DRY RUN] Would update work OL26463951W

==================================================
FINAL STATISTICS
==================================================
Total works processed: 10
Successful updates: 8
Failed updates: 0
Skipped works: 2
Total duplicate authors removed: 8
==================================================
```

## 🔐 Bot Account Setup

### Creating a Bot Account

1. Go to [Open Library Account Creation](https://openlibrary.org/account/create)
2. Create a new account with a descriptive name (e.g., `DuplicateAuthorRemoverBot`)
3. Use a valid email address

### Getting Bot Permissions

Before running in production:

1. Contact the Open Library team via:
   - [GitHub Issues](https://github.com/internetarchive/openlibrary/issues)
   - [Open Library Slack](https://openlibrary.org/volunteer)
   
2. Explain your bot's purpose:
```
   Hi! I've created a bot to remove duplicate author entries from ~3,949 works.
   The bot has been tested in dry-run mode and I'd like to request bot permissions
   to perform the cleanup. Repository: [your-repo-link]
```

3. Wait for approval before running in live mode

## ⚙️ How It Works

1. **Authentication**: Logs into Open Library using bot credentials
2. **Data Loading**: Reads the JSON file with works containing duplicates
3. **Work Processing**: For each work:
   - Fetches current work data from Open Library API
   - Identifies duplicate authors in the authors field
   - Creates a cleaned authors list (keeping first occurrence)
   - Updates the work (if not in dry-run mode)
4. **Rate Limiting**: Waits between requests to respect server resources
5. **Logging**: Records all operations to both console and log file
6. **Statistics**: Provides summary of operations performed

## 📁 Project Structure
```
openlibrary_bot/
├── remove_duplicate_authors.py  # Main bot script
├── duplicate_authors.json       # Input data (works with duplicates)
├── bot_run_*.log               # Generated log files
├── venv/                       # Virtual environment (not in repo)
└── README.md                   # This file
```

## ⚠️ Important Notes

- **Always test in dry-run mode first**
- **Start with small batches** before processing all works
- **Respect rate limits** - default is 2 seconds between requests
- **Review logs regularly** to catch any issues
- **Get bot permissions** before running in production
- **Estimated time**: ~2.2 hours for all 3,949 works (with 2s delays)

## 🐛 Troubleshooting

### Login Failed
- Verify your username and password are correct
- Check if your account has bot permissions
- Ensure you're not being rate limited

### Work Not Found (404)
- The work may have been deleted or merged
- The work ID might be incorrect in the JSON file

### Update Failed (403 Forbidden)
- Your account may not have bot permissions
- You might not be logged in correctly

### Rate Limiting Issues
- Increase `DELAY_BETWEEN_REQUESTS` value
- Process in smaller batches

## 📚 Resources

- [Open Library Developer Docs](https://openlibrary.org/developers)
- [Open Library API Documentation](https://openlibrary.org/developers/api)
- [Writing Bots for Open Library](https://github.com/internetarchive/openlibrary/wiki/Writing-Bots)
- [Open Library Data Dumps](https://openlibrary.org/developers/dumps)

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👤 Author

**Nishant Singh**
- GitHub: [@NishantSinghhhhh](https://github.com/NishantSinghhhhh)

## 🙏 Acknowledgments

- Open Library team for maintaining the database
- Ray Berger for identifying the duplicate author issue
- Internet Archive for hosting Open Library

## 📊 Statistics

- **Total works affected**: 3,949
- **Date identified**: October 2024
- **Status**: Ready for cleanup

---

**Note**: This bot is designed to improve data quality in Open Library. Always test thoroughly before running in production mode.