# Avirta Development Guidelines

This document provides essential information for developers working on the Avirta project.

## Build and Configuration Instructions

### Environment Setup

1. **Python Version**: This project requires Python 3.8 or higher.

2. **Virtual Environment**: Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # On Windows
   .\.venv\Scripts\activate
   # On Unix/MacOS
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   - For development:
     ```bash
     pip install -e ".[dev]"
     ```
   - For production:
     ```bash
     pip install -e .
     ```
   - From requirements.txt:
     ```bash
     pip install -r requirements.txt
     ```

### Project Structure

```
avirta/
├── avirta/             # Main package
│   ├── __init__.py     # Package initialization
│   ├── utils.py        # Utility functions
│   ├── question_bank.py # Question bank module
│   └── README.md       # Question bank documentation
├── tests/              # Test directory
│   ├── __init__.py
│   ├── test_utils.py   # Tests for utils module
│   └── test_question_bank.py # Tests for question bank module
├── examples/           # Example scripts
│   └── question_bank_demo.py # Demo of question bank module
├── .flake8             # Flake8 configuration
├── .junie/             # Project documentation
├── pyproject.toml      # Black configuration
├── pytest.ini          # Pytest configuration
├── requirements.txt    # Project dependencies
└── setup.py            # Package installation
```

## Testing Information

### Running Tests

1. **Run all tests**:
   ```bash
   python -m pytest
   ```

2. **Run tests with coverage**:
   ```bash
   python -m pytest --cov=avirta
   ```

3. **Run specific test file**:
   ```bash
   python -m pytest tests/test_utils.py
   ```

4. **Run specific test function**:
   ```bash
   python -m pytest tests/test_utils.py::test_calculate_score_basic
   ```

### Adding New Tests

1. Create a new test file in the `tests` directory with the naming convention `test_*.py`.
2. Import the module/function you want to test.
3. Write test functions with the naming convention `test_*`.
4. Use assertions to verify expected behavior.

Example:

```python
# tests/test_example.py
import pytest
from Avirta.avirta import function_to_test


def test_function_behavior():
    # Arrange
    input_value = "test"
    expected_output = "TEST"

    # Act
    result = function_to_test(input_value)

    # Assert
    assert result == expected_output
```

## Code Style and Development Guidelines

### Code Formatting

This project uses Black for code formatting with a line length of 100 characters:

```bash
# Format all Python files
black .

# Check formatting without making changes
black --check .
```

### Linting

Flake8 is used for linting with the following configuration:
- Max line length: 100 characters
- Ignored rules: E203 (whitespace before ':'), W503 (line break before binary operator)

```bash
# Run linting
flake8
```

### Git Workflow

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit them with descriptive messages:
   ```bash
   git commit -m "Add feature: description of changes"
   ```

3. Push your branch and create a pull request:
   ```bash
   git push origin feature/your-feature-name
   ```

### Documentation

- Use docstrings for all modules, classes, and functions.
- Follow Google-style docstring format as shown in the example below:

```python
def function(param1, param2):
    """Short description of function.

    Longer description if needed.

    Args:
        param1 (type): Description of param1.
        param2 (type): Description of param2.

    Returns:
        type: Description of return value.

    Raises:
        ExceptionType: When and why this exception is raised.
    """
    # Function implementation
```

## Module-Specific Guidelines

### Question Bank Module

The `question_bank.py` module provides a standalone function for managing Avirta questions, including:

1. **Categorization by Topic**: Questions are stored organized by category (e.g., science, history)
2. **Difficulty Levels**: Each question is assigned a difficulty level (easy, medium, hard)
3. **Prevent Repeats**: The system prevents repeated questions until all questions in a category have been used

#### Using the Question Bank

```python
# Import the functions
from Avirta.avirta.question_bank import add_question, get_question, get_questions_by_category, reset_used_questions

# Add a question
add_question({
    "type": "multiple_choice",
    "question": "What is the capital of France?",
    "options": ["Paris", "London", "Berlin", "Madrid"],
    "correct_answer": "Paris"
}, "geography", "easy")

# Get a question (prevents repeats by default)
question = get_question("geography")

# Get a question with specific difficulty
easy_question = get_question("geography", "easy")

# Get all questions in a category
all_questions = get_questions_by_category("geography")

# Reset used questions tracking
reset_used_questions("geography")
```

For more details, see the documentation in `avirta/README.md` and the example in `examples/question_bank_demo.py`.

### Question Import/Export Module

The `question_import_export.py` module provides standalone functions for importing and exporting Avirta questions from/to various file formats, including CSV and Excel (XLS/XLSX).

#### Features

1. **Export Templates**: Generate template files (CSV or Excel) for users to fill in with questions
2. **Import Questions**: Import questions from CSV or Excel files into the question bank
3. **Validation**: Validate uploaded content for proper formatting
4. **Error Reporting**: Provide detailed error reporting for failed imports

#### Using the Question Import/Export Module

```python
from Avirta.avirta import export_template, import_questions

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
import_stats = import_questions("questions.csv", default_category="science", default_difficulty="easy")
```

#### Requirements

For Excel file support, the `openpyxl` library is required:

```bash
pip install openpyxl
```

The module will still work without openpyxl, but only CSV files will be supported.

## Debugging and Troubleshooting

### Common Issues

1. **Import errors**: Ensure you've installed the package in development mode with `pip install -e .`

2. **Test failures**: Check that your virtual environment has all development dependencies installed with `pip install -e ".[dev]"`

3. **Code style issues**: Run `black .` to automatically format your code according to the project's style guidelines
