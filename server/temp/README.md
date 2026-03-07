# Temporary Files Directory

This directory contains temporary files generated during development, testing, and debugging.

## Structure

- **categorization/** - Output files from categorization scripts
- **uploads/** - Temporary file uploads (if needed)
- **debug/** - Debug output files
- **test_results/** - Test output files

## Usage

### Categorization Scripts

The categorization scripts (`categorize_simple.py` and `categorize_transactions.py`) automatically save results here:

```bash
# Run with default output location (temp/categorization/result_{timestamp}.json)
python categorize_simple.py

# Specify custom output location
python categorize_simple.py --output my_results.json

# Only print to stdout, don't save file
python categorize_simple.py --no-file
```

### Cleanup

Files in this directory are git-ignored and can be safely deleted at any time:

```bash
# Clean all temporary files
rm -rf temp/categorization/* temp/debug/* temp/test_results/*

# Keep .gitkeep files
find temp -name ".gitkeep" -o -type f -delete
```

## Git Configuration

All JSON, CSV, and TXT files in subdirectories are automatically ignored by git (see `.gitignore`), but the directory structure is preserved via `.gitkeep` files.
