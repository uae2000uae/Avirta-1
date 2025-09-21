"""
Question Import/Export Module for Question Management

This module provides standalone functions for importing and exporting questions
from/to various file formats, including CSV and Excel (XLS/XLSX).
"""

import os
import csv
import json
import uuid
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from questionmanagement.question_bank import add_question, get_questions_by_category

# Define question types and their required fields
QUESTION_TYPES = ["multiple_choice", "true_false", "text"]
REQUIRED_FIELDS = {
    "multiple_choice": ["question", "options", "correct_answer"],
    "true_false": ["question", "correct_answer"],
    "text": ["question", "correct_answer"]
}

# Define valid points levels
POINTS_LEVELS = [100, 200, 300, 400, 500]

def export_template(output_path, format="xlsx"):
    """
    Export a template file for users to fill in with questions.

    Args:
        output_path (str): Path where the template file will be saved
        format (str, optional): Format of the template file. Defaults to "xlsx".
            Supported formats: "xlsx", "csv"

    Returns:
        tuple: (success, message)
    """
    if format.lower() == "xlsx":
        if not OPENPYXL_AVAILABLE:
            return False, "openpyxl library is required for Excel export. Install with: pip install openpyxl"
        return _export_xlsx_template(output_path)
    elif format.lower() == "csv":
        return _export_csv_template(output_path)
    else:
        return False, f"Unsupported format: {format}. Supported formats: xlsx, csv"

def _export_xlsx_template(output_path):
    """
    Export an Excel template file for users to fill in with questions.

    Args:
        output_path (str): Path where the template file will be saved

    Returns:
        tuple: (success, message)
    """
    try:
        # Create a new workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Questions Template"

        # Define headers
        headers = [
            "question", "type", "category", "points", "correct_answer", 
            "option1", "option2", "option3", "option4", 
            "notes"
        ]

        # Add headers
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            cell.alignment = Alignment(horizontal="center", vertical="center")

            # Set column width based on header length
            ws.column_dimensions[get_column_letter(col_num)].width = max(15, len(header) + 5)

        # Add data validation for type and difficulty
        # Note: This is a simplified version without data validation
        # In a real implementation, you would add data validation for type and difficulty

        # Add instructions sheet
        ws_instructions = wb.create_sheet(title="Instructions")
        instructions = [
            ["Question Template Instructions"],
            [""],
            ["This template is used to create questions for the game."],
            [""],
            ["Field Descriptions:"],
            ["question", "The text of the question"],
            ["type", f"The type of question. Must be one of: {', '.join(QUESTION_TYPES)}"],
            ["category", "The category the question belongs to (e.g., science, history, geography)"],
            ["points", f"Point value for the question. Must be one of: {', '.join(map(str, POINTS_LEVELS))}"],
            ["correct_answer", "The correct answer to the question"],
            ["option1-4", "For multiple_choice questions, the possible answer options"],
            ["notes", "Any additional notes about the question (optional)"]
        ]

        for row_num, instruction in enumerate(instructions, 1):
            if len(instruction) == 1:
                cell = ws_instructions.cell(row=row_num, column=1)
                cell.value = instruction[0]
                if row_num == 1:
                    cell.font = Font(bold=True, size=14)
            else:
                cell_label = ws_instructions.cell(row=row_num, column=1)
                cell_desc = ws_instructions.cell(row=row_num, column=2)
                cell_label.value = instruction[0]
                cell_desc.value = instruction[1]
                if instruction[0] in headers:
                    cell_label.font = Font(bold=True)

        # Adjust column widths
        ws_instructions.column_dimensions['A'].width = 20
        ws_instructions.column_dimensions['B'].width = 80

        # Save the workbook
        wb.save(output_path)
        return True, f"Template exported successfully to {output_path}"

    except Exception as e:
        return False, f"Error exporting template: {str(e)}"

def _export_csv_template(output_path):
    """
    Export a CSV template file for users to fill in with questions.

    Args:
        output_path (str): Path where the template file will be saved

    Returns:
        tuple: (success, message)
    """
    try:
        # Define headers
        headers = [
            "question", "type", "category", "points", "correct_answer", 
            "option1", "option2", "option3", "option4", 
            "notes"
        ]

        # Write to CSV file
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()

        return True, f"Template exported successfully to {output_path}"

    except Exception as e:
        return False, f"Error exporting template: {str(e)}"

def import_questions(file_path, default_category="general", default_points=300):
    """
    Import questions from a file (CSV, XLSX) and add them to the question bank.

    Args:
        file_path (str): Path to the file to import
        default_category (str, optional): Default category for questions. Defaults to "general".
        default_points (int, optional): Default points value for questions. Defaults to 300.
            Must be one of: 100, 200, 300, 400, 500

    Returns:
        dict: Import statistics
    """
    # Initialize import stats
    import_stats = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "errors": []
    }

    # Check if file exists
    if not os.path.exists(file_path):
        import_stats["errors"].append(f"File not found: {file_path}")
        return import_stats

    # Determine file format
    file_extension = os.path.splitext(file_path)[1].lower()[1:]

    # Import based on file format
    if file_extension == "csv":
        return _import_from_csv(file_path, default_category, default_points)
    elif file_extension in ["xlsx", "xls"]:
        if not OPENPYXL_AVAILABLE:
            import_stats["errors"].append("openpyxl library is required for Excel import. Install with: pip install openpyxl")
            return import_stats
        return _import_from_excel(file_path, default_category, default_points)
    else:
        import_stats["errors"].append(f"Unsupported file format: {file_extension}. Supported formats: csv, xlsx, xls")
        return import_stats

def _import_from_csv(file_path, default_category, default_points):
    """
    Import questions from a CSV file.

    Args:
        file_path (str): Path to the CSV file
        default_category (str): Default category for questions
        default_points (int): Default points value for questions

    Returns:
        dict: Import statistics
    """
    import_stats = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "errors": []
    }

    try:
        questions = []

        with open(file_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row_num, row in enumerate(reader, 2):  # Start at 2 to account for header row
                # Convert CSV row to question format
                question = _convert_row_to_question(row, row_num, default_category, default_points)
                if question:
                    questions.append(question)
                else:
                    import_stats["failed"] += 1
                    import_stats["errors"].append(f"Row {row_num}: Invalid question format")

        # Process questions
        return _process_questions(questions, import_stats)

    except Exception as e:
        import_stats["errors"].append(f"Error importing from CSV: {str(e)}")
        return import_stats

def _import_from_excel(file_path, default_category, default_points):
    """
    Import questions from an Excel file.

    Args:
        file_path (str): Path to the Excel file
        default_category (str): Default category for questions
        default_points (int): Default points value for questions

    Returns:
        dict: Import statistics
    """
    import_stats = {
        "total": 0,
        "successful": 0,
        "failed": 0,
        "errors": []
    }

    try:
        # Load workbook
        wb = openpyxl.load_workbook(file_path, read_only=True)

        # Get the first worksheet (skip any instruction sheets)
        ws = None
        for sheet_name in wb.sheetnames:
            if "instruction" not in sheet_name.lower():
                ws = wb[sheet_name]
                break

        if not ws:
            import_stats["errors"].append("No valid worksheet found in the Excel file")
            return import_stats

        # Get headers
        headers = []
        for cell in ws[1]:
            headers.append(cell.value)

        questions = []

        # Process rows
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            # Skip empty rows
            if not any(row):
                continue

            # Convert row to dictionary
            row_dict = {}
            for i, value in enumerate(row):
                if i < len(headers) and headers[i]:
                    row_dict[headers[i]] = value

            # Convert row to question format
            question = _convert_row_to_question(row_dict, row_num, default_category, default_points)
            if question:
                questions.append(question)
            else:
                import_stats["failed"] += 1
                import_stats["errors"].append(f"Row {row_num}: Invalid question format")

        # Process questions
        return _process_questions(questions, import_stats)

    except Exception as e:
        import_stats["errors"].append(f"Error importing from Excel: {str(e)}")
        return import_stats

def _convert_row_to_question(row, row_num, default_category, default_points):
    """
    Convert a row from a CSV or Excel file to a question object.

    Args:
        row (dict): Row as a dictionary
        row_num (int): Row number for error reporting
        default_category (str): Default category for questions
        default_points (int): Default points value for questions

    Returns:
        dict: Question object or None if invalid
    """
    # Skip empty rows
    if not row or not any(row.values()):
        return None

    # Basic validation
    if "question" not in row or not row["question"]:
        return None

    if "type" not in row or not row["type"]:
        return None

    question_type = str(row["type"]).lower()
    if question_type not in QUESTION_TYPES:
        return None

    if "correct_answer" not in row or not row["correct_answer"]:
        return None

    # Create question object
    question = {
        "question": row["question"],
        "type": question_type,
        "correct_answer": row["correct_answer"]
    }

    # Handle category
    if "category" in row and row["category"]:
        question["category_id"] = row["category"]
    else:
        question["category_id"] = default_category

    # Handle points
    if "points" in row and row["points"]:
        points_value = row["points"]
        # Convert string points to numeric if needed
        if isinstance(points_value, str):
            # Check if it's a difficulty string and convert
            difficulty_map = {"easy": 100, "medium": 300, "hard": 500}
            if points_value.lower() in difficulty_map:
                points_value = difficulty_map.get(points_value.lower(), default_points)

        # Try to convert to int if it's a numeric string
        try:
            points_value = int(points_value)
        except (ValueError, TypeError):
            points_value = default_points

        # Validate points
        if points_value in POINTS_LEVELS:
            question["points"] = points_value
        else:
            question["points"] = default_points
    # Handle difficulty field (as per PRJ-002 rule)
    elif "difficulty" in row and row["difficulty"]:
        difficulty_value = row["difficulty"]
        # Convert string difficulty to numeric points
        if isinstance(difficulty_value, str):
            # More comprehensive mapping including easiest and hardest
            difficulty_map = {
                "easiest": 100, 
                "easy": 200, 
                "medium": 300, 
                "hard": 400, 
                "hardest": 500
            }
            # For backward compatibility
            legacy_map = {"easy": 100, "medium": 300, "hard": 500}

            # Try the new map first, then fall back to legacy map
            points_value = difficulty_map.get(
                difficulty_value.lower(), 
                legacy_map.get(difficulty_value.lower(), default_points)
            )
            question["points"] = points_value
        else:
            # Try to convert to int if it's a numeric value
            try:
                difficulty_value = int(difficulty_value)
                # Map to closest valid points value
                question["points"] = min(POINTS_LEVELS, key=lambda x: abs(x - difficulty_value))
            except (ValueError, TypeError):
                question["points"] = default_points
    else:
        question["points"] = default_points

    # Handle options for multiple choice
    if question_type == "multiple_choice":
        options = []

        # Look for option1, option2, etc.
        for i in range(1, 10):  # Assume max 9 options
            option_key = f"option{i}"
            if option_key in row and row[option_key]:
                options.append(row[option_key])

        if not options:
            return None  # No options found for multiple choice

        question["options"] = options

        # Ensure correct_answer is in options
        if question["correct_answer"] not in options:
            options.append(question["correct_answer"])

    # Alternative answers functionality has been removed

    # Handle points
    if "points" in row and row["points"]:
        try:
            question["points"] = int(row["points"])
        except (ValueError, TypeError):
            # If points is not a valid integer, ignore it
            pass

    # Remove difficulty field if present (as per PRJ-002 rule)
    if "difficulty" in question:
        del question["difficulty"]

    return question

def _process_questions(questions, import_stats):
    """
    Process a list of questions and add them to the question bank.

    Args:
        questions (list): List of question objects
        import_stats (dict): Import statistics to update

    Returns:
        dict: Updated import statistics
    """
    import_stats["total"] = len(questions)

    for question in questions:
        try:
            # Get category and points
            category_id = question.pop("category_id", "general")
            points = question.pop("points", 30)

            # Add the question
            success, result = add_question(question, category_id, points)

            if success:
                import_stats["successful"] += 1
            else:
                import_stats["failed"] += 1
                import_stats["errors"].append(f"Question '{question.get('question', 'Unknown')}': {result}")

        except Exception as e:
            import_stats["failed"] += 1
            import_stats["errors"].append(f"Error processing question: {str(e)}")

    return import_stats
