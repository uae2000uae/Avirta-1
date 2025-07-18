"""
Bulk Import Module for Avirta

This module handles the bulk importing of questions from various file formats
like CSV, JSON, or Excel, allowing administrators to quickly add multiple questions at once.
"""

import json
import csv
import os
from datetime import datetime

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from questionmanagement.question_import_export import _import_from_excel

class BulkImport:
    """
    A class to handle bulk importing of Avirta questions.

    Attributes:
        question_uploader (object): Reference to the QuestionUploader instance
        category_manager (object): Reference to the CategoryManager instance
        supported_formats (list): List of supported file formats
        import_stats (dict): Statistics about the import process
    """

    def __init__(self, question_uploader, category_manager):
        """
        Initialize a new bulk import handler.

        Args:
            question_uploader (object): Reference to the QuestionUploader instance
            category_manager (object): Reference to the CategoryManager instance
        """
        self.question_uploader = question_uploader
        self.category_manager = category_manager
        self.supported_formats = ["json", "csv"]

        # Add Excel formats if openpyxl is available
        if OPENPYXL_AVAILABLE:
            self.supported_formats.extend(["xlsx", "xls"])
        self.import_stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "errors": []
        }

    def import_from_file(self, file_path, default_category="general", create_categories=True):
        """
        Import questions from a file.

        Args:
            file_path (str): Path to the file to import
            default_category (str, optional): Default category for questions. Defaults to "general".
            create_categories (bool, optional): Whether to create missing categories. Defaults to True.

        Returns:
            dict: Import statistics
        """
        # Reset import stats
        self.import_stats = {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "errors": []
        }

        # Check if file exists
        if not os.path.exists(file_path):
            self.import_stats["errors"].append(f"File not found: {file_path}")
            return self.import_stats

        # Determine file format
        file_extension = os.path.splitext(file_path)[1].lower()[1:]
        if file_extension not in self.supported_formats:
            self.import_stats["errors"].append(f"Unsupported file format: {file_extension}")
            return self.import_stats

        # Import based on file format
        if file_extension == "json":
            self._import_from_json(file_path, default_category, create_categories)
        elif file_extension == "csv":
            self._import_from_csv(file_path, default_category, create_categories)
        elif file_extension in ["xlsx", "xls"]:
            if not OPENPYXL_AVAILABLE:
                self.import_stats["errors"].append("openpyxl library is required for Excel import. Install with: pip install openpyxl")
                return self.import_stats
            self._import_from_excel_file(file_path, default_category, create_categories)

        return self.import_stats

    def _import_from_json(self, file_path, default_category, create_categories):
        """
        Import questions from a JSON file.

        Args:
            file_path (str): Path to the JSON file
            default_category (str): Default category for questions
            create_categories (bool): Whether to create missing categories
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                questions = json.load(f)

            if not isinstance(questions, list):
                self.import_stats["errors"].append("JSON file must contain a list of questions")
                return

            self._process_questions(questions, default_category, create_categories)

        except json.JSONDecodeError as e:
            self.import_stats["errors"].append(f"Invalid JSON file: {str(e)}")
        except Exception as e:
            self.import_stats["errors"].append(f"Error importing from JSON: {str(e)}")

    def _import_from_excel_file(self, file_path, default_category, create_categories):
        """
        Import questions from an Excel file.

        Args:
            file_path (str): Path to the Excel file
            default_category (str): Default category for questions
            create_categories (bool): Whether to create missing categories
        """
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
                self.import_stats["errors"].append("No valid worksheet found in the Excel file")
                return

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
                question = self._convert_csv_row_to_question(row_dict)
                if question:
                    questions.append(question)
                else:
                    self.import_stats["failed"] += 1
                    self.import_stats["errors"].append(f"Row {row_num}: Invalid question format")

            # Process the questions
            self._process_questions(questions, default_category, create_categories)

        except Exception as e:
            self.import_stats["errors"].append(f"Error importing from Excel: {str(e)}")

    def _import_from_csv(self, file_path, default_category, create_categories):
        """
        Import questions from a CSV file.

        Args:
            file_path (str): Path to the CSV file
            default_category (str): Default category for questions
            create_categories (bool): Whether to create missing categories
        """
        try:
            questions = []

            with open(file_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Convert CSV row to question format
                    question = self._convert_csv_row_to_question(row)
                    if question:
                        questions.append(question)

            self._process_questions(questions, default_category, create_categories)

        except Exception as e:
            self.import_stats["errors"].append(f"Error importing from CSV: {str(e)}")

    def _convert_csv_row_to_question(self, row):
        """
        Convert a CSV row to a question object.

        Args:
            row (dict): CSV row as a dictionary

        Returns:
            dict: Question object or None if invalid
        """
        # Basic validation
        if "question" not in row or not row["question"]:
            return None

        if "type" not in row or not row["type"]:
            return None

        if "correct_answer" not in row or not row["correct_answer"]:
            return None

        question = {
            "question": row["question"],
            "type": row["type"].lower(),
            "correct_answer": row["correct_answer"]
        }

        # Handle category
        if "category" in row and row["category"]:
            question["category_id"] = row["category"]

        # Handle options for multiple choice
        if question["type"] == "multiple_choice":
            options = []

            # Look for option1, option2, etc.
            for i in range(1, 10):  # Assume max 9 options
                option_key = f"option{i}"
                if option_key in row and row[option_key]:
                    options.append(row[option_key])

            # Also check for comma-separated options
            if "options" in row and row["options"]:
                options.extend([opt.strip() for opt in row["options"].split(",")])

            if not options:
                return None  # No options found for multiple choice

            question["options"] = options

            # Ensure correct_answer is in options
            if question["correct_answer"] not in options:
                options.append(question["correct_answer"])

        # Alternative answers functionality has been removed

        # Define valid points levels
        points_levels = [100, 200, 300, 400, 500]

        # Handle points
        if "points" in row and row["points"]:
            try:
                points_value = int(row["points"])
                # Validate points are in the allowed range
                if points_value in points_levels:
                    question["points"] = points_value
                else:
                    # Find closest valid points value
                    closest_points = min(points_levels, key=lambda x: abs(x - points_value))
                    question["points"] = closest_points
            except ValueError:
                # Check if it's a string difficulty and convert
                if isinstance(row["points"], str):
                    difficulty_map = {"easy": 100, "medium": 300, "hard": 500}
                    if row["points"].lower() in difficulty_map:
                        question["points"] = difficulty_map.get(row["points"].lower(), 300)
                    else:
                        question["points"] = 300  # Default if conversion fails
                else:
                    question["points"] = 300  # Default if conversion fails
        # Handle legacy difficulty field
        elif "difficulty" in row and row["difficulty"]:
            difficulty_value = row["difficulty"]
            # Convert string difficulty to numeric if needed
            if isinstance(difficulty_value, str):
                difficulty_map = {"easy": 100, "medium": 300, "hard": 500}
                difficulty_value = difficulty_map.get(difficulty_value.lower(), 300)

            # Try to convert to int if it's a numeric string
            try:
                difficulty_value = int(difficulty_value)
            except (ValueError, TypeError):
                difficulty_value = 300

            # Map to closest points value
            closest_points = min(points_levels, key=lambda x: abs(x - difficulty_value))
            question["points"] = closest_points
        else:
            # Default points if neither points nor difficulty is specified
            question["points"] = 300

        return question

    def _process_questions(self, questions, default_category, create_categories):
        """
        Process a list of questions for import.

        Args:
            questions (list): List of question objects
            default_category (str): Default category for questions
            create_categories (bool): Whether to create missing categories
        """
        self.import_stats["total"] = len(questions)

        for question in questions:
            try:
                # Get category ID
                category_id = question.get("category_id", default_category)

                # Check if category exists
                if self.category_manager.get_category(category_id) is None:
                    if create_categories:
                        # Create the category
                        category_name = category_id.replace("_", " ").title()
                        self.category_manager.add_category(category_id, category_name)
                    else:
                        # Use default category
                        category_id = default_category

                # Add the question
                result = self.question_uploader.add_question(question, category_id)

                if result[0]:
                    self.import_stats["successful"] += 1
                    # Increment question count for the category
                    self.category_manager.increment_question_count(category_id)
                else:
                    self.import_stats["failed"] += 1
                    self.import_stats["errors"].append(f"Question '{question.get('question', 'Unknown')}': {result[1]}")

            except Exception as e:
                self.import_stats["failed"] += 1
                self.import_stats["errors"].append(f"Error processing question: {str(e)}")

    def export_to_file(self, file_path, category_id=None, question_ids=None):
        """
        Export questions to a file.

        Args:
            file_path (str): Path to save the exported file
            category_id (str, optional): Export only questions from this category. Defaults to None.
            question_ids (list, optional): Export only these specific questions. Defaults to None.

        Returns:
            tuple: (success, message)
        """
        # Determine file format
        file_extension = os.path.splitext(file_path)[1].lower()[1:]
        if file_extension not in self.supported_formats:
            return False, f"Unsupported file format: {file_extension}"

        # Get questions to export
        questions = []

        if question_ids:
            # Export specific questions
            for question_id in question_ids:
                question = self.question_uploader.get_question(question_id)
                if question:
                    questions.append(question)
        elif category_id:
            # Export questions from a category
            questions = self.question_uploader.get_questions_by_category(category_id)
        else:
            # Export all questions
            questions = list(self.question_uploader.questions.values())

        if not questions:
            return False, "No questions to export"

        # Export based on file format
        try:
            if file_extension == "json":
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(questions, f, indent=2, ensure_ascii=False)
            elif file_extension == "csv":
                self._export_to_csv(file_path, questions)
            elif file_extension in ["xlsx", "xls"]:
                if not OPENPYXL_AVAILABLE:
                    return False, "openpyxl library is required for Excel export. Install with: pip install openpyxl"
                self._export_to_excel(file_path, questions)

            return True, f"Successfully exported {len(questions)} questions to {file_path}"

        except Exception as e:
            return False, f"Error exporting questions: {str(e)}"

    def _export_to_excel(self, file_path, questions):
        """
        Export questions to an Excel file.

        Args:
            file_path (str): Path to save the Excel file
            questions (list): List of question objects to export
        """
        # Create a new workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Questions"

        # Determine all possible fields
        fields = set()
        for question in questions:
            fields.update(question.keys())

        # Ensure essential fields come first
        essential_fields = ["id", "question", "type", "category_id", "correct_answer", "points"]
        fieldnames = essential_fields + [f for f in sorted(fields) if f not in essential_fields]

        # Add headers
        for col_num, header in enumerate(fieldnames, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.font = openpyxl.styles.Font(bold=True)
            cell.fill = openpyxl.styles.PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
            cell.alignment = openpyxl.styles.Alignment(horizontal="center", vertical="center")

            # Set column width based on header length
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_num)].width = max(15, len(header) + 5)

        # Add data
        for row_num, question in enumerate(questions, 2):
            row = question.copy()

            # Convert options list to string for Excel
            if "options" in row and isinstance(row["options"], list):
                row["options"] = ",".join(row["options"])

            # Write each field
            for col_num, field in enumerate(fieldnames, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = row.get(field, "")

        # Add instructions sheet
        ws_instructions = wb.create_sheet(title="Instructions")
        instructions = [
            ["Question Export Instructions"],
            [""],
            ["This file contains exported questions from the Avirta system."],
            [""],
            ["Field Descriptions:"],
            ["id", "Unique identifier for the question"],
            ["question", "The text of the question"],
            ["type", "The type of question (multiple_choice, true_false, text)"],
            ["category_id", "The category the question belongs to"],
            ["correct_answer", "The correct answer to the question"],
            ["points", "Point value for the question (100, 200, 300, 400, 500)"],
            ["options", "For multiple_choice questions, comma-separated answer options"]
        ]

        for row_num, instruction in enumerate(instructions, 1):
            if len(instruction) == 1:
                cell = ws_instructions.cell(row=row_num, column=1)
                cell.value = instruction[0]
                if row_num == 1:
                    cell.font = openpyxl.styles.Font(bold=True, size=14)
            else:
                cell_label = ws_instructions.cell(row=row_num, column=1)
                cell_desc = ws_instructions.cell(row=row_num, column=2)
                cell_label.value = instruction[0]
                cell_desc.value = instruction[1]
                if instruction[0] in fieldnames:
                    cell_label.font = openpyxl.styles.Font(bold=True)

        # Adjust column widths
        ws_instructions.column_dimensions['A'].width = 20
        ws_instructions.column_dimensions['B'].width = 80

        # Save the workbook
        wb.save(file_path)

    def _export_to_csv(self, file_path, questions):
        """
        Export questions to a CSV file.

        Args:
            file_path (str): Path to save the CSV file
            questions (list): List of question objects to export
        """
        # Determine all possible fields
        fields = set()
        for question in questions:
            fields.update(question.keys())

        # Ensure essential fields come first
        essential_fields = ["id", "question", "type", "category_id", "correct_answer"]
        fieldnames = essential_fields + [f for f in sorted(fields) if f not in essential_fields]

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for question in questions:
                # Convert options list to string for CSV
                row = question.copy()
                if "options" in row and isinstance(row["options"], list):
                    row["options"] = ",".join(row["options"])

                # Alternative answers functionality has been removed

                writer.writerow(row)
