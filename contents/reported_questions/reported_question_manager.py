"""
Reported Question Manager Module for Avirta

This module handles the management of reported questions,
including storage, retrieval, and editing.
"""

import json
import os
from datetime import datetime

class ReportedQuestionManager:
    """
    A class to handle managing reported questions in Avirta.

    Attributes:
        reported_questions (dict): Dictionary of reported questions indexed by ID
        storage_path (str): Path to store reported question data
    """

    def __init__(self, storage_path="reported_questions"):
        """
        Initialize a new reported question manager.

        Args:
            storage_path (str, optional): Path to store reported question data. Defaults to "reported_questions".
        """
        self.reported_questions = {}
        self.storage_path = storage_path

        # Create storage directory if it doesn't exist
        os.makedirs(storage_path, exist_ok=True)

    def report_question(self, question_data, reporter=None):
        """
        Report a question for review.

        Args:
            question_data (dict): Question data
            reporter (str, optional): Name of the person reporting the question. Defaults to None.

        Returns:
            tuple: (success, message or report_id)
        """
        # Generate a unique ID for the report
        report_id = self._generate_report_id()

        # Add metadata
        report_data = {
            "report_id": report_id,
            "question_id": question_data.get("id"),
            "reported_at": datetime.now().isoformat(),
            "reporter": reporter,
            "status": "pending"  # pending, reviewed, rejected
        }

        # Store the report
        self.reported_questions[report_id] = report_data

        # Save to file
        self._save_report(report_id, report_data)

        return True, report_id

    def get_report(self, report_id, question_uploader=None):
        """
        Get a report by ID.

        Args:
            report_id (str): ID of the report
            question_uploader (QuestionUploader, optional): Question uploader to get question data. Defaults to None.

        Returns:
            dict: Report data or None if not found
        """
        report = self.reported_questions.get(report_id)

        if report and question_uploader and "question_id" in report:
            question_id = report.get("question_id")
            question_data = question_uploader.get_question(question_id)
            if question_data:
                # Add the question data to the report
                report_copy = report.copy()
                report_copy["question_data"] = question_data
                return report_copy

        return report

    def get_all_reports(self, status=None, question_uploader=None):
        """
        Get all reports, optionally filtered by status.

        Args:
            status (str, optional): Status to filter by. Defaults to None.
            question_uploader (QuestionUploader, optional): Question uploader to get question data. Defaults to None.

        Returns:
            list: List of reports with question data
        """
        reports = []
        for report in self.reported_questions.values():
            if status and report.get("status") != status:
                continue

            # If question_uploader is provided, get the question data from the original database
            if question_uploader and "question_id" in report:
                question_id = report.get("question_id")
                question_data = question_uploader.get_question(question_id)
                if question_data:
                    # Add the question data to the report
                    report_copy = report.copy()
                    report_copy["question_data"] = question_data
                    reports.append(report_copy)
                else:
                    # If question not found, still include the report but without question data
                    reports.append(report)
            else:
                reports.append(report)

        return reports

    def update_report_status(self, report_id, status):
        """
        Update the status of a report.

        Args:
            report_id (str): ID of the report
            status (str): New status (pending, reviewed, rejected)

        Returns:
            bool: True if report was updated successfully, False otherwise
        """
        if report_id not in self.reported_questions:
            return False

        self.reported_questions[report_id]["status"] = status
        self.reported_questions[report_id]["updated_at"] = datetime.now().isoformat()

        # Save to file
        self._save_report(report_id, self.reported_questions[report_id])

        return True

    def delete_report(self, report_id):
        """
        Delete a report.

        Args:
            report_id (str): ID of the report to delete

        Returns:
            bool: True if report was deleted successfully, False otherwise
        """
        if report_id not in self.reported_questions:
            return False

        # Remove from memory
        del self.reported_questions[report_id]

        # Remove from storage
        file_path = os.path.join(self.storage_path, f"{report_id}.json")
        if os.path.exists(file_path):
            os.remove(file_path)

        return True

    def load_reports(self):
        """
        Load all reports from storage.

        Returns:
            int: Number of reports loaded
        """
        count = 0
        # Clear existing reports to ensure a clean load
        self.reported_questions = {}

        if os.path.exists(self.storage_path):
            for filename in os.listdir(self.storage_path):
                if filename.endswith(".json"):
                    file_path = os.path.join(self.storage_path, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            report_data = json.load(f)
                            report_id = report_data.get("report_id")
                            if report_id:
                                self.reported_questions[report_id] = report_data
                                count += 1
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"Error loading report from {filename}: {e}")

        return count

    def _generate_report_id(self):
        """
        Generate a unique report ID in the format R####### (R followed by 7 digits).
        Continues the serial system by finding the highest existing ID and incrementing it.

        Returns:
            str: Unique report ID
        """
        # Find the highest existing ID
        highest_num = 0
        for report_id in self.reported_questions.keys():
            # Check if the ID follows the R####### format
            if report_id.startswith('R') and len(report_id) == 8 and report_id[1:].isdigit():
                num = int(report_id[1:])
                if num > highest_num:
                    highest_num = num

        # Increment the highest ID
        new_num = highest_num + 1

        # Format the new ID as R#######
        return f"R{new_num:07d}"

    def _save_report(self, report_id, report_data):
        """
        Save a report to storage.

        Args:
            report_id (str): ID of the report
            report_data (dict): Report data
        """
        file_path = os.path.join(self.storage_path, f"{report_id}.json")
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"Error saving report {report_id}: {e}")
