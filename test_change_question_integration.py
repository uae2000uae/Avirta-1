"""
Integration test script for the Change Question tool.

This script tests the complete integration of the Change Question tool
from the web interface through to the backend logic.
"""

import sys
import os

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from contents.game_room.game_room import GameRoom
from contents.categories_questions.question_uploader import QuestionUploader
from contents.game_tools.gametools import GameTools

def test_change_question_integration():
    """Test the complete integration of the Change Question tool."""
    
    print("Testing Change Question Tool Integration")
    print("=" * 50)
    
    # Create a mock question uploader with test data
    class MockQuestionUploader:
        def get_questions_by_category(self, category_id):
            if category_id == "science":
                return [
                    {"id": "Q0000001", "question": "What is H2O?", "points": 300, "use_count": 0, "category_id": "science"},
                    {"id": "Q0000002", "question": "What is CO2?", "points": 300, "use_count": 1, "category_id": "science"},
                    {"id": "Q0000003", "question": "What is NaCl?", "points": 300, "use_count": 0, "category_id": "science"},
                    {"id": "Q0000004", "question": "What is O2?", "points": 300, "use_count": 2, "category_id": "science"},
                    {"id": "Q0000005", "question": "What is H2SO4?", "points": 400, "use_count": 0, "category_id": "science"}
                ]
            return []
    
    question_uploader = MockQuestionUploader()
    
    # Create a game room
    game_room = GameRoom("test_room", "Test Game", "host_player", categories=["science"])
    game_room.add_player("host_player")
    game_room.add_player("player1")
    game_room.add_player("player2")
    
    # Initialize the board with some questions
    game_room.board = {
        "science": {
            300: [
                {"id": "Q0000001", "question": "What is H2O?", "points": 300, "use_count": 0}
            ]
        }
    }
    
    # Set up game state
    game_room.current_player = "player1"
    game_room.question_active = True
    game_room.answered_questions = set()
    
    # Test 1: Player1 uses change question tool (should work)
    print("Test 1: Player1 uses change question tool")
    result = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result is not None}")
    if result:
        print(f"New question ID: {result.get('id')}")
        print(f"New question: {result.get('question')}")
        print(f"Points: {result.get('points')}")
    print(f"Tool still available: {game_room.has_tool_available('player1', 'change_question')}")
    print()
    
    # Test 2: Player1 tries to use change question again (should fail)
    print("Test 2: Player1 tries to use change question again")
    result2 = game_room.use_change_question("player1", "science", 300, question_uploader)
    print(f"Result: {result2 is None}")
    print(f"Expected: True (tool should be unavailable)")
    print()
    
    # Test 3: Player2 tries to use change question when it's not their turn (should fail)
    print("Test 3: Player2 tries to use change question when it's not their turn")
    result3 = game_room.use_change_question("player2", "science", 300, question_uploader)
    print(f"Result: {result3 is None}")
    print(f"Expected: True (not player's turn)")
    print()
    
    # Test 4: Host acts on behalf of current player
    print("Test 4: Host acts on behalf of current player")
    game_room.current_player = "player2"  # Change turn to player2
    result4 = game_room.use_change_question("host_player", "science", 300, question_uploader, acting_player="player2")
    print(f"Result: {result4 is not None}")
    if result4:
        print(f"New question ID: {result4.get('id')}")
        print(f"Tool still available for player2: {game_room.has_tool_available('player2', 'change_question')}")
    print()
    
    # Test 5: Test when question is not active
    print("Test 5: Test when question is not active")
    game_room.question_active = False
    result5 = game_room.use_change_question("host_player", "science", 300, question_uploader)
    print(f"Result: {result5 is None}")
    print(f"Expected: True (question not active)")
    print()
    
    print("Integration tests completed!")

if __name__ == "__main__":
    test_change_question_integration()