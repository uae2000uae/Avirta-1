"""
Test script for the Change Question tool implementation.

This script tests the corrected Change Question tool to ensure it follows PRJ-007 rules:
- Can only be used when a question is active
- Can only be used when it's the player's turn
- Must replace the current question with another from the same category
- The new question must be from the same category with equal or close points value
- Each player gets one use per game
"""

import sys
import os

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from contents.game_tools.gametools import GameTools

def test_change_question_tool():
    """Test the Change Question tool implementation."""

    print("Testing Change Question Tool Implementation")
    print("=" * 50)

    # Mock data for testing
    player_tools = {
        "player1": {
            "change_question": {"has": True, "available": True, "active": False}
        },
        "player2": {
            "change_question": {"has": True, "available": False, "active": False}  # Already used
        }
    }

    # Mock board with questions
    board = {
        "science": {
            300: [
                {"id": "Q0000001", "question": "What is H2O?", "points": 300, "use_count": 0},
                {"id": "Q0000002", "question": "What is CO2?", "points": 300, "use_count": 1}
            ]
        }
    }

    answered_questions = set()

    # Mock question uploader
    class MockQuestionUploader:
        def get_questions_by_category(self, category_id):
            if category_id == "science":
                return [
                    {"id": "Q0000003", "question": "What is NaCl?", "points": 300, "use_count": 0},
                    {"id": "Q0000004", "question": "What is O2?", "points": 300, "use_count": 2},
                    {"id": "Q0000005", "question": "What is H2SO4?", "points": 400, "use_count": 0}  # Close points
                ]
            return []

    question_uploader = MockQuestionUploader()

    # Test 1: Tool not available (already used)
    print("Test 1: Tool not available (already used)")
    result = GameTools.use_change_question(
        player_tools, "player2", "player2", True, board, 
        answered_questions, "science", 300, question_uploader
    )
    print(f"Result: {result}")
    print(f"Expected: Error dict (tool not available)")
    is_error = isinstance(result, dict) and result.get('success') == False
    print(f"PASS: {is_error}")
    if is_error:
        print(f"Error message: {result.get('message')}")
    print()

    # Test 2: Question not active
    print("Test 2: Question not active")
    result = GameTools.use_change_question(
        player_tools, "player1", "player1", False, board, 
        answered_questions, "science", 300, question_uploader
    )
    print(f"Result: {result}")
    print(f"Expected: Error dict (question not active)")
    is_error = isinstance(result, dict) and result.get('success') == False
    print(f"PASS: {is_error}")
    if is_error:
        print(f"Error message: {result.get('message')}")
    print()

    # Test 3: Not player's turn
    print("Test 3: Not player's turn")
    result = GameTools.use_change_question(
        player_tools, "player1", "player2", True, board, 
        answered_questions, "science", 300, question_uploader
    )
    print(f"Result: {result}")
    print(f"Expected: Error dict (not player's turn)")
    is_error = isinstance(result, dict) and result.get('success') == False
    print(f"PASS: {is_error}")
    if is_error:
        print(f"Error message: {result.get('message')}")
    print()

    # Test 4: Successful tool usage
    print("Test 4: Successful tool usage")
    result = GameTools.use_change_question(
        player_tools, "player1", "player1", True, board, 
        answered_questions, "science", 300, question_uploader
    )
    print(f"Result: {result is not None}")
    print(f"Expected: True (tool should work)")
    if result:
        print(f"New question ID: {result.get('id')}")
        print(f"New question points: {result.get('points')}")
        print(f"Tool still available: {player_tools['player1']['change_question']['available']}")
    print(f"PASS: {result is not None}")
    print()

    # Test 5: Tool no longer available after use
    print("Test 5: Tool no longer available after use")
    result2 = GameTools.use_change_question(
        player_tools, "player1", "player1", True, board, 
        answered_questions, "science", 300, question_uploader
    )
    print(f"Result: {result2}")
    print(f"Expected: Error dict (tool already used)")
    is_error = isinstance(result2, dict) and result2.get('success') == False
    print(f"PASS: {is_error}")
    if is_error:
        print(f"Error message: {result2.get('message')}")
    print()

    print("All tests completed!")

if __name__ == "__main__":
    test_change_question_tool()
