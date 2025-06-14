"""
Game Room Module for Avirta

This module handles the creation and management of game rooms where players can join and participate in Avirta games.
"""

from contents.game_tools import GameTools

class GameRoom:
    """
    A class to represent a game room for Avirta games.

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
    """

    def __init__(self, room_id, name, host, categories=None, max_players=10):
        """ Initialize a new game room. """
        self.room_id = room_id
        self.name = name
        self.host = host
        self.players = [host]  # Host is automatically a player
        self.max_players = max_players
        self.current_game = None
        self.is_active = True
        self.current_player = host  # Track whose turn it is, starting with the host
        self.question_active = False  # Track whether a question is currently active

        # Initialize categories (using the provided categories list)
        self.categories = categories if categories else []

        # Initialize game board and answered questions
        self.board = {}
        self.answered_questions = set()

        # Initialize player tools with default values
        self.player_tools = {host: self._initialize_tools()}

    @staticmethod
    def _initialize_tools():
        """ Initializes default player tools """
        return GameTools.initialize_tools()

    def add_player(self, player_name):
        """ Add a player to the game room. """
        if len(self.players) >= self.max_players or player_name in self.players:
            return False

        self.players.append(player_name)
        self.player_tools[player_name] = self._initialize_tools()
        return True

    def remove_player(self, player_name):
        """ Remove a player from the game room. """
        if player_name not in self.players:
            return False

        self.players.remove(player_name)

        # If the host leaves, reassign or close the room
        if player_name == self.host:
            self.host = self.players[0] if self.players else None
            self.is_active = bool(self.players)  # Room stays active if players remain

        return True

    def start_game(self, game_session):
        """ Start a new game in this room. """
        if not self.is_active or len(self.players) < 2:
            return False

        self.current_game = game_session

        # Reset tools for all players
        for player in self.players:
            self.player_tools[player] = self._initialize_tools()

        return True

    def end_game(self):
        """ End the current game in this room. """
        if not self.current_game:
            return False

        self.current_game = None
        self.board.clear()
        self.answered_questions.clear()
        return True

    def create_board(self, question_uploader):
        """
        Create a game board with 5 questions per category, prioritizing unused questions,
        but allowing flexible point values when needed.
        """
        if not self.categories:
            return False

        point_values = [500, 400, 300, 200, 100]  # Default set of point values
        self.board = {}

        for category_id in self.categories:
            category_questions = question_uploader.get_questions_by_category(category_id)
            if not category_questions:
                continue

            self.board[category_id] = {}
            used_question_ids = set()

        # Organize questions by point values
            questions_by_points = {}
            for question in category_questions:
                points_value = question.get("points")
                if not isinstance(points_value, int):
                    continue  # Ignore invalid point values
                questions_by_points.setdefault(points_value, []).append(question)

        # Assign questions, allowing flexibility when needed
            for points in point_values:
                matching_questions = questions_by_points.get(points, [])

            # Filter out already used questions
                available_matching_questions = [q for q in matching_questions if
                                            q.get("id", "") not in used_question_ids]

                if not available_matching_questions:
                    # Expand search to *any* available question, rather than forcing duplication
                    all_available_questions = [
                        q for qs in questions_by_points.values()
                        for q in qs
                        if q.get("id", "") not in used_question_ids
                    ]

                    if not all_available_questions:
                        continue  # No questions available at all

                    # Pick the least-used question from any available point value
                    question = min(all_available_questions, key=lambda q: q.get("use_count", 0))
                else:
                    # Select the least-used question of the exact matching point value
                    question = min(available_matching_questions, key=lambda q: q.get("use_count", 0))

                question_id = question.get("id", "")
                used_question_ids.add(question_id)

            # Assign question to board, maintaining point values but allowing flexibility
                self.board[category_id][points] = question.copy()

        return bool(self.board)

    def select_question(self, category_id, points, player_name, acting_player=None):
        """
        Select a question from the board based on category and point value.

        Args:
            category_id (str): ID of the category
            points (int): Point value of the question
            player_name (str): Name of the player selecting the question
            acting_player (str, optional): Name of the player on whose behalf the action is being taken.
                                          If provided and player_name is the host, allows the host to act for another player.

        Returns:
            dict: The selected question or None if not available
        """
        # Check if player is in the game
        if player_name not in self.players:
            return None

        # Determine the effective player (who will be credited with the action)
        effective_player = player_name

        # If acting_player is provided and player_name is the host, use acting_player
        if acting_player and self.is_host(player_name) and acting_player in self.players:
            effective_player = acting_player

        # Check if it's the effective player's turn
        if effective_player != self.current_player:
            # Allow host override
            if not (self.is_host(player_name) and acting_player == self.current_player):
                return None

        # Check if category exists in board
        if category_id not in self.board:
            return None

        # Check if point value exists for category
        if points not in self.board[category_id]:
            return None

        # Get the question
        question = self.board[category_id][points].copy()

        # Check if question has already been answered
        if question['id'] in self.answered_questions:
            return None

        # Mark question as answered
        self.answered_questions.add(question['id'])

        # Apply double points if active for the effective player
        if self.player_tools.get(effective_player, {}).get("double_points", {}).get("active", False):
            # Ensure points is an integer before multiplying
            if isinstance(question['points'], str):
                try:
                    question['points'] = int(question['points'])
                except ValueError:
                    question['points'] = 300

            question['points'] = question['points'] * 2
            question['doubled'] = True
            # Deactivate double points for this player after use
            self.player_tools[effective_player]["double_points"]["active"] = False

        return question

    def get_available_questions(self):
        """
        Get all questions on the board, marking answered ones.
        Questions are sorted from most difficult to least difficult within each category.

        Returns:
            dict: Dictionary of questions organized by category and point value,
                 with answered questions marked as {"points": points, "answered": True}
        """
        available = {}

        for category_id, questions in self.board.items():
            available[category_id] = {}

            # Create a list of (points_key, question) tuples
            question_items = []
            for points_key, question in questions.items():
                # Use the actual points value from the question, not the position on the board
                actual_points = question.get('points', points_key)

                # Ensure actual_points is an integer
                if isinstance(actual_points, str):
                    try:
                        actual_points = int(actual_points)
                    except ValueError:
                        actual_points = points_key

                # Check if double points is active for the current player
                doubled = False
                if self.player_tools.get(self.current_player, {}).get("double_points", {}).get("active", False) and question['id'] not in self.answered_questions:
                    actual_points = actual_points * 2
                    doubled = True

                if question['id'] not in self.answered_questions:
                    # Store the actual point value from the question
                    question_items.append((points_key, {"points": actual_points, "answered": False, "doubled": doubled}))
                else:
                    # Include answered questions but mark them as answered
                    question_items.append((points_key, {"points": actual_points, "answered": True, "doubled": False}))

            # Sort by actual points in descending order (most difficult to least difficult)
            question_items.sort(key=lambda item: item[1]["points"], reverse=True)

            # Add sorted items to the available dictionary
            for points_key, question_info in question_items:
                available[category_id][points_key] = question_info

        return available

    def is_board_completed(self):
        """
        Check if all questions on the board have been answered.

        Returns:
            bool: True if all questions have been answered, False otherwise
        """
        for category_id, questions in self.board.items():
            for points, question in questions.items():
                if question['id'] not in self.answered_questions:
                    return False

        return True

    def use_double_points(self, player_name, acting_player=None):
        """
        Activate the "Double the Points" tool for a player.
        This tool doubles the points for the next question the player selects.
        Must be used before the question is revealed.
        Can only be used when the host is in the game room page, not in the question page.

        Args:
            player_name (str): Name of the player using the tool
            acting_player (str, optional): Name of the player on whose behalf the action is being taken.
                                           If provided and player_name is the host, allows the host to act for another player.

        Returns:
            bool: True if the tool was used successfully, False otherwise
        """
        # Validate player existence
        if player_name not in self.players:
            return False

        # Determine effective player (host can act for another player)
        effective_player = acting_player if acting_player and self.is_host(
            player_name) and acting_player in self.players else player_name

        # Use the GameTools class to handle the tool usage
        return GameTools.use_double_points(self.player_tools, effective_player, self.question_active)

    def use_change_question(self, player_name, category_id, current_points, question_uploader=None, acting_player=None):
        """
        Activate the "Change the Question" tool for a player.
        This tool allows the player to swap the current question for another one
        from the same category with the same point value.
        Must be used during the answering timer.
        Can only be used when the host is in the question page and it's the player's turn.

        Args:
            player_name (str): Name of the player using the tool
            category_id (str): ID of the category
            current_points (int): Point value of the current question
            question_uploader (QuestionUploader, optional): Instance of QuestionUploader to get questions.
                                                          If not provided, will attempt to get from Flask app context.
            acting_player (str, optional): Name of the player on whose behalf the action is being taken.
                                          If provided and player_name is the host, allows the host to act for another player.

        Returns:
            dict: The new question or None if the tool couldn't be used
        """
        # Check if player is in the game
        if player_name not in self.players:
            return None

        # Determine the effective player (who will be credited with the action)
        effective_player = player_name

        # If acting_player is provided and player_name is the host, use acting_player
        if acting_player and self.is_host(player_name) and acting_player in self.players:
            effective_player = acting_player

        # Use the GameTools class to handle the tool usage
        return GameTools.use_change_question(
            self.player_tools, 
            effective_player, 
            self.current_player, 
            self.question_active, 
            self.board, 
            self.answered_questions, 
            category_id, 
            current_points, 
            question_uploader
        )


    def has_tool_available(self, player_name, tool_name):
        """
        Check if a player has a specific tool available.

        Args:
            player_name (str): Name of the player
            tool_name (str): Name of the tool to check ("double_points" or "change_question")

        Returns:
            bool: True if the player has the tool available, False otherwise
        """
        return GameTools.has_tool_available(self.player_tools, player_name, tool_name)

    def _is_id_on_board(self, question_id):
        """
        Check if a question ID exists in any question on the board.

        Args:
            question_id (str): ID of the question to check

        Returns:
            bool: True if the ID exists on the board, False otherwise
        """
        for category_id, questions in self.board.items():
            for points, question in questions.items():
                if question.get('id') == question_id:
                    return True
        return False

    def get_player_tools(self, player_name):
        """
        Get all tools available for a player.

        Args:
            player_name (str): Name of the player

        Returns:
            dict: Dictionary of tool names and their availability status
        """
        return GameTools.get_player_tools(self.player_tools, player_name)

    def is_host(self, player_name):
        """
        Check if a player is the host of this game room.

        Args:
            player_name (str): Name of the player to check

        Returns:
            bool: True if the player is the host, False otherwise
        """
        return player_name == self.host

    def advance_turn(self):
        """
        Advance to the next player's turn.

        Returns:
            str: The name of the player whose turn it is now
        """
        if not self.players:
            return None

        # Find the current player's index
        try:
            current_index = self.players.index(self.current_player)
        except ValueError:
            # If current player is not in the list, start with the first player
            self.current_player = self.players[0]
            return self.current_player

        # Move to the next player
        next_index = (current_index + 1) % len(self.players)
        self.current_player = self.players[next_index]

        return self.current_player
