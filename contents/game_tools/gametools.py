"""
Game Tools Module for Avirta

This module handles the game tools functionality for Avirta games, including:
- Double Points: Doubles the points for the next question
- Change Question: Changes the current question to a new one

These tools can be used by players during the game to enhance their gameplay experience.
"""

class GameTools:
    """
    A class to manage game tools for Avirta games.

    This class provides methods for initializing, using, and checking the availability of game tools.
    It is designed to be used by the GameRoom class to handle game tools functionality.
    """

    @staticmethod
    def initialize_tools():
        """
        Initialize default player tools.

        Returns:
            dict: A dictionary containing the default tools and their states
        """
        return {
            "double_points": {"has": True, "available": True, "active": False},
            "change_question": {"has": True, "available": True, "active": False}
        }

    @staticmethod
    def use_double_points(player_tools, effective_player, question_active):
        """
        Activate the "Double the Points" tool for a player.
        This tool doubles the points for the next question the player selects.
        Can be used at any time, but only once per player.

        Args:
            player_tools (dict): Dictionary of player tools
            effective_player (str): Name of the player using the tool
            question_active (bool): Whether a question is currently active (not used anymore)

        Returns:
            bool: True if the tool was used successfully, False otherwise
        """
        # Retrieve player's tool info efficiently
        tool_data = player_tools.setdefault(effective_player, {}).get("double_points", {})

        # Ensure tool availability (only check if it's been used before)
        if not tool_data.get("available", False):
            return False

        # Activate the tool and mark it as used
        tool_data["active"] = True
        tool_data["available"] = False

        return True

    @staticmethod
    def use_change_question(player_tools, effective_player, current_player, question_active, board, 
                           answered_questions, category_id, current_points, question_uploader=None):
        """
        Activate the "Change the Question" tool for a player.
        This tool allows the player to swap the current question for another one
        from the same category with the same point value.
        Can be used at any time, but only once per player.

        Args:
            player_tools (dict): Dictionary of player tools
            effective_player (str): Name of the player using the tool
            current_player (str): Name of the player whose turn it is (not used anymore)
            question_active (bool): Whether a question is currently active (not used anymore)
            board (dict): Game board with questions organized by category and point value
            answered_questions (set): Set of question IDs that have been answered
            category_id (str): ID of the category
            current_points (int): Point value of the current question
            question_uploader (QuestionUploader, optional): Instance of QuestionUploader to get questions.

        Returns:
            dict: The new question or None if the tool couldn't be used
        """
        # Check if effective player has the tool available (only check if it's been used before)
        if not player_tools.get(effective_player, {}).get("change_question", {}).get("available", False):
            return None

        # Check if category exists in board
        if category_id not in board:
            return None

        # Check if point value exists for category
        if current_points not in board[category_id]:
            return None

        # Get the current question
        current_question = board[category_id][current_points]

        # Mark the current question as answered
        answered_questions.add(current_question['id'])

        # If question_uploader is not provided, try to get it from the app context
        if not question_uploader:
            try:
                from flask import current_app
                question_uploader = current_app.config.get('question_uploader')
            except (ImportError, RuntimeError):
                # Flask app context not available or Flask not installed
                pass

        if not question_uploader:
            # No question_uploader available
            return None

        # Get all questions for this category
        category_questions = question_uploader.get_questions_by_category(category_id)

        # Skip if no questions available
        if not category_questions:
            return None

        # Get all question IDs currently on the board
        board_question_ids = set()
        for cat_id, questions in board.items():
            for points, question in questions.items():
                board_question_ids.add(question.get('id', ''))

        # Filter out questions that are already on the board or have been answered
        existing_question_ids = {q.get('id') for cat in board.values() for q in cat.values()}

        available_questions = [q for q in category_questions
                               if q.get('id') not in existing_question_ids
                               and q.get('id') not in answered_questions]

        if not available_questions:
            # If no available questions, return None
            return None

        # Get the point value of the current question
        current_points_value = current_question.get('points', current_points)
        if isinstance(current_points_value, str):
            try:
                current_points_value = int(current_points_value)
            except ValueError:
                current_points_value = current_points

        # First try to find questions with exactly matching points
        matching_questions = [q for q in available_questions 
                             if q.get('points') == current_points_value]

        # If no exact matches, look for questions with similar points
        if not matching_questions:
            # Define a range of acceptable point values (e.g., within 100 points)
            point_range = 100
            matching_questions = [q for q in available_questions 
                                 if abs(int(q.get('points', 0)) - current_points_value) <= point_range]

        # If still no matches, use any available question from the category
        if not matching_questions:
            matching_questions = available_questions

        # If we have matching questions, sort by usage count (least used first)
        if matching_questions:
            # Track question usage count if not already present
            if not hasattr(question_uploader, 'question_usage_count'):
                question_uploader.question_usage_count = {}

            # Sort questions by usage count (least used first)
            matching_questions.sort(key=lambda q: question_uploader.question_usage_count.get(q.get('id', ''), 0))

            # Select the next least used question if available, otherwise use the least used
            if len(matching_questions) > 1:
                new_question = matching_questions[1]  # Next least used
            else:
                new_question = matching_questions[0]  # Least used

            # Increment the usage count for this question
            question_id = new_question.get('id', '')
            if question_id:
                question_uploader.question_usage_count[question_id] = question_uploader.question_usage_count.get(question_id, 0) + 1

            # Update the board with the new question
            board[category_id][current_points].update({
                key: value for key, value in new_question.items() if key != "id"
            })
            # Mark the tool as used (disable but don't remove)
            player_tools[effective_player]["change_question"]["available"] = False

            return new_question

        return None

    @staticmethod
    def has_tool_available(player_tools, player_name, tool_name):
        """
        Check if a player has a specific tool available.

        Args:
            player_tools (dict): Dictionary of player tools
            player_name (str): Name of the player
            tool_name (str): Name of the tool to check ("double_points" or "change_question")

        Returns:
            bool: True if the player has the tool available, False otherwise
        """
        return player_tools.get(player_name, {}).get(tool_name, {}).get("available", False)

    @staticmethod
    def get_player_tools(player_tools, player_name):
        """
        Get all tools available for a player.

        Args:
            player_tools (dict): Dictionary of player tools
            player_name (str): Name of the player

        Returns:
            dict: Dictionary of tool names and their availability status
        """
        tools = player_tools.get(player_name, {})
        # Return a simplified version for backward compatibility
        simplified_tools = {}
        for tool_name, status in tools.items():
            simplified_tools[tool_name] = status.get("available", False)
        return simplified_tools
