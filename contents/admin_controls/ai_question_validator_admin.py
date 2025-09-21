"""
AI Question Validator Admin Interface

This module provides admin interface functionality for the AI question validation tool.
It integrates with the existing admin controls system and provides category selection
and validation management capabilities.
"""

import json
import os
from datetime import datetime
from contents.admin_controls.admin_setup import AdminSetup
from questionmanagement.ai_question_validator import AIQuestionValidator, validate_category_questions
from questionmanagement.question_bank import question_bank


class AIQuestionValidatorAdmin:
    """
    Admin interface for AI question validation functionality.
    Provides methods for managing validation sessions, category selection,
    and applying validation edits through the admin interface.
    """

    def __init__(self):
        """Initialize the validator admin interface."""
        self.admin_setup = AdminSetup()
        # Pass admin_setup to validator so it can use centralized API settings
        self.validator = AIQuestionValidator(admin_setup=self.admin_setup)
        
        # Load saved API settings (for backward compatibility)
        self.api_settings = self.admin_setup.load_saved_api_settings_from_file()
        
    def get_available_categories(self):
        """
        Get list of available question categories.
        
        Returns:
            dict: Dictionary mapping category IDs to category information
        """
        try:
            # Load questions to get updated category information
            question_bank.load_questions()
            
            categories_info = {}
            
            for category_id in question_bank.categories:
                question_count = len(question_bank.categories[category_id])
                
                # Get category display name (use category_id as fallback)
                display_name = category_id.replace('_', ' ').title()
                
                categories_info[category_id] = {
                    'display_name': display_name,
                    'question_count': question_count,
                    'category_id': category_id
                }
            
            return categories_info
            
        except Exception as e:
            print(f"Error getting available categories: {str(e)}")
            return {}

    def validate_selected_categories(self, selected_categories, username=None, required_level='MODERATOR'):
        """
        Validate questions in selected categories.
        
        Args:
            selected_categories (list): List of category IDs to validate
            username (str, optional): Username requesting validation
            required_level (str, optional): Required permission level
            
        Returns:
            dict: Validation results for all selected categories
        """
        # Check permissions - skip for authenticated admin sessions
        # If username is 'admin' from web session, assume they have proper authentication
        if username and username != 'admin' and not self.admin_setup.has_permission(username, required_level):
            raise PermissionError(f"User '{username}' does not have required permission level: {required_level}")
        
        validation_results = {}
        
        for category_id in selected_categories:
            try:
                print(f"Starting validation for category: {category_id}")
                
                # Validate the category using centralized API settings
                # The validator will automatically use admin_setup settings
                validation_id, results = self.validator.validate_category_questions(
                    category_id=category_id,
                    options={
                        'initiated_by': username,
                        'timestamp': datetime.now().isoformat()
                    }
                )
                
                validation_results[category_id] = {
                    'validation_id': validation_id,
                    'results': results,
                    'status': 'completed',
                    'total_questions': len(results),
                    'issues_found': self._count_issues(results)
                }
                
                # Log the validation event
                self.admin_setup.log_event(
                    f"AI validation completed for category '{category_id}' by {username or 'system'}"
                )
                
            except Exception as e:
                print(f"Error validating category {category_id}: {str(e)}")
                validation_results[category_id] = {
                    'validation_id': None,
                    'results': [],
                    'status': 'failed',
                    'error': str(e),
                    'total_questions': 0,
                    'issues_found': 0
                }
        
        return validation_results

    def get_validation_summary(self, validation_id):
        """
        Get a summary of validation results.
        
        Args:
            validation_id (str): The validation ID
            
        Returns:
            dict: Summary of validation results
        """
        try:
            validation_data = self.validator.get_validation_results(validation_id)
            
            if not validation_data:
                return None
            
            # Calculate summary statistics
            results = validation_data['results']
            
            summary = {
                'validation_id': validation_id,
                'category_id': validation_data['category_id'],
                'timestamp': validation_data['timestamp'],
                'total_questions': len(results),
                'questions_with_issues': 0,
                'accuracy_issues': 0,
                'completeness_issues': 0,
                'difficulty_adjustments': 0,
                'score_distribution': {
                    'excellent': 0,
                    'good': 0,
                    'fair': 0,
                    'poor': 0,
                    'unknown': 0
                },
                'recommended_actions': {
                    'keep_as_is': 0,
                    'minor_edit': 0,
                    'major_revision': 0,
                    'remove': 0,
                    'manual_review': 0
                }
            }
            
            for result in results:
                # Count issues
                if result.get('accuracy_issues'):
                    summary['accuracy_issues'] += len(result['accuracy_issues'])
                    summary['questions_with_issues'] += 1
                    
                if result.get('completeness_issues'):
                    summary['completeness_issues'] += len(result['completeness_issues'])
                    if result.get('accuracy_issues'):
                        pass  # Already counted
                    else:
                        summary['questions_with_issues'] += 1
                
                # Check difficulty adjustments
                diff_assessment = result.get('difficulty_assessment', {})
                current_points = diff_assessment.get('current_points', 0)
                suggested_points = diff_assessment.get('suggested_points', 0)
                
                if current_points != suggested_points:
                    summary['difficulty_adjustments'] += 1
                
                # Count score distribution
                score = result.get('overall_score', 'unknown')
                if score in summary['score_distribution']:
                    summary['score_distribution'][score] += 1
                
                # Count recommended actions
                action = result.get('recommended_action', 'manual_review')
                if action in summary['recommended_actions']:
                    summary['recommended_actions'][action] += 1
            
            return summary
            
        except Exception as e:
            print(f"Error getting validation summary: {str(e)}")
            return None

    def format_validation_results_for_display(self, validation_id):
        """
        Format validation results for admin interface display.
        
        Args:
            validation_id (str): The validation ID
            
        Returns:
            dict: Formatted results for display
        """
        try:
            validation_data = self.validator.get_validation_results(validation_id)
            
            if not validation_data:
                return None
            
            # Format results for easy display and selection
            formatted_results = {
                'validation_info': {
                    'validation_id': validation_id,
                    'category_id': validation_data['category_id'],
                    'timestamp': validation_data['timestamp'],
                    'total_questions': len(validation_data['results'])
                },
                'questions': []
            }
            
            for result in validation_data['results']:
                question_id = result['question_id']
                
                # Get original question data for context
                original_question = question_bank.questions.get(question_id, {})
                
                formatted_question = {
                    'question_id': question_id,
                    'original_question': {
                        'question': original_question.get('question', ''),
                        'correct_answer': original_question.get('correct_answer', ''),
                        'points': original_question.get('points', 0),
                        'explanation': original_question.get('explanation', ''),
                        'type': original_question.get('type', '')
                    },
                    'validation_results': result,
                    'selectable_edits': self._create_selectable_edits(result)
                }
                
                formatted_results['questions'].append(formatted_question)
            
            return formatted_results
            
        except Exception as e:
            print(f"Error formatting validation results: {str(e)}")
            return None

    def apply_selected_edits(self, validation_id, selected_edits, username=None):
        """
        Apply selected validation edits.
        
        Args:
            validation_id (str): The validation ID
            selected_edits (dict): Dictionary of selected edits per question
            username (str, optional): Username applying the edits
            
        Returns:
            dict: Summary of applied changes
        """
        try:
            # Apply the edits using the validator
            changes_summary = self.validator.apply_validation_edits(
                validation_id=validation_id,
                selected_edits=selected_edits,
                username=username
            )
            
            # Log the edit application event
            self.admin_setup.log_event(
                f"Applied validation edits: {changes_summary['updated_questions']} questions updated by {username or 'system'}"
            )
            
            return changes_summary
            
        except Exception as e:
            print(f"Error applying selected edits: {str(e)}")
            return {
                'updated_questions': 0,
                'failed_updates': 0,
                'changes_log': [],
                'error': str(e)
            }

    def get_validation_history(self, limit=20):
        """
        Get recent validation history.
        
        Args:
            limit (int, optional): Maximum number of records to return
            
        Returns:
            list: List of recent validation sessions
        """
        try:
            validation_files = []
            validation_dir = self.validator.validation_storage_path
            
            if not os.path.exists(validation_dir):
                return []
            
            # Get all validation files
            for filename in os.listdir(validation_dir):
                if filename.startswith('validation_') and filename.endswith('.json') and not filename.startswith('validation_changes_'):
                    filepath = os.path.join(validation_dir, filename)
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            validation_files.append({
                                'filename': filename,
                                'validation_id': data.get('validation_id'),
                                'category_id': data.get('category_id'),
                                'timestamp': data.get('timestamp'),
                                'total_questions': data.get('total_questions', 0),
                                'filepath': filepath
                            })
                    except Exception as e:
                        print(f"Error reading validation file {filename}: {str(e)}")
                        continue
            
            # Sort by timestamp (newest first)
            validation_files.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return validation_files[:limit]
            
        except Exception as e:
            print(f"Error getting validation history: {str(e)}")
            return []


    def _count_issues(self, results):
        """Count total issues in validation results."""
        total_issues = 0
        
        for result in results:
            total_issues += len(result.get('accuracy_issues', []))
            total_issues += len(result.get('completeness_issues', []))
            
            # Count difficulty adjustments as issues
            diff_assessment = result.get('difficulty_assessment', {})
            current_points = diff_assessment.get('current_points', 0)
            suggested_points = diff_assessment.get('suggested_points', 0)
            
            if current_points != suggested_points:
                total_issues += 1
        
        return total_issues

    def _create_selectable_edits(self, validation_result):
        """
        Create selectable edit options for a validation result.
        
        Args:
            validation_result (dict): The validation result for a question
            
        Returns:
            dict: Selectable edit options
        """
        selectable_edits = {
            'accuracy_fixes': [],
            'completeness_fixes': [],
            'difficulty_adjustment': None
        }
        
        # Create accuracy fix options
        for i, issue in enumerate(validation_result.get('accuracy_issues', [])):
            selectable_edits['accuracy_fixes'].append({
                'index': i,
                'issue': issue['issue'],
                'severity': issue['severity'],
                'suggested_fix': issue['suggested_fix'],
                'selectable': True
            })
        
        # Create completeness fix options
        for i, issue in enumerate(validation_result.get('completeness_issues', [])):
            selectable_edits['completeness_fixes'].append({
                'index': i,
                'issue': issue['issue'],
                'severity': issue['severity'],
                'suggested_fix': issue['suggested_fix'],
                'selectable': True
            })
        
        # Create difficulty adjustment option
        diff_assessment = validation_result.get('difficulty_assessment', {})
        current_points = diff_assessment.get('current_points', 0)
        suggested_points = diff_assessment.get('suggested_points', 0)
        
        if current_points != suggested_points:
            selectable_edits['difficulty_adjustment'] = {
                'current_points': current_points,
                'suggested_points': suggested_points,
                'reasoning': diff_assessment.get('reasoning', ''),
                'selectable': True
            }
        
        return selectable_edits


# Standalone functions for easy integration
def get_available_categories():
    """
    Standalone function to get available question categories.
    
    Returns:
        dict: Available categories information
    """
    admin_validator = AIQuestionValidatorAdmin()
    return admin_validator.get_available_categories()


def validate_selected_categories(selected_categories, username=None):
    """
    Standalone function to validate selected categories.
    
    Args:
        selected_categories (list): List of category IDs
        username (str, optional): Username requesting validation
        
    Returns:
        dict: Validation results
    """
    admin_validator = AIQuestionValidatorAdmin()
    return admin_validator.validate_selected_categories(selected_categories, username)


def get_validation_summary(validation_id):
    """
    Standalone function to get validation summary.
    
    Args:
        validation_id (str): Validation ID
        
    Returns:
        dict: Validation summary
    """
    admin_validator = AIQuestionValidatorAdmin()
    return admin_validator.get_validation_summary(validation_id)


def format_validation_results_for_display(validation_id):
    """
    Standalone function to format validation results for display.
    
    Args:
        validation_id (str): Validation ID
        
    Returns:
        dict: Formatted validation results
    """
    admin_validator = AIQuestionValidatorAdmin()
    return admin_validator.format_validation_results_for_display(validation_id)


def apply_selected_edits(validation_id, selected_edits, username=None):
    """
    Standalone function to apply selected edits.
    
    Args:
        validation_id (str): Validation ID
        selected_edits (dict): Selected edits
        username (str, optional): Username applying edits
        
    Returns:
        dict: Changes summary
    """
    admin_validator = AIQuestionValidatorAdmin()
    return admin_validator.apply_selected_edits(validation_id, selected_edits, username)