"""
AI Question Generator Module for Question Management

This module provides functionality for generating questions using AI services.
It supports generating multiple types of questions (multiple choice, true/false, text)
with customizable options.
"""

import json
import uuid
import os
import re
from datetime import datetime
import requests
from questionmanagement.question_bank import question_bank

class AIQuestionGenerator:
    """
    A class to generate questions using AI services.

    This class provides methods for generating questions based on prompts,
    with customizable options for question type, difficulty, etc.
    """

    def __init__(self, temp_storage_path=None):
        """
        Initialize a new AI question generator.

        Args:
            temp_storage_path (str, optional): Path to store temporarily generated questions.
                If None, defaults to "contents/ai_generated_questions".
        """
        # Set default path if none provided
        if temp_storage_path is None:
            temp_storage_path = os.path.join("contents", "ai_generated_questions")
        # Convert to absolute path if it's a relative path
        if not os.path.isabs(temp_storage_path):
            # Get the absolute path relative to the current script location
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.temp_storage_path = os.path.join(base_dir, temp_storage_path)
        else:
            self.temp_storage_path = temp_storage_path

        # Create storage directory if it doesn't exist
        os.makedirs(self.temp_storage_path, exist_ok=True)

        # Dictionary to store generated question batches
        self.question_batches = {}

        # OpenAI API settings (will be set by the web app)
        self.api_key = None
        self.model = "gpt-3.5-turbo"
        self.temperature = 0.7
        self.max_tokens = 2000

        # API connection status
        self.api_connected = False

    def generate_questions(self, prompt, options=None):
        """
        Generate questions based on a prompt and options.

        Args:
            prompt (str): The prompt to generate questions from
            options (dict, optional): Options for generation. Defaults to None.
                Possible options:
                - question_type: Type of questions to generate (mixed, multiple_choice, true_false, text)
                - difficulty: Difficulty level (mixed, easy, medium, hard)
                - num_questions: Number of questions to generate
                - include_explanations: Whether to include explanations for correct answers
                - language: Language for questions (english, arabic)
                - reference_categories: List of category IDs to read and avoid repeating questions from
                - api_key: OpenAI API key
                - model: OpenAI model to use
                - temperature: Temperature for generation
                - max_tokens: Maximum tokens for generation

        Returns:
            tuple: (batch_id, questions) where batch_id is a unique identifier for this batch
                and questions is a list of generated question dictionaries

        Raises:
            ValueError: If no valid API key is provided or API connection fails
        """
        if options is None:
            options = {}

        # Set default options
        question_type = options.get('question_type', 'mixed')
        difficulty = options.get('difficulty', 'mixed')
        num_questions = int(options.get('num_questions', 20))
        include_explanations = options.get('include_explanations', True)
        language = options.get('language', 'arabic')
        reference_categories = options.get('reference_categories', [])

        # Get API settings from options if provided
        self.api_key = options.get('api_key', self.api_key)
        self.model = options.get('model', self.model)
        self.temperature = float(options.get('temperature', self.temperature))
        self.max_tokens = int(options.get('max_tokens', self.max_tokens))

        # Check if API key is provided and not empty
        if not self.api_key or not self.api_key.strip():
            raise ValueError("OpenAI API key is required to generate questions. Please provide a valid API key.")

        print(f"API key is provided (length: {len(self.api_key.strip())}). Verifying OpenAI API connection...")

        # Verify the API connection first
        connection_success, connection_message = self.verify_api_connection()

        if not connection_success:
            raise ValueError(f"OpenAI API connection failed: {connection_message}")

        print(f"OpenAI API connection successful. Attempting to generate questions.")
        try:
            questions = self._generate_questions_with_openai(
                prompt, 
                question_type, 
                difficulty, 
                num_questions, 
                include_explanations,
                language,
                reference_categories
            )
            # If successful, return the questions
            if questions:
                print(f"Successfully generated {len(questions)} questions with OpenAI API.")
                # Generate a unique batch ID
                batch_id = str(uuid.uuid4())

                # Store the batch
                self.question_batches[batch_id] = questions

                # Create metadata
                metadata = {
                    'prompt': prompt,
                    'question_type': question_type,
                    'difficulty': difficulty,
                    'num_questions': num_questions,
                    'include_explanations': include_explanations,
                    'language': language,
                    'timestamp': datetime.now().isoformat()
                }

                # Save to temporary storage with metadata
                self._save_batch(batch_id, questions, metadata)

                return batch_id, questions
            else:
                raise ValueError("OpenAI API returned no questions. Please try again with a different prompt or settings.")
        except Exception as e:
            print(f"Error generating questions with OpenAI: {str(e)}")
            raise ValueError(f"Failed to generate questions with OpenAI: {str(e)}")

    def get_batch(self, batch_id):
        """
        Get a batch of generated questions by ID.

        Args:
            batch_id (str): The batch ID

        Returns:
            list: The list of questions in the batch, or None if not found
        """
        # Try to get from memory first
        if batch_id in self.question_batches:
            return self.question_batches[batch_id]

        # If not in memory, try to load from storage
        batch_path = os.path.join(self.temp_storage_path, f"{batch_id}.json")
        if os.path.exists(batch_path):
            try:
                with open(batch_path, 'r', encoding="utf-8") as f:
                    batch_data = json.load(f)

                # Handle both old and new format
                if isinstance(batch_data, list):
                    # Old format: just a list of questions
                    questions = batch_data
                elif isinstance(batch_data, dict) and 'questions' in batch_data:
                    # New format: dict with 'metadata' and 'questions'
                    questions = batch_data['questions']
                else:
                    # Unknown format
                    print(f"Unknown batch data format for batch {batch_id}")
                    return None

                # Cache in memory
                self.question_batches[batch_id] = questions
                return questions
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for batch {batch_id}: {str(e)}")
                return None
            except Exception as e:
                print(f"Unexpected error loading batch {batch_id}: {str(e)}")
                return None

        return None

    def get_batch_metadata(self, batch_id):
        """
        Get metadata for a batch of generated questions by ID.

        Args:
            batch_id (str): The batch ID

        Returns:
            dict: The metadata for the batch, or None if not found or no metadata exists
        """
        # Try to load from storage
        batch_path = os.path.join(self.temp_storage_path, f"{batch_id}.json")
        if os.path.exists(batch_path):
            try:
                with open(batch_path, 'r', encoding="utf-8") as f:
                    batch_data = json.load(f)

                # Handle both old and new format
                if isinstance(batch_data, dict) and 'metadata' in batch_data:
                    # New format: dict with 'metadata' and 'questions'
                    return batch_data['metadata']
                elif isinstance(batch_data, list):
                    # Old format: just a list of questions, no metadata
                    # Create basic metadata with file creation time and estimated question count
                    return {
                        'timestamp': datetime.fromtimestamp(os.path.getctime(batch_path)).isoformat(),
                        'num_questions': len(batch_data),
                        'prompt': 'Unknown (Legacy Format)',
                        'question_type': 'mixed',
                        'difficulty': 'mixed',
                        'language': 'unknown'
                    }
                else:
                    # Unknown format but still a valid JSON, create minimal metadata
                    return {
                        'timestamp': datetime.fromtimestamp(os.path.getctime(batch_path)).isoformat(),
                        'prompt': 'Unknown Format',
                        'question_type': 'unknown',
                        'difficulty': 'unknown',
                        'language': 'unknown'
                    }
            except json.JSONDecodeError:
                # If JSON is invalid, still return minimal metadata so it shows in the list
                return {
                    'timestamp': datetime.fromtimestamp(os.path.getctime(batch_path)).isoformat(),
                    'prompt': 'Invalid JSON Format',
                    'question_type': 'unknown',
                    'difficulty': 'unknown',
                    'language': 'unknown'
                }

        return None

    def _save_batch(self, batch_id, questions, metadata=None):
        """
        Save a batch of questions to temporary storage.

        Args:
            batch_id (str): The batch ID
            questions (list): The list of questions to save
            metadata (dict, optional): Additional metadata about the batch. Defaults to None.
        """
        # If no metadata is provided, create an empty dict
        if metadata is None:
            metadata = {}

        # Add timestamp if not present
        if 'timestamp' not in metadata:
            metadata['timestamp'] = datetime.now().isoformat()

        # Create a structure that includes both metadata and questions
        batch_data = {
            'metadata': metadata,
            'questions': questions
        }

        batch_path = os.path.join(self.temp_storage_path, f"{batch_id}.json")
        with open(batch_path, 'w', encoding="utf-8") as f:
            json.dump(batch_data, f, indent=2, ensure_ascii=False)

    def verify_api_connection(self):
        """
        Verify the connection to the OpenAI API.

        Returns:
            tuple: (success, message) where success is a boolean indicating if the connection was successful
                and message is a string with details about the connection status
        """
        if not self.api_key or not self.api_key.strip():
            self.api_connected = False
            print(f"API key validation failed. API key: '{self.api_key}'")
            return False, "OpenAI API key is missing or empty"

        try:
            # Prepare a simple API request to test the connection
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key.strip()}"  # Ensure no whitespace in the API key
            }

            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello, are you connected?"}
                ],
                "temperature": 0.7,
                "max_tokens": 50
            }

            print(f"Verifying OpenAI API connection with key: '{self.api_key[:5]}...'")
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data
            )

            if response.status_code == 200:
                self.api_connected = True
                print("OpenAI API connection successful")
                return True, "OpenAI API connection successful"
            else:
                self.api_connected = False
                error_message = f"OpenAI API error: {response.status_code} - {response.text}"
                print(error_message)
                return False, error_message

        except requests.exceptions.RequestException as e:
            self.api_connected = False
            error_message = f"Failed to connect to OpenAI API: {str(e)}"
            print(error_message)
            return False, error_message
        except Exception as e:
            self.api_connected = False
            error_message = f"Unexpected error during API connection verification: {str(e)}"
            print(error_message)
            return False, error_message

    def _generate_questions_with_openai(self, prompt, question_type, difficulty, num_questions, include_explanations, language='english', reference_categories=None):
        """
        Generate questions using the OpenAI API.

        Args:
            prompt (str): The prompt to generate questions from
            question_type (str): Type of questions to generate
            difficulty (str): Difficulty level
            num_questions (int): Number of questions to generate
            include_explanations (bool): Whether to include explanations
            language (str, optional): Language for questions (english, arabic). Defaults to 'english'.
            reference_categories (list, optional): List of category IDs to read and avoid repeating questions from.

        Returns:
            list: A list of generated question dictionaries
        """
        # Ensure API key is valid
        if not self.api_key or not self.api_key.strip():
            print(f"OpenAI API key is missing or empty: '{self.api_key}'")
            raise ValueError("OpenAI API key is required")

        # Use the stripped API key to avoid any whitespace issues
        api_key = self.api_key.strip()

        print(f"Preparing to call OpenAI API with model: {self.model}, temperature: {self.temperature}")
        print(f"Generating {num_questions} {question_type} questions with difficulty: {difficulty}")
        print(f"Using API key: '{api_key[:5]}...'")

        # Get existing questions from reference categories if provided
        existing_questions = []
        if reference_categories and len(reference_categories) > 0:
            print(f"Reading questions from {len(reference_categories)} reference categories")
            # Ensure question_bank has the latest data
            question_bank.load_questions()

            # Collect questions from each selected category
            for category_id in reference_categories:
                if category_id in question_bank.categories:
                    category_questions = []
                    for question_id in question_bank.categories[category_id]:
                        if question_id in question_bank.questions:
                            question = question_bank.questions[question_id]
                            # Add only the question text to avoid making the prompt too long
                            question_text = question.get('question', '')
                            if question_text:
                                category_questions.append(question_text)

                    if category_questions:
                        print(f"Found {len(category_questions)} questions in category {category_id}")
                        existing_questions.extend(category_questions)
                else:
                    print(f"Category {category_id} not found in question bank")

        # Create a system prompt that instructs the AI how to format the response
        system_prompt = """
        You are a question generator for an educational game. Generate questions based on the user's prompt.
        Set the difficulty level of the generated questions from the perspective of an average high school student.
        The "points": 100|200|300|400|500 are to define how difficult the questions are or much the information is common,
        the higher the points, the harder the questions.
        Format your response as a JSON array of question objects with the following structure:

        For multiple-choice questions:
        {
            "type": "multiple_choice",
            "question": "The question text",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "The correct option (exactly matching one of the options)",
            "explanation": "Explanation of why this is the correct answer",
            "points": 100|200|300|400|500
        }

        For true/false questions:
        {
            "type": "true_false",
            "question": "The question text",
            "correct_answer": "True|False",
            "explanation": "Explanation of why this is correct",
            "points": 100|200|300|400|500
        }

        For text questions:
        {
            "type": "text",
            "question": "The question text",
            "correct_answer": "The correct answer",
            "explanation": "Explanation of why this is correct",
            "points": 100|200|300|400|500
        }
        """

        # Add existing questions to the system prompt if available
        if existing_questions:
            existing_questions_text = "\n".join([f"- {q}" for q in existing_questions[:50]])  # Limit to 50 questions to avoid token limits
            system_prompt += f"""

            IMPORTANT: Avoid generating questions that are similar to the following existing questions:
            {existing_questions_text}

            If there are more than 50 existing questions, I've only shown you a subset. Please try to generate questions that are substantially different from these and would explore new aspects of the topic.
            """

        # Add specific instructions based on options
        if question_type != 'mixed':
            system_prompt += f"\nOnly generate {question_type} questions."

        if difficulty != 'mixed':
            # Map difficulty to points
            difficulty_level = {"easiest": 100, "easy": 200, "medium": 300, "hard": 400, "hardest": 500}
            points_value = difficulty_level.get(difficulty, 0)  # Get the correct point value
            system_prompt += f"\nAll questions should have {points_value} points."
        else:
            system_prompt += "\nGenerate questions across all difficulty levels."

        if not include_explanations:
            system_prompt += "\nDo not include explanations."

        # Add language-specific instructions
        if language.lower() == 'arabic':
            system_prompt += "\nGenerate all questions and answers in Arabic language. Use proper Arabic grammar and vocabulary."
        else:
            system_prompt += "\nGenerate all questions and answers in English language."

        # Create the user prompt
        user_prompt = f"Generate {num_questions} questions about: {prompt}"

        # Prepare the API request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # Use the stripped API key
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        print("Making API request to OpenAI...")
        try:
            # Make the API request
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data
            )

            # Check for errors
            if response.status_code != 200:
                error_message = f"OpenAI API error: {response.status_code} - {response.text}"
                print(error_message)
                raise Exception(error_message)

            print("Received successful response from OpenAI API")
            # Parse the response
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            print(f"Response content length: {len(content)} characters")

            # Try to extract JSON from the response
            try:
                # Find JSON array in the response using regex
                json_match = re.search(r'\[.*\]', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)
                    print("Found JSON array in response")
                else:
                    print("No JSON array found in response, attempting to parse full content")

                # Parse the JSON
                questions = json.loads(content)
                print(f"Successfully parsed JSON with {len(questions)} questions")

                # Validate the questions
                validated_questions = []
                for i, question in enumerate(questions):
                    print(f"Validating question {i+1}...")
                    # Ensure required fields are present
                    if 'type' not in question or 'question' not in question or 'correct_answer' not in question:
                        print(f"Question {i+1} missing required fields, skipping")
                        continue

                    # Ensure multiple choice questions have options
                    if question['type'] == 'multiple_choice' and ('options' not in question or not question['options']):
                        print(f"Multiple choice question {i+1} missing options, skipping")
                        continue


                    # Ensure points are set correctly based on difficulty
                    # Map difficulty to points
                    difficulty_points = {"easiest": 100, "easy": 200, "medium": 300, "hard": 400, "hardest": 500}

                    # Always set points based on difficulty if not mixed
                    if difficulty != 'mixed':
                        question['points'] = difficulty_points.get(difficulty, 300)
                        print(f"Set points to {question['points']} for question {i+1} based on difficulty: {difficulty}")
                    elif 'points' not in question:
                        # For mixed difficulty, only set default points if not already present
                        question['points'] = 300
                        print(f"Added default points (300) to question {i+1} for mixed difficulty")

                    # Remove difficulty field if present (as per PRJ-002 rule)
                    if 'difficulty' in question:
                        del question['difficulty']
                        print(f"Removed difficulty field from question {i+1} as per PRJ-002 rule")

                    validated_questions.append(question)
                    print(f"Question {i+1} validated successfully")

                print(f"Validation complete. {len(validated_questions)} of {len(questions)} questions are valid.")
                return validated_questions

            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {str(e)}")
                print(f"Content that failed to parse: {content[:500]}...")  # Print first 500 chars
                return None
            except Exception as e:
                print(f"Error validating questions: {str(e)}")
                print(f"Response content: {content[:500]}...")  # Print first 500 chars
                return None

        except requests.exceptions.RequestException as e:
            print(f"Request error: {str(e)}")
            raise Exception(f"Failed to connect to OpenAI API: {str(e)}")
        except Exception as e:
            print(f"Unexpected error during API call: {str(e)}")
            raise


# Create a singleton instance
ai_question_generator = AIQuestionGenerator()

def generate_questions(prompt, options=None):
    """
    Generate questions based on a prompt and options.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        prompt (str): The prompt to generate questions from
        options (dict, optional): Options for generation. Defaults to None.
            Possible options:
            - question_type: Type of questions to generate (mixed, multiple_choice, true_false, text)
            - difficulty: Difficulty level (mixed, easy, medium, hard)
            - num_questions: Number of questions to generate
            - include_explanations: Whether to include explanations for correct answers
            - language: Language for questions (english, arabic)
            - api_key: OpenAI API key
            - model: OpenAI model to use
            - temperature: Temperature for generation
            - max_tokens: Maximum tokens for generation

    Returns:
        tuple: (batch_id, questions) where batch_id is a unique identifier for this batch
            and questions is a list of generated question dictionaries
    """
    return ai_question_generator.generate_questions(prompt, options)

def get_batch(batch_id):
    """
    Get a batch of generated questions by ID.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        batch_id (str): The batch ID

    Returns:
        list: The list of questions in the batch, or None if not found
    """
    return ai_question_generator.get_batch(batch_id)

def verify_api_connection(api_key=None):
    """
    Verify the connection to the OpenAI API.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        api_key (str, optional): The OpenAI API key to verify. If not provided,
            uses the API key already set in the AIQuestionGenerator instance.

    Returns:
        tuple: (success, message) where success is a boolean indicating if the connection was successful
            and message is a string with details about the connection status
    """
    if api_key:
        ai_question_generator.api_key = api_key

    return ai_question_generator.verify_api_connection()

def get_batch_metadata(batch_id):
    """
    Get metadata for a batch of generated questions by ID.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        batch_id (str): The batch ID

    Returns:
        dict: The metadata for the batch, or None if not found or no metadata exists
    """
    return ai_question_generator.get_batch_metadata(batch_id)

def get_all_batches():
    """
    Get a list of all available question batches.

    This is a standalone function that uses the AIQuestionGenerator class.

    Returns:
        list: A list of dictionaries containing batch_id and metadata for each batch,
              sorted by timestamp (newest first)
    """
    batches = []

    # Get the path to the AI generated questions folder
    folder_path = ai_question_generator.temp_storage_path

    # List all JSON files in the folder
    if os.path.exists(folder_path):
        for filename in os.listdir(folder_path):
            if filename.endswith('.json'):
                batch_id = filename[:-5]  # Remove .json extension
                metadata = get_batch_metadata(batch_id)

                # If metadata is None, create a minimal metadata object with file creation time
                if not metadata:
                    file_path = os.path.join(folder_path, filename)
                    metadata = {
                        'timestamp': datetime.fromtimestamp(os.path.getctime(file_path)).isoformat(),
                        'prompt': 'Unknown (File format not recognized)',
                        'question_type': 'unknown',
                        'difficulty': 'unknown',
                        'language': 'unknown',
                        'num_questions': 'unknown'
                    }

                # Always add the batch to the list
                batches.append({
                    'batch_id': batch_id,
                    'metadata': metadata
                })

    # Sort batches by timestamp (newest first)
    batches.sort(key=lambda x: x['metadata'].get('timestamp', ''), reverse=True)

    return batches
