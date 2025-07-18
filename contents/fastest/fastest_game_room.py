"""
Fastest Game Room Module for Avirta

This module extends the GameRoom class to implement the "Who is the fastest" game mode,
which allows players to compete to answer questions the fastest.
"""

import random

from contents.game_room.game_room import GameRoom
from contents.game_board_creator import (
    create_board as create_game_board,
    get_available_questions as get_board_available_questions
)
from questionmanagement.question_bank import increment_use_count

class FastestGameRoom(GameRoom):
    """
    A class to represent a "Who is the fastest" game room for Avirta games.

    This class extends the GameRoom class to add functionality specific to the "Who is the fastest" game mode,
    particularly the ability to track which player answers questions the fastest.

    Attributes:
        room_id (str): Unique identifier for the room
        name (str): Name of the game room
        host (str): Username of the room host
        players (list): List of players in the room
        max_players (int): Maximum number of players allowed
        current_game (object): Reference to the current game session
        is_active (bool): Whether the room is currently active
        categories (list): List of selected categories for the game
        board (dict): Game board with questions organized by category and point value
        answered_questions (set): Set of question IDs that have been answered
        point_values (list): List of point values to use for questions
        current_question (dict): The currently active question
        timer_active (bool): Whether the timer is currently active
        question_revealed (bool): Whether the current question has been revealed
        answer_revealed (bool): Whether the answer to the current question has been revealed
    """

    def __init__(self, room_id, name, host, categories=None, max_players=10, point_values=None, question_types=None):
        """
        Initialize a new Fastest game room.

        Args:
            room_id (str): Unique identifier for the room
            name (str): Name of the game room
            host (str): Username of the room host
            categories (list, optional): List of selected categories for the game
            max_players (int, optional): Maximum number of players allowed
            point_values (list, optional): List of point values to use for questions
            question_types (list, optional): List of question types to include (e.g., ["multiple_choice", "true_false"]).
                                           If None, includes all question types. Defaults to None.
        """
        super().__init__(room_id, name, host, categories, max_players)
        # Use provided point values or default to standard values
        self.point_values = point_values if point_values else [500, 400, 300, 200, 100]
        # Store question types
        self.question_types = question_types

        # Initialize additional attributes for the fastest game mode
        self.current_question = None
        self.timer_active = False
        self.question_revealed = False
        self.answer_revealed = False
        self.current_question_number = 0
        self.total_questions = 0
        self.player_scores = {player: 0 for player in self.players}

    def create_board(self, question_uploader, questions_per_category=10):
        """
        Create a game board with the exact number of questions per category.
        This implementation prioritizes getting the full number of questions
        that match the selected point values and question types.
        Implements sophisticated question selection algorithm as per issue requirements.

        Returns:
            tuple: (success, enough_questions, error_details) where:
                - success (bool): True if the board was created successfully, False otherwise
                - enough_questions (bool): True if enough questions were found that match the criteria
                - error_details (dict): Detailed information about lacking categories and criteria
        """
        # Use the imported create_game_board function with the point_values and question_types parameters
        self.board, self.answered_questions, enough_questions, error_details = create_game_board(
            self.categories, 
            question_uploader, 
            questions_per_category, 
            self.point_values,
            self.question_types
        )

        # Calculate total number of questions
        self.total_questions = sum(len(questions) for category in self.board.values() for questions in category.values())

        return bool(self.board), enough_questions, error_details

    def add_player(self, player_name):
        """
        Add a player to the game room and initialize their score to 0.
        This method overrides the parent class method to ensure that new players
        have their scores initialized in the player_scores dictionary.

        Args:
            player_name (str): Name of the player to add

        Returns:
            bool: True if the player was added successfully, False otherwise
        """
        # Call the parent class method to add the player
        result = super().add_player(player_name)

        # If the player was added successfully, initialize their score to 0
        if result:
            self.player_scores[player_name] = 0

        return result

    def get_available_questions(self):
        """
        Get all questions on the board, marking answered ones.
        This method overrides the parent class method to ensure that only questions
        with point values that match the selected point values are returned.

        Returns:
            dict: Dictionary of questions organized by category and point value,
                 with answered questions marked as {"points": points, "answered": True}
        """
        # Use the imported get_board_available_questions function with use_custom_points=True
        return get_board_available_questions(
            self.board, 
            self.answered_questions, 
            self.current_player, 
            self.player_tools,
            use_custom_points=True
        )

    def get_next_question(self):
        """
        Get the next unanswered question from the board, prioritizing least used questions.

        Returns:
            dict: A question with the lowest use_count or None if all questions have been answered
        """
        # Check if all questions have been answered
        if len(self.answered_questions) >= self.total_questions:
            return None

        # Collect all unanswered questions
        unanswered_questions = []
        for category_id, points_dict in self.board.items():
            for points, questions_list in points_dict.items():
                for question in questions_list:
                    if question['id'] not in self.answered_questions:
                        # Add category_id and points to the question for later use
                        question_with_metadata = question.copy()
                        question_with_metadata['category_id'] = category_id
                        question_with_metadata['points'] = points
                        unanswered_questions.append(question_with_metadata)

        # If there are no unanswered questions, return None
        if not unanswered_questions:
            return None

        # Sort questions by use_count (prioritize least used questions)
        sorted_questions = sorted(unanswered_questions, key=lambda q: q.get("use_count", 0))

        # Get all questions with the minimum use_count
        min_use_count = sorted_questions[0].get("use_count", 0)
        least_used_questions = [q for q in sorted_questions if q.get("use_count", 0) == min_use_count]

        # Randomly select a question from the least used questions
        selected_question = random.choice(least_used_questions)

        # Mark question as answered
        self.answered_questions.add(selected_question['id'])

        # Increment the use_count for this question
        increment_use_count(selected_question['id'])

        # Update current question number
        self.current_question_number += 1

        # Set as current question
        self.current_question = selected_question

        # Reset question state
        self.question_revealed = False
        self.answer_revealed = False
        self.timer_active = False

        return self.current_question

    def reveal_question(self):
        """
        Reveal the current question and start the timer.

        Returns:
            bool: True if the question was revealed, False otherwise
        """
        if not self.current_question or self.question_revealed:
            return False

        self.question_revealed = True
        self.timer_active = True
        return True

    def reveal_answer(self):
        """
        Reveal the answer to the current question and stop the timer.

        Returns:
            bool: True if the answer was revealed, False otherwise
        """
        if not self.current_question or not self.question_revealed or self.answer_revealed:
            return False

        self.answer_revealed = True
        self.timer_active = False
        return True

    def award_points_to_player(self, player_name):
        """
        Award points to the player who answered the question correctly.

        Args:
            player_name (str): Name of the player who answered correctly

        Returns:
            bool: True if points were awarded, False otherwise
        """
        if not self.current_question or not player_name in self.players:
            return False

        # Award points to the player
        points = self.current_question.get('points', 0)
        self.player_scores[player_name] = self.player_scores.get(player_name, 0) + points
        return True

    def get_leaderboard(self):
        """
        Get the current leaderboard sorted by score in descending order.
        Ensures all players have entries in the leaderboard, even if they haven't
        answered any questions yet.

        Returns:
            list: List of (player_name, score) tuples sorted by score
        """
        # Ensure all players have entries in player_scores
        for player in self.players:
            if player not in self.player_scores:
                self.player_scores[player] = 0

        return sorted(self.player_scores.items(), key=lambda x: x[1], reverse=True)

    def get_game_stats(self):
        """
        Get statistics about the current game.

        Returns:
            dict: Dictionary containing game statistics
        """
        return {
            'current_question_number': self.current_question_number,
            'total_questions': self.total_questions,
            'question_revealed': self.question_revealed,
            'answer_revealed': self.answer_revealed,
            'timer_active': self.timer_active,
            'current_question': self.current_question
        }
