"""
Question Manager Module for Avirta

This module handles the management of questions during a trivia game session,
including selecting questions, validating answers, and tracking scores.
"""

import random
from datetime import datetime

class QuestionManager:
    """
    A class to manage questions during an Avirta game session.

    Attributes:
        questions (list): List of question objects for the current game
        current_question_index (int): Index of the current question
        scores (dict): Dictionary mapping player names to their scores
        question_history (list): List of questions that have been asked
        time_limit (int): Time limit in seconds for answering each question
    """

    def __init__(self, questions=None, time_limit=30):
        """
        Initialize a new question manager.

        Args:
            questions (list, optional): List of question objects. Defaults to None.
            time_limit (int, optional): Time limit in seconds for each question. Defaults to 30.
        """
        self.questions = questions or []
        self.current_question_index = -1
        self.scores = {}
        self.question_history = []
        self.time_limit = time_limit

    def add_questions(self, questions):
        """
        Add questions to the question pool.

        Args:
            questions (list): List of question objects to add
        """
        self.questions.extend(questions)

    def set_questions(self, questions):
        """
        Set the question pool, replacing any existing questions.

        Args:
            questions (list): List of question objects
        """
        self.questions = questions
        self.current_question_index = -1

    def shuffle_questions(self):
        """
        Randomly shuffle the order of questions.
        """
        random.shuffle(self.questions)

    def get_next_question(self):
        """
        Get the next question in the sequence.

        Returns:
            dict: The next question object, or None if no more questions
        """
        if not self.questions or self.current_question_index >= len(self.questions) - 1:
            return None

        self.current_question_index += 1
        question = self.questions[self.current_question_index]
        self.question_history.append({
            'question': question,
            'timestamp': datetime.now()
        })

        return question

    def check_answer(self, player_name, answer):
        """
        Check if a player's answer is correct and update their score.

        Args:
            player_name (str): Name of the player submitting the answer
            answer (str): The player's answer

        Returns:
            bool: True if the answer is correct, False otherwise
        """
        if self.current_question_index < 0 or self.current_question_index >= len(self.questions):
            return False

        current_question = self.questions[self.current_question_index]
        is_correct = self._validate_answer(current_question, answer)

        # Initialize player score if not exists
        if player_name not in self.scores:
            self.scores[player_name] = 0

        # Update score if answer is correct
        if is_correct:
            # Ensure points is an integer
            points = current_question.get('points', 10)
            if isinstance(points, str):
                try:
                    points = int(points)
                except ValueError:
                    points = 10
            self.scores[player_name] += points

        return is_correct

    def _validate_answer(self, question, answer):
        """
        Validate if an answer is correct for a given question.

        Args:
            question (dict): The question object
            answer (str): The player's answer

        Returns:
            bool: True if the answer is correct, False otherwise
        """
        # If answer is None (e.g., when time runs out and no selection is made), return False
        if answer is None:
            return False

        correct_answer = question.get('correct_answer', '').lower().strip()
        player_answer = answer.lower().strip()

        # For multiple choice questions
        if question.get('type') == 'multiple_choice':
            return player_answer == correct_answer

        # For true/false questions
        elif question.get('type') == 'true_false':
            # Define English and Arabic versions of true/false
            true_values = ['true', 'صحيح']  # English and Arabic for "true"
            false_values = ['false', 'خطأ']  # English and Arabic for "false"

            # Check if the correct answer is a form of "true"
            if correct_answer in true_values:
                return player_answer in true_values
            # Check if the correct answer is a form of "false"
            elif correct_answer in false_values:
                return player_answer in false_values
            # If it's neither, fall back to exact matching
            else:
                return player_answer == correct_answer

        # For text input questions, allow partial matching
        elif question.get('type') == 'text':
            # Check for exact match first
            if player_answer == correct_answer:
                return True

            # Alternative answers functionality has been removed
            return False

        return False

    def get_player_score(self, player_name):
        """
        Get the current score for a player.

        Args:
            player_name (str): Name of the player

        Returns:
            int: The player's current score
        """
        return self.scores.get(player_name, 0)

    def get_leaderboard(self, all_players=None):
        """
        Get the current leaderboard sorted by score.

        Args:
            all_players (list, optional): List of all player names to include in the leaderboard.
                                         If provided, ensures all players are included even if they have no score.

        Returns:
            list: List of tuples (player_name, score) sorted by score
        """
        # If all_players is provided, ensure all players are in the scores dictionary
        if all_players:
            scores_dict = self.scores.copy()
            for player in all_players:
                if player not in scores_dict:
                    scores_dict[player] = 0
            return sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
        else:
            return sorted(self.scores.items(), key=lambda x: x[1], reverse=True)

    def award_points(self, player_name, points):
        """
        Award points to a player directly (used for moderator evaluation).

        Args:
            player_name (str): Name of the player to award points to
            points (int): Number of points to award

        Returns:
            int: The player's updated score
        """
        # Initialize player score if not exists
        if player_name not in self.scores:
            self.scores[player_name] = 0

        # Ensure points is an integer
        if isinstance(points, str):
            try:
                points = int(points)
            except ValueError:
                points = 0

        # Add points to the player's score
        self.scores[player_name] += points

        return self.scores[player_name]
