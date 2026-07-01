"""
AI Question Validator Module for Question Management

This module provides functionality for validating and assessing existing questions using AI services.
It can identify inaccurate information, missing answers, and suggest difficulty level adjustments.
"""

import json
import uuid
import os
import glob
import requests
from datetime import datetime
from questionmanagement.question_bank import question_bank
from contents.admin_controls.openai_models import is_known_model, get_max_output_tokens, get_model_config


class AIQuestionValidator:
    """
    A class to validate and assess questions using AI services.

    This class provides methods for validating question accuracy, completeness,
    and difficulty level appropriateness.
    """

    def __init__(self, validation_storage_path=None, admin_setup=None):
        """
        Initialize a new AI question validator.

        Args:
            validation_storage_path (str, optional): Path to store validation results.
                If None, defaults to "contents/question_validations".
            admin_setup (AdminSetup, optional): Admin setup instance for centralized API settings.
                If provided, API settings will be automatically retrieved from system configuration.
        """
        # Set default path if none provided
        if validation_storage_path is None:
            validation_storage_path = os.path.join("contents", "question_validations")
        
        # Convert to absolute path if it's a relative path
        if not os.path.isabs(validation_storage_path):
            # Get the absolute path relative to the current script location
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.validation_storage_path = os.path.join(base_dir, validation_storage_path)
        else:
            self.validation_storage_path = validation_storage_path

        # Create storage directory if it doesn't exist
        os.makedirs(self.validation_storage_path, exist_ok=True)

        # Store admin_setup reference for centralized API settings
        self.admin_setup = admin_setup

        # OpenAI API settings - will be retrieved from admin_setup if available
        if admin_setup and hasattr(admin_setup, 'game_settings'):
            gs = admin_setup.game_settings
            self.api_key = gs.get('openai_api_key', '')
            # Modern default model
            self.model = gs.get('openai_model', 'gpt-4o-mini')
            # Lower temperature for more consistent validation
            self.temperature = gs.get('openai_temperature', 0.3)
            self.top_p = gs.get('openai_top_p', 1.0)
            self.frequency_penalty = gs.get('openai_frequency_penalty', 0.0)
            self.presence_penalty = gs.get('openai_presence_penalty', 0.0)
            self.reasoning_effort = gs.get('openai_reasoning_effort', 'medium')
            self.verbosity = gs.get('openai_verbosity', 'medium')
            self.response_format = gs.get('openai_response_format', None)
            # Support legacy boolean json mode flag
            if not self.response_format and gs.get('openai_json_mode', False):
                self.response_format = {"type": "json_object"}
            elif isinstance(self.response_format, str) and self.response_format.lower() == 'json_object':
                self.response_format = {"type": "json_object"}
            self.base_url = gs.get('openai_base_url', 'https://api.openai.com/v1')
            self.organization = gs.get('openai_organization', None)
            self.user = gs.get('openai_user', None)
            self.request_timeout = gs.get('openai_request_timeout', 60)
            # Limit max_output_tokens to the selected model's real cap
            configured_tokens = gs.get('openai_max_tokens', gs.get('openai_max_output_tokens', 3000))
            cap = get_max_output_tokens(self.model) if is_known_model(self.model) else 16384
            self.max_output_tokens = min(configured_tokens, cap)
            # Seed (optional determinism)
            self.seed = gs.get('openai_seed', 0)
        else:
            # Fallback to default settings if no admin_setup provided
            self.api_key = None
            self.model = 'gpt-4o-mini'
            self.temperature = 0.3  # Lower temperature for more consistent validation
            self.top_p = 1.0
            self.frequency_penalty = 0.0
            self.presence_penalty = 0.0
            self.reasoning_effort = 'medium'
            self.verbosity = 'medium'
            self.response_format = None
            self.base_url = 'https://api.openai.com/v1'
            self.organization = None
            self.user = None
            self.request_timeout = 60
            self.max_output_tokens = 3000
            self.seed = 0

        # API connection status
        self.api_connected = False

        # Internal helper: redact secrets in logs
        self._secret_prefix = (self.api_key or '').strip()[:5]

    def _is_reasoning_model(self) -> bool:
        """Whether self.model is a reasoning-family model (e.g. GPT-5.x) rather
        than a standard chat-completions model (e.g. GPT-4o). Reasoning models
        don't accept temperature/top_p/frequency_penalty/presence_penalty."""
        if is_known_model(self.model):
            return get_model_config(self.model).get('family') == 'reasoning'
        return False

    def _generation_params(self, max_tokens_value, temperature_override=None):
        """Build the model-appropriate sampling/reasoning + token-limit params for a request payload."""
        if self._is_reasoning_model():
            params = {"max_completion_tokens": max_tokens_value}
            if getattr(self, 'reasoning_effort', None):
                params["reasoning_effort"] = self.reasoning_effort
            if getattr(self, 'verbosity', None):
                params["verbosity"] = self.verbosity
            return params

        temperature = self.temperature if temperature_override is None else temperature_override
        return {
            "temperature": min(max(temperature, 0.0), 2.0),
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "max_tokens": max_tokens_value,
        }

    def validate_category_questions(self, category_id, api_key=None, options=None):
        """
        Validate all questions in a specific category.

        Args:
            category_id (str): The category ID to validate
            api_key (str, optional): OpenAI API key. If not provided, will use centralized settings.
            options (dict, optional): Validation options

        Returns:
            tuple: (validation_id, validation_results) where validation_id is a unique
                identifier for this validation session and validation_results contains
                the assessment results
        """
        if options is None:
            options = {}

        # Use provided API key or fall back to centralized settings
        if api_key:
            self.api_key = api_key
        elif not self.api_key and self.admin_setup:
            # Refresh API settings from admin_setup in case they were updated
            gs = self.admin_setup.game_settings
            self.api_key = gs.get('openai_api_key', '')
            self.model = gs.get('openai_model', 'gpt-4o-mini')
            self.temperature = gs.get('openai_temperature', 0.3)
            self.top_p = gs.get('openai_top_p', 1.0)
            self.frequency_penalty = gs.get('openai_frequency_penalty', 0.0)
            self.presence_penalty = gs.get('openai_presence_penalty', 0.0)
            self.reasoning_effort = gs.get('openai_reasoning_effort', self.reasoning_effort)
            self.verbosity = gs.get('openai_verbosity', self.verbosity)
            self.response_format = gs.get('openai_response_format', self.response_format)
            if not self.response_format and gs.get('openai_json_mode', False):
                self.response_format = {"type": "json_object"}
            elif isinstance(self.response_format, str) and self.response_format.lower() == 'json_object':
                self.response_format = {"type": "json_object"}
            self.base_url = gs.get('openai_base_url', self.base_url)
            self.organization = gs.get('openai_organization', self.organization)
            self.user = gs.get('openai_user', self.user)
            self.request_timeout = gs.get('openai_request_timeout', self.request_timeout)
            # Limit max_output_tokens to the selected model's real cap
            configured_tokens = gs.get('openai_max_tokens', gs.get('openai_max_output_tokens', 3000))
            cap = get_max_output_tokens(self.model) if is_known_model(self.model) else 16384
            self.max_output_tokens = min(configured_tokens, cap)
            self.seed = gs.get('openai_seed', self.seed)

        # Check if we have a valid API key
        if not self.api_key or not self.api_key.strip():
            raise ValueError("OpenAI API key not configured. Please configure API settings in admin controls.")

        # Verify API connection
        if not self._verify_api_connection():
            raise ValueError("Failed to connect to OpenAI API")

        # Load questions from the category
        question_bank.load_questions()
        
        if category_id not in question_bank.categories:
            raise ValueError(f"Category '{category_id}' not found")

        # Get all questions in the category
        questions_to_validate = []
        for question_id in question_bank.categories[category_id]:
            if question_id in question_bank.questions:
                question = question_bank.questions[question_id].copy()
                questions_to_validate.append(question)

        if not questions_to_validate:
            raise ValueError(f"No questions found in category '{category_id}'")

        print(f"Validating {len(questions_to_validate)} questions in category '{category_id}'")

        # Validate questions using AI
        validation_results = self._validate_questions_with_openai(
            questions_to_validate, 
            category_id,
            options
        )

        # Generate validation ID and save results
        validation_id = str(uuid.uuid4())
        self._save_validation_results(validation_id, category_id, validation_results)

        return validation_id, validation_results

    def _verify_api_connection(self):
        """Verify the connection to the OpenAI API."""
        if not self.api_key or not self.api_key.strip():
            return False

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key.strip()}"
            }
            if self.organization:
                headers["OpenAI-Organization"] = str(self.organization)

            # Respect JSON mode if configured
            wants_json = False
            rf = self.response_format
            if isinstance(rf, dict) and rf.get("type") == "json_object":
                wants_json = True

            messages = (
                [
                    {"role": "system", "content": "You are a connectivity tester. Reply only with a small valid JSON object and nothing else."},
                    {"role": "user", "content": "Please respond with a JSON object: {\"ok\": true}"}
                ]
                if wants_json
                else [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello, test connection."}
                ]
            )

            data = {
                "model": self.model,
                "messages": messages,
                **self._generation_params(20 if wants_json else 50),
            }
            if self.response_format:
                data["response_format"] = self.response_format
            if self.user:
                data["user"] = self.user
            try:
                if int(self.seed) > 0:
                    data["seed"] = int(self.seed)
            except Exception:
                pass

            base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
            url = f"{base}/chat/completions"

            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=self.request_timeout or 60
            )

            return response.status_code == 200

        except Exception as e:
            print(f"API connection failed: {str(e)}")
            return False

    def _improve_questions_with_openai(self, questions, category_id, options, progress_tracker=None):
        """
        Generate improved versions of questions using OpenAI API.

        Args:
            questions (list): List of question dictionaries to improve
            category_id (str): The category ID
            options (dict): Improvement options
            progress_tracker (dict, optional): Dictionary to track progress based on terminal output

        Returns:
            list: List of improved question dictionaries
        """
        # Create system prompt for question improvement
        system_prompt = """You are an expert educational content creator. Improve quiz questions by:
1. Fixing inaccuracies: correct any factual errors in questions or answers.
2. Completing missing information: add explanations where missing, fix incomplete answers.
3. Adjusting difficulty: set an appropriate point value (100=easy, 200=medium-easy, 300=medium, 400=hard, 500=very hard).
4. Improving clarity: make questions clearer and more precise.
5. Fixing formatting: proper punctuation, grammar, and structure.

Key rules:
- Replace placeholder answers (e.g. "Add '?' at the end of the question") with actual correct answers.
- Add missing explanations for every question.
- Ensure questions end with proper punctuation.
- Preserve all original metadata (id, timestamps, category_id, use_count, active) unchanged.

Return a JSON array of COMPLETE improved question objects - every original field preserved, options only present for multiple_choice, points a number 100-500. Example shape:
{"type": "original_type", "question": "improved text?", "correct_answer": "improved answer", "options": ["...", "...", "...", "..."], "explanation": "why this is correct", "points": 300, "id": "original_id", "created_at": "original_created_at", "updated_at": "current_timestamp", "active": true, "category_id": "original_category_id", "use_count": 0}"""

        improved_questions = []
        batch_size = 5  # Smaller batches for more detailed processing
        total_batches = (len(questions) + batch_size - 1) // batch_size  # Calculate total batches

        for i in range(0, len(questions), batch_size):
            batch = questions[i:i + batch_size]
            batch_number = i // batch_size + 1
            
            # Update progress tracker BEFORE processing (starting batch)
            if progress_tracker:
                progress_tracker['total_batches'] = total_batches
                progress_tracker['current_batch'] = batch_number
                progress_tracker['message'] = f"Improving batch {batch_number} ({len(batch)} questions)"
                progress_tracker['stage'] = f"Processing questions {i + 1}-{min(i + len(batch), len(questions))} of {len(questions)}"
            
            # Create user prompt with the batch of questions
            user_prompt = f"Improve these questions from the '{category_id}' category:\n"
            for question in batch:
                user_prompt += f"\nQuestion {question.get('id', 'unknown')}: {json.dumps(question, ensure_ascii=False, separators=(',', ':'))}"
            user_prompt += "\n\nReturn a JSON array with the complete improved question objects (preserve all original fields, just improve the content)."

            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key.strip()}"
                }
                if self.organization:
                    headers["OpenAI-Organization"] = str(self.organization)

                data = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    **self._generation_params(self.max_output_tokens),
                }
                if self.response_format:
                    data["response_format"] = self.response_format
                if self.user:
                    data["user"] = self.user
                try:
                    if int(self.seed) > 0:
                        data["seed"] = int(self.seed)
                except Exception:
                    pass

                print(f"Improving batch {i//batch_size + 1} ({len(batch)} questions)...")
                base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
                url = f"{base}/chat/completions"
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=self.request_timeout or 90
                )

                if response.status_code == 200:
                    response_data = response.json()
                    content = response_data['choices'][0]['message']['content']
                    
                    # Parse the JSON response
                    try:
                        # Clean up the content - remove markdown code block wrappers if present
                        cleaned_content = content.strip()
                        if cleaned_content.startswith('```json'):
                            cleaned_content = cleaned_content[7:]  # Remove ```json
                        if cleaned_content.startswith('```'):
                            cleaned_content = cleaned_content[3:]  # Remove ```
                        if cleaned_content.endswith('```'):
                            cleaned_content = cleaned_content[:-3]  # Remove trailing ```
                        cleaned_content = cleaned_content.strip()
                        
                        batch_results = json.loads(cleaned_content)
                        if isinstance(batch_results, list):
                            # Update timestamps and ensure all required fields
                            for improved_q in batch_results:
                                improved_q['updated_at'] = datetime.now().isoformat()
                            improved_questions.extend(batch_results)
                        else:
                            # If single result, wrap in list
                            batch_results['updated_at'] = datetime.now().isoformat()
                            improved_questions.append(batch_results)
                            
                        # Update progress tracker AFTER successful batch completion
                        if progress_tracker:
                            progress_tracker['completed_batches'] = batch_number
                            progress_tracker['overall_percentage'] = (batch_number / total_batches) * 100
                            progress_tracker['message'] = f"Completed batch {batch_number} of {total_batches}"
                            
                    except json.JSONDecodeError:
                        print(f"Failed to parse AI response for batch {i//batch_size + 1}")
                        print(f"AI response content: {content[:500]}...")  # Show first 500 chars
                        # If parsing fails, return original questions with minimal improvements
                        for question in batch:
                            improved_q = question.copy()
                            # At least fix obvious issues
                            if improved_q.get('correct_answer') == "Add '?' at the end of the question":
                                improved_q['correct_answer'] = "Manual review needed"
                            if not improved_q.get('explanation'):
                                improved_q['explanation'] = "Explanation needs to be added"
                            improved_q['updated_at'] = datetime.now().isoformat()
                            improved_questions.append(improved_q)
                            
                        # Update progress even on parsing failure
                        if progress_tracker:
                            progress_tracker['completed_batches'] = batch_number
                            progress_tracker['overall_percentage'] = (batch_number / total_batches) * 100
                            progress_tracker['message'] = f"Batch {batch_number} completed with parsing issues"
                else:
                    print(f"API request failed for batch {i//batch_size + 1}: {response.status_code}")
                    print(f"API response: {response.text}")
                    # If API fails, return original questions
                    for question in batch:
                        improved_q = question.copy()
                        improved_q['updated_at'] = datetime.now().isoformat()
                        improved_questions.append(improved_q)
                    
                    # Update progress even on API failure
                    if progress_tracker:
                        progress_tracker['completed_batches'] = batch_number
                        progress_tracker['overall_percentage'] = (batch_number / total_batches) * 100
                        progress_tracker['message'] = f"Batch {batch_number} completed with API error"

            except Exception as e:
                print(f"Error improving batch {i//batch_size + 1}: {str(e)}")
                # If error occurs, return original questions
                for question in batch:
                    improved_q = question.copy()
                    improved_q['updated_at'] = datetime.now().isoformat()
                    improved_questions.append(improved_q)
                
                # Update progress even on exception
                if progress_tracker:
                    progress_tracker['completed_batches'] = batch_number
                    progress_tracker['overall_percentage'] = (batch_number / total_batches) * 100
                    progress_tracker['message'] = f"Batch {batch_number} completed with error"

        # Report final completion
        if progress_tracker:
            progress_tracker['completed_batches'] = total_batches
            progress_tracker['overall_percentage'] = 100
            progress_tracker['message'] = f"Completed all {total_batches} batches"
            progress_tracker['stage'] = f"Successfully processed all {len(questions)} questions"

        return improved_questions

    def _validate_questions_with_openai(self, questions, category_id, options):
        """
        Validate questions using OpenAI API.

        Args:
            questions (list): List of question dictionaries to validate
            category_id (str): The category ID
            options (dict): Validation options

        Returns:
            list: List of validation results for each question
        """
        # Create system prompt for question validation
        system_prompt = """You are an expert educational content validator. Assess each question for:
1. Accuracy: is the information in the question and answer factually correct?
2. Completeness: is the answer complete and present?
3. Difficulty: does the points value (100=easy, 200=medium-easy, 300=medium, 400=hard, 500=very hard) match the question's actual complexity?

Return a JSON array with one object per question, in this exact structure:
{"question_id": "<must exactly match the Question ID given in the input, unchanged>", "accuracy_issues": [{"issue": "...", "severity": "low|medium|high", "suggested_fix": "..."}], "completeness_issues": [{"issue": "...", "severity": "low|medium|high", "suggested_fix": "..."}], "difficulty_assessment": {"current_points": 300, "suggested_points": 300, "reasoning": "..."}, "overall_score": "excellent|good|fair|poor", "recommended_action": "keep_as_is|minor_edit|major_revision|remove"}

Use an empty array when a category has no issues. Be thorough but practical - flag only issues that would meaningfully impact educational value."""

        validation_results = []
        batch_size = 10  # Process questions in batches to avoid token limits

        for i in range(0, len(questions), batch_size):
            batch = questions[i:i + batch_size]

            # Create user prompt with the batch of questions
            user_prompt = f"Validate these questions from the '{category_id}' category:\n"
            for question in batch:
                user_prompt += (
                    f"\nQuestion ID: {question.get('id', 'unknown')} | Type: {question.get('type', 'unknown')} | "
                    f"Points: {question.get('points', 0)}\n"
                    f"Question: {question.get('question', '')}\n"
                    f"Correct Answer: {question.get('correct_answer', '')}\n"
                    f"Explanation: {question.get('explanation', '')}"
                )
            user_prompt += "\n\nRespond with a JSON array containing one validation result per question, in the same order, using the exact question_id given above."

            try:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key.strip()}"
                }

                data = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    **self._generation_params(self.max_output_tokens),
                }
                if self.response_format:
                    data["response_format"] = self.response_format
                if self.user:
                    data["user"] = self.user
                try:
                    if int(self.seed) > 0:
                        data["seed"] = int(self.seed)
                except Exception:
                    pass

                print(f"Validating batch {i//batch_size + 1} ({len(batch)} questions)...")
                base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
                url = f"{base}/chat/completions"
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=self.request_timeout or 60
                )

                if response.status_code == 200:
                    response_data = response.json()
                    content = response_data['choices'][0]['message']['content']
                    
                    # Parse the JSON response
                    try:
                        # Clean up the content - remove markdown code block wrappers if present
                        cleaned_content = content.strip()
                        if cleaned_content.startswith('```json'):
                            cleaned_content = cleaned_content[7:]  # Remove ```json
                        if cleaned_content.startswith('```'):
                            cleaned_content = cleaned_content[3:]  # Remove ```
                        if cleaned_content.endswith('```'):
                            cleaned_content = cleaned_content[:-3]  # Remove trailing ```
                        cleaned_content = cleaned_content.strip()
                        
                        batch_results = json.loads(cleaned_content)
                        if isinstance(batch_results, list):
                            validation_results.extend(batch_results)
                        else:
                            # If single result, wrap in list
                            validation_results.append(batch_results)
                    except json.JSONDecodeError:
                        print(f"Failed to parse AI response for batch {i//batch_size + 1}")
                        print(f"AI response content: {content[:500]}...")  # Show first 500 chars
                        # Create fallback results for this batch
                        for question in batch:
                            validation_results.append({
                                "question_id": question.get('id', 'unknown'),
                                "accuracy_issues": [],
                                "completeness_issues": [{"issue": "Could not validate - AI response parsing failed", "severity": "medium", "suggested_fix": "Manual review required"}],
                                "difficulty_assessment": {
                                    "current_points": question.get('points', 0),
                                    "suggested_points": question.get('points', 0),
                                    "reasoning": "Could not assess due to parsing error"
                                },
                                "overall_score": "unknown",
                                "recommended_action": "manual_review"
                            })
                else:
                    print(f"API request failed for batch {i//batch_size + 1}: {response.status_code}")
                    print(f"API response: {response.text}")
                    # Create fallback results for this batch
                    for question in batch:
                        validation_results.append({
                            "question_id": question.get('id', 'unknown'),
                            "accuracy_issues": [],
                            "completeness_issues": [{"issue": "Could not validate - API request failed", "severity": "medium", "suggested_fix": "Manual review required"}],
                            "difficulty_assessment": {
                                "current_points": question.get('points', 0),
                                "suggested_points": question.get('points', 0),
                                "reasoning": "Could not assess due to API error"
                            },
                            "overall_score": "unknown",
                            "recommended_action": "manual_review"
                        })

            except Exception as e:
                print(f"Error validating batch {i//batch_size + 1}: {str(e)}")
                # Create fallback results for this batch
                for question in batch:
                    validation_results.append({
                        "question_id": question.get('id', 'unknown'),
                        "accuracy_issues": [],
                        "completeness_issues": [{"issue": f"Could not validate - {str(e)}", "severity": "medium", "suggested_fix": "Manual review required"}],
                        "difficulty_assessment": {
                            "current_points": question.get('points', 0),
                            "suggested_points": question.get('points', 0),
                            "reasoning": "Could not assess due to error"
                        },
                        "overall_score": "unknown",
                        "recommended_action": "manual_review"
                    })

        return validation_results

    def _save_validation_results(self, validation_id, category_id, results):
        """Save validation results to file."""
        try:
            validation_data = {
                "validation_id": validation_id,
                "category_id": category_id,
                "timestamp": datetime.now().isoformat(),
                "total_questions": len(results),
                "results": results
            }

            filename = f"validation_{category_id}_{validation_id}.json"
            filepath = os.path.join(self.validation_storage_path, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(validation_data, f, ensure_ascii=False, indent=2)

            print(f"Validation results saved to: {filepath}")
        except Exception as e:
            print(f"Error saving validation results: {str(e)}")

    def get_validation_results(self, validation_id):
        """Retrieve validation results by ID."""
        try:
            pattern = os.path.join(self.validation_storage_path, f"validation_*_{validation_id}.json")
            matching_files = glob.glob(pattern)
            
            if not matching_files:
                return None
            
            with open(matching_files[0], 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error retrieving validation results: {str(e)}")
            return None

    def apply_validation_edits(self, validation_id, selected_edits, username=None):
        """
        Apply selected validation edits to question files.
        
        Args:
            validation_id (str): The validation session ID
            selected_edits (dict): Dictionary mapping question_id to selected edit actions
            username (str, optional): Username applying the edits
            
        Returns:
            dict: Summary of applied changes
        """
        # Get validation results
        validation_data = self.get_validation_results(validation_id)
        if not validation_data:
            raise ValueError(f"Validation results not found for ID: {validation_id}")

        category_id = validation_data['category_id']
        results = validation_data['results']
        
        # Load current questions
        question_bank.load_questions()
        
        changes_summary = {
            "updated_questions": 0,
            "failed_updates": 0,
            "changes_log": []
        }

        # Apply selected edits
        for result in results:
            question_id = result['question_id']
            
            if question_id not in selected_edits:
                continue
                
            edit_actions = selected_edits[question_id]
            
            if question_id not in question_bank.questions:
                changes_summary["failed_updates"] += 1
                changes_summary["changes_log"].append({
                    "question_id": question_id,
                    "status": "failed",
                    "reason": "Question not found in database"
                })
                continue

            # Get the current question
            current_question = question_bank.questions[question_id].copy()
            original_question = current_question.copy()
            question_updated = False

            # Apply accuracy fixes
            if 'accuracy_fixes' in edit_actions:
                for fix_index in edit_actions['accuracy_fixes']:
                    if fix_index < len(result['accuracy_issues']):
                        fix = result['accuracy_issues'][fix_index]
                        # Apply the suggested fix (this is a simplified implementation)
                        # In a real implementation, you'd have more sophisticated logic
                        if 'correct_answer' in fix['suggested_fix'].lower():
                            current_question['correct_answer'] = fix['suggested_fix'].replace('Suggested answer: ', '')
                        elif 'question' in fix['suggested_fix'].lower():
                            current_question['question'] = fix['suggested_fix'].replace('Suggested question: ', '')
                        question_updated = True

            # Apply completeness fixes
            if 'completeness_fixes' in edit_actions:
                for fix_index in edit_actions['completeness_fixes']:
                    if fix_index < len(result['completeness_issues']):
                        fix = result['completeness_issues'][fix_index]
                        # Apply completeness fix
                        if 'explanation' in fix['issue'].lower() and not current_question.get('explanation'):
                            current_question['explanation'] = fix['suggested_fix']
                        question_updated = True

            # Apply difficulty adjustment
            if 'apply_difficulty_adjustment' in edit_actions and edit_actions['apply_difficulty_adjustment']:
                new_points = result['difficulty_assessment']['suggested_points']
                if new_points != current_question.get('points', 0):
                    current_question['points'] = new_points
                    question_updated = True

            # Update timestamp if question was modified
            if question_updated:
                current_question['updated_at'] = datetime.now().isoformat()
                
                # Update the question in the database
                try:
                    question_bank.questions[question_id] = current_question
                    # Save to the actual JSON file
                    self._update_question_in_file(category_id, question_id, current_question)
                    
                    changes_summary["updated_questions"] += 1
                    changes_summary["changes_log"].append({
                        "question_id": question_id,
                        "status": "updated",
                        "original": original_question,
                        "updated": current_question,
                        "applied_by": username,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                except Exception as e:
                    changes_summary["failed_updates"] += 1
                    changes_summary["changes_log"].append({
                        "question_id": question_id,
                        "status": "failed",
                        "reason": str(e)
                    })

        # Save change log to separate file
        self._save_change_log(validation_id, changes_summary)
        
        return changes_summary

    def _update_question_in_file(self, category_id, question_id, updated_question):
        """Update a specific question in its JSON file."""
        try:
            # Find the question file - get the project root and construct the correct path
            # validation_storage_path is typically contents/question_validations
            # So we need to go up to project root and then to contents/questions
            project_root = os.path.dirname(os.path.dirname(self.validation_storage_path))
            questions_dir = os.path.join(project_root, "contents", "questions")
            question_file = os.path.join(questions_dir, f"{category_id}.json")
            
            if not os.path.exists(question_file):
                raise ValueError(f"Question file not found: {question_file}")
            
            # Load the current file
            with open(question_file, 'r', encoding='utf-8') as f:
                questions_data = json.load(f)
            
            # Find and update the specific question
            for i, question in enumerate(questions_data):
                if question.get('id') == question_id:
                    questions_data[i] = updated_question
                    break
            else:
                raise ValueError(f"Question {question_id} not found in file")
            
            # Save the updated file
            with open(question_file, 'w', encoding='utf-8') as f:
                json.dump(questions_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            raise Exception(f"Failed to update question file: {str(e)}")

    def _save_change_log(self, validation_id, changes_summary):
        """Save the change log to a separate dataset."""
        try:
            log_filename = f"validation_changes_{validation_id}.json"
            log_filepath = os.path.join(self.validation_storage_path, log_filename)
            
            with open(log_filepath, 'w', encoding='utf-8') as f:
                json.dump(changes_summary, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Error saving change log: {str(e)}")


# Standalone functions for easy integration
def validate_category_questions(category_id, api_key, options=None):
    """
    Standalone function to validate questions in a category.
    
    Args:
        category_id (str): Category to validate
        api_key (str): OpenAI API key
        options (dict, optional): Validation options
        
    Returns:
        tuple: (validation_id, validation_results)
    """
    validator = AIQuestionValidator()
    return validator.validate_category_questions(category_id, api_key, options)


def get_validation_results(validation_id):
    """
    Standalone function to get validation results.
    
    Args:
        validation_id (str): Validation ID
        
    Returns:
        dict: Validation results or None if not found
    """
    validator = AIQuestionValidator()
    return validator.get_validation_results(validation_id)


def apply_validation_edits(validation_id, selected_edits, username=None):
    """
    Standalone function to apply validation edits.
    
    Args:
        validation_id (str): Validation ID
        selected_edits (dict): Selected edit actions
        username (str, optional): Username applying edits
        
    Returns:
        dict: Summary of applied changes
    """
    validator = AIQuestionValidator()
    return validator.apply_validation_edits(validation_id, selected_edits, username)