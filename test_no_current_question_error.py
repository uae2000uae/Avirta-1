"""
Test script to reproduce the "No current question found to change" error.

This script tests the specific scenario where all questions in a category/point 
combination have been answered, causing the change question tool to fail with
the "No current question found to change" error message.
"""

import sys
import os

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from contents.game_tools.gametools import GameTools

def test_no_current_question_scenario():
    """Test the scenario where no current question is found to change."""
    
    print("Testing 'No current question found to change' Error Scenario")
    print("=" * 60)
    
    # Mock data for testing
    player_tools = {
        "player1": {
            "change_question": {"has": True, "available": True, "active": False}
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
    
    # All questions in this category/point combination have been answered
    answered_questions = {"Q0000001", "Q0000002"}
    
    # Mock question uploader
    class MockQuestionUploader:
        def get_questions_by_category(self, category_id):
            if category_id == "science":
                return [
                    {"id": "Q0000003", "question": "What is NaCl?", "points": 300, "use_count": 0},
                    {"id": "Q0000004", "question": "What is O2?", "points": 300, "use_count": 2}
                ]
            return []
    
    question_uploader = MockQuestionUploader()
    
    print("Scenario: All questions in the current category/point combination have been answered")
    print(f"Board questions: {[q['id'] for q in board['science'][300]]}")
    print(f"Answered questions: {answered_questions}")
    print()
    
    result = GameTools.use_change_question(
        player_tools, "player1", "player1", True, board, 
        answered_questions, "science", 300, question_uploader
    )
    
    print(f"Result: {result}")
    
    if isinstance(result, dict) and result.get('success') == False:
        print(f"Error type: {result.get('error')}")
        print(f"Error message: {result.get('message')}")
        
        if result.get('error') == 'no_current_question':
            print("✓ PASS: Correctly identified 'no_current_question' error")
            print("✓ PASS: Specific error message provided")
        else:
            print("✗ FAIL: Expected 'no_current_question' error")
    else:
        print("✗ FAIL: Expected error response")
    
    print()
    print("ANALYSIS:")
    print("This error occurs when:")
    print("1. A question is active and it's the player's turn")
    print("2. The player has the change question tool available")
    print("3. But all questions in the current category/point combination have been answered")
    print("4. The system cannot find an 'unanswered' question to change to")
    print()
    print("This is a legitimate error condition that should be handled gracefully.")

if __name__ == "__main__":
    test_no_current_question_scenario()