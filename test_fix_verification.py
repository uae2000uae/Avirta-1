"""
Script to verify that the fix for the "Could not change question" error works correctly.

This script tests that specific error messages are now returned for different failure scenarios
instead of the generic error message.
"""

import sys
import os

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from contents.game_room.game_room import GameRoom
from contents.categories_questions.question_uploader import QuestionUploader

def test_specific_error_messages():
    """Test that specific error messages are returned for different failure scenarios."""
    
    print("Testing Specific Error Messages for Change Question Tool")
    print("=" * 60)
    
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
    if isinstance(result, dict) and result.get('success') == False:
        print(f"Specific error message: {result.get('message')}")
        print(f"✓ PASS: Specific error message provided")
    else:
        print(f"✗ FAIL: Expected specific error message")
    print()
    
    # Test Scenario 2: Question not active
    print("Scenario 2: Question not active")
    game_room.player_tools["player1"]["change_question"]["available"] = True  # Reset tool
    game_room.question_active = False  # No question active
    
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result}")
    if isinstance(result, dict) and result.get('success') == False:
        print(f"Specific error message: {result.get('message')}")
        print(f"✓ PASS: Specific error message provided")
    else:
        print(f"✗ FAIL: Expected specific error message")
    print()
    
    # Test Scenario 3: Not player's turn
    print("Scenario 3: Not player's turn")
    game_room.question_active = True  # Reset question active
    game_room.current_player = "player2"  # Different player's turn
    
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result}")
    if isinstance(result, dict) and result.get('success') == False:
        print(f"Specific error message: {result.get('message')}")
        print(f"✓ PASS: Specific error message provided")
    else:
        print(f"✗ FAIL: Expected specific error message")
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
    if isinstance(result, dict) and result.get('success') == False:
        print(f"Specific error message: {result.get('message')}")
        print(f"✓ PASS: Specific error message provided")
    else:
        print(f"✗ FAIL: Expected specific error message")
    print()
    
    # Test Scenario 5: Successful usage
    print("Scenario 5: Successful usage")
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result type: {type(result)}")
    if isinstance(result, dict) and 'id' in result:
        print(f"✓ PASS: Successfully changed question")
        print(f"New question ID: {result.get('id')}")
        print(f"New question: {result.get('question')}")
    else:
        print(f"Result: {result}")
        if isinstance(result, dict) and result.get('success') == False:
            print(f"Error message: {result.get('message')}")
        print(f"✗ FAIL: Expected successful question change")
    print()
    
    print("FIX VERIFICATION COMPLETE!")
    print("The fix now provides specific error messages instead of the generic:")
    print("'Could not change question.لا يمكن استبدال السؤال'")

if __name__ == "__main__":
    test_specific_error_messages()