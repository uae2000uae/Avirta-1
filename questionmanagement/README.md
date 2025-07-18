# Question Management

This module provides a standalone function for managing Avirta questions, including categorization by topic, difficulty level assignment, and prevention of repeated questions.

## Features

- **Categorization by Topic**: Store questions organized by category (e.g., science, history, geography)
- **Difficulty Levels**: Assign easy, medium, or hard difficulty to each question
- **Prevent Repeats**: Dynamically prevent repeated questions from appearing unless no more questions exist in the category
- **Persistent Storage**: Save questions to disk for later retrieval

## Storage Structure

As of the latest update, the question storage structure has been changed to improve organization and performance:

### Previous Structure
- Each question was stored in an individual JSON file (e.g., `Q0000061.json`, `Q0000062.json`, etc.)
- All question files were stored in the same directory

### New Structure
- Questions are now grouped by category
- Each category has a single JSON file (e.g., `general.json`, `science.json`, etc.)
- Each category file contains an array of all questions in that category

### Migration

A migration script is provided to convert from the old structure to the new structure. To run the migration:

```bash
python -m questionmanagement.migrate_questions
```

The migration script will:
1. Load all existing question files
2. Group them by category
3. Save each category group to a new category file
4. Create a backup of the original files (in a timestamped directory)
5. Optionally remove the old individual files

## Usage

### Adding Questions

```python
from questionmanagement.question_bank import add_question

# Add a question with category and difficulty
add_question({
    "type": "multiple_choice",
    "question": "What is the chemical symbol for gold?",
    "options": ["Au", "Ag", "Fe", "Cu"],
    "correct_answer": "Au"
}, "science", "easy")
```

### Getting Questions

```python
from questionmanagement.question_bank import get_question, get_questions_by_category

# Get a random question from a category
question = get_question("science")

# Get a question with specific difficulty
easy_question = get_question("science", "easy")

# Get all questions in a category
science_questions = get_questions_by_category("science")

# Get questions filtered by difficulty
easy_science = get_questions_by_category("science", "easy")

# Get a limited number of questions
limited_questions = get_questions_by_category("science", limit=5)
```

### Preventing Repeated Questions

The `get_question` function automatically prevents repeated questions from appearing until all questions in the category have been used. Once all questions have been used, the system will reset and start using questions again.

```python
# By default, get_question prevents repeats
question1 = get_question("science")  # First unique question
question2 = get_question("science")  # Second unique question

# If you want to allow repeats, set prevent_repeats to False
question = get_question("science", prevent_repeats=False)

# Reset the used questions tracking for a category
from questionmanagement.question_bank import reset_used_questions
reset_used_questions("science")

# Reset for all categories
reset_used_questions()
```

## Question Import/Export

The `question_import_export.py` module provides functions for importing and exporting questions from/to various file formats, including CSV and Excel (XLS/XLSX).

### Features

- **Export Templates**: Generate template files (CSV or Excel) for users to fill in with questions
- **Import Questions**: Import questions from CSV or Excel files into the question bank
- **Validation**: Validate uploaded content for proper formatting
- **Error Reporting**: Provide detailed error reporting for failed imports

### Usage

```python
from questionmanagement.question_import_export import export_template, import_questions

# Export a template file
success, message = export_template("template.xlsx", format="xlsx")
if success:
    print(f"Template exported: {message}")
else:
    print(f"Error exporting template: {message}")

# Export a CSV template
export_template("template.csv", format="csv")

# Import questions from a file
import_stats = import_questions("questions.xlsx")
print(f"Imported {import_stats['successful']} questions successfully")
print(f"Failed to import {import_stats['failed']} questions")

# Import with custom default category and difficulty
import_stats = import_questions("questions.csv", default_category="science", default_points=300)
```

### Requirements

For Excel file support, the `openpyxl` library is required:

```bash
pip install openpyxl
```

The module will still work without openpyxl, but only CSV files will be supported.

## Example

See the `examples/question_bank_demo.py` file for a complete demonstration of how to use the question bank.

## API Reference

### Functions

#### Question Bank Functions

- `add_question(question_data, category_id="general", difficulty="medium")`: Add a new question to the bank
- `get_question(category_id, difficulty=None, prevent_repeats=True)`: Get a question from the specified category and difficulty
- `get_questions_by_category(category_id, difficulty=None, limit=None)`: Get all questions in a category, optionally filtered by difficulty
- `reset_used_questions(category_id=None)`: Reset the used_questions tracking for a category or all categories

#### Import/Export Functions

- `export_template(output_path, format="xlsx")`: Export a template file for users to fill in with questions
- `import_questions(file_path, default_category="general", default_points=300)`: Import questions from a file (CSV, XLSX) and add them to the question bank

### Question Data Format

Questions should be dictionaries with the following structure:

```python
{
    "type": "multiple_choice",  # or "true_false", "text"
    "question": "The question text",
    "options": ["Option A", "Option B", "Option C", "Option D"],  # for multiple_choice
    "correct_answer": "The correct answer"
}
```

Additional fields will be added automatically:
- `id`: A unique identifier for the question
- `category_id`: The category the question belongs to
- `difficulty`: The difficulty level of the question
- `created_at`: Timestamp when the question was created
- `updated_at`: Timestamp when the question was last updated
- `active`: Whether the question is active
