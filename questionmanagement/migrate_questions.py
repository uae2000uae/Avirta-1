"""
Migration Script for Question Bank

This script migrates questions from individual files to category-based files.
It reads all existing question files, groups them by category, and saves them
to category-based JSON files.
"""

import os
import json
import shutil
from datetime import datetime

def migrate_questions(questions_dir, backup_dir=None):
    """
    Migrate questions from individual files to category-based files.
    
    Args:
        questions_dir (str): Directory containing question files
        backup_dir (str, optional): Directory to backup original files. If None, no backup is made.
        
    Returns:
        tuple: (success, message)
    """
    # Create backup directory if specified
    if backup_dir:
        os.makedirs(backup_dir, exist_ok=True)
        
    # Check if questions directory exists
    if not os.path.exists(questions_dir):
        return False, f"Questions directory {questions_dir} does not exist"
        
    # Dictionary to store questions by category
    categories = {}
    
    # Count of processed files
    processed_count = 0
    
    # Process all question files
    for filename in os.listdir(questions_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(questions_dir, filename)
            
            # Skip if it's already a category file (filename doesn't start with Q)
            if not filename.startswith("Q"):
                continue
                
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    question_data = json.load(f)
                    
                # Get category ID, default to "general" if not specified
                category_id = question_data.get("category_id", "general")
                
                # Initialize category if not exists
                if category_id not in categories:
                    categories[category_id] = []
                    
                # Add question to category
                categories[category_id].append(question_data)
                
                # Backup original file if backup directory is specified
                if backup_dir:
                    backup_path = os.path.join(backup_dir, filename)
                    shutil.copy2(file_path, backup_path)
                
                processed_count += 1
                
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error processing file {filename}: {e}")
    
    # Save questions by category
    saved_categories = 0
    for category_id, questions in categories.items():
        category_file = os.path.join(questions_dir, f"{category_id}.json")
        try:
            with open(category_file, "w", encoding="utf-8") as f:
                json.dump(questions, f, indent=2)
            saved_categories += 1
        except IOError as e:
            print(f"Error saving category file {category_file}: {e}")
    
    # Return success message
    return True, f"Migrated {processed_count} questions to {saved_categories} category files"

def remove_individual_files(questions_dir):
    """
    Remove individual question files after migration.
    
    Args:
        questions_dir (str): Directory containing question files
        
    Returns:
        int: Number of files removed
    """
    removed_count = 0
    
    for filename in os.listdir(questions_dir):
        if filename.endswith(".json") and filename.startswith("Q"):
            file_path = os.path.join(questions_dir, filename)
            try:
                os.remove(file_path)
                removed_count += 1
            except IOError as e:
                print(f"Error removing file {filename}: {e}")
    
    return removed_count

if __name__ == "__main__":
    # Default paths
    questions_dir = os.path.join("contents", "questions")
    backup_dir = os.path.join("contents", "questions_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    # Convert paths to absolute paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    questions_dir = os.path.join(base_dir, questions_dir)
    backup_dir = os.path.join(base_dir, backup_dir)
    
    print(f"Migrating questions from {questions_dir}")
    print(f"Backing up to {backup_dir}")
    
    # Migrate questions
    success, message = migrate_questions(questions_dir, backup_dir)
    print(message)
    
    if success:
        # Ask user if they want to remove individual files
        response = input("Do you want to remove individual question files? (y/n): ")
        if response.lower() == "y":
            removed_count = remove_individual_files(questions_dir)
            print(f"Removed {removed_count} individual question files")
        else:
            print("Individual question files were not removed")
    
    print("Migration complete")