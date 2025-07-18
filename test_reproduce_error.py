"""
Script to reproduce the "Could not change question" error.

This script will test various scenarios that could cause the change question tool to fail
and demonstrate the generic error message issue.
"""

import sys
import os

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from contents.game_room.game_room import GameRoom
from contents.categories_questions.question_uploader import QuestionUploader

def test_error_scenarios():
    """Test various scenarios that cause the change question tool to fail."""
    
    print("Testing Change Question Error Scenarios")
    print("=" * 50)
    
    # Create a mock question uploader
    class MockQuestionUploader:
        def get_questions_by_category(self, category_id):
            if category_id == "science":
                return [
                    {"id": "Q0000001", "question": "What is H2O?", "points": 300, "use_count": 0, "category_id": "science"},
                    {"id": "Q0000002", "question": "What is CO2?", "points": 300, "use_count": 1, "category_id": "science"}
                ]
            return []
    
    question_uploader = MockQuestionUploader()
    
    # Create a game room
    game_room = GameRoom("test_room", "Test Game", "host_player", categories=["science"])
    game_room.add_player("host_player")
    game_room.add_player("player1")
    game_room.add_player("player2")
    
    # Initialize the board
    game_room.board = {
        "science": {
            300: [
                {"id": "Q0000001", "question": "What is H2O?", "points": 300, "use_count": 0}
            ]
        }
    }
    
    # Test Scenario 1: Tool already used
    print("Scenario 1: Tool already used")
    game_room.current_player = "player1"
    game_room.question_active = True
    game_room.player_tools["player1"]["change_question"]["available"] = False  # Tool already used
    
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result}")
    print(f"Expected: None (tool not available)")
    print(f"This would show: 'Could not change question.لا يمكن استبدال السؤال'")
    print()
    
    # Test Scenario 2: Question not active
    print("Scenario 2: Question not active")
    game_room.player_tools["player1"]["change_question"]["available"] = True  # Reset tool
    game_room.question_active = False  # No question active
    
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result}")
    print(f"Expected: None (question not active)")
    print(f"This would show: 'Could not change question.لا يمكن استبدال السؤال'")
    print()
    
    # Test Scenario 3: Not player's turn
    print("Scenario 3: Not player's turn")
    game_room.question_active = True  # Reset question active
    game_room.current_player = "player2"  # Different player's turn
    
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result}")
    print(f"Expected: None (not player's turn)")
    print(f"This would show: 'Could not change question.لا يمكن استبدال السؤال'")
    print()
    
    # Test Scenario 4: No available questions
    print("Scenario 4: No available questions")
    game_room.current_player = "player1"  # Reset to correct player
    
    # Mock question uploader with no questions
    class EmptyQuestionUploader:
        def get_questions_by_category(self, category_id):
            return []
    
    empty_uploader = EmptyQuestionUploader()
    result = game_room.use_change_question("player1", "science", 300, empty_uploader)
    print(f"Result: {result}")
    print(f"Expected: None (no available questions)")
    print(f"This would show: 'Could not change question.لا يمكن استبدال السؤال'")
    print()
    
    print("ISSUE IDENTIFIED:")
    print("All different failure scenarios show the same generic error message:")
    print("'Could not change question.لا يمكن استبدال السؤال'")
    print("This doesn't help users understand why the tool failed.")

if __name__ == "__main__":
    test_error_scenarios()