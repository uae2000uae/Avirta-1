# Avirta Project Coding Reference

This document serves as a quick reference for the Avirta project structure, key components, and functionality. It complements the information in guidelines.md and is designed to be updated with each request.

## Actual Project Structure

```
Avirta/
├── add_arabic_questions.py     # Script for adding Arabic questions
├── add_new_questions.py        # Script for adding new questions
├── avirta/                     # Core package
│   ├── __init__.py
│   ├── question_bank.py        # Question bank functionality
│   ├── question_import_export.py # Import/export functionality
│   ├── utils.py                # Utility functions
│   └── README.md
├── contents/                   # Game content
│   ├── __init__.py
│   ├── admin_controls/         # Admin functionality
│   │   ├── __init__.py
│   │   └── admin_setup.py
│   ├── bulk_upload/            # Bulk question upload
│   │   ├── __init__.py
│   │   └── bulk_import.py
│   ├── categories_questions/   # Category management
│   │   ├── __init__.py
│   │   ├── category_manager.py
│   │   └── question_uploader.py
│   ├── game_content/           # Game content management
│   │   ├── __init__.py
│   │   └── question_manager.py
│   ├── game_room/              # Game room functionality
│   │   ├── __init__.py
│   │   └── game_room.py
│   ├── main.py                 # Main entry point
│   └── questions/              # Question JSON files
│       └── Q*.json             # Individual question files
├── modify_template.py          # Template modification script
├── pyproject.toml              # Project configuration
├── requirements.txt            # Dependencies
├── setup.py                    # Package setup
└── Avirta/                     # Web application
    ├── app.py                  # Flask application
    ├── index.html              # Main HTML file
    ├── README.md               # Web app documentation
    ├── static/                 # Static assets
    │   ├── css/
    │   │   └── style.css       # Main stylesheet
    │   └── js/
    │       └── script.js       # Main JavaScript
    └── templates/              # HTML templates
        ├── add_question.html
        ├── base.html           # Base template
        ├── bulk_import.html
        ├── create_room.html
        ├── edit_category.html
        ├── game_room.html
        ├── index.html
        ├── join_room.html
        ├── leaderboard.html
        ├── question.html
        ├── question_bank.html
        ├── result.html
        └── view_questions.html
```

## Key Components

### Web Application (Avirta/app.py)

The web application is built with Flask and serves as the user interface for the Avirta game.

#### Main Routes:
- `index()`: Main landing page
- `ping()`: Health check endpoint

#### Game Room Management:
- `create_room()`: Create a new game room
- `join_room()`: Join an existing game room
- `game_room(room_id)`: Display the game room
- `reset_game()`: Reset the current game

#### Game Mechanics:
- `select_question()`: Handle question selection
- `question(room_id)`: Display a question
- `answer_question()`: Process a player's answer
- `evaluate_answer()`: Evaluate if an answer is correct
- `result(room_id)`: Show game results
- `leaderboard(room_id)`: Display the leaderboard
- `use_tool()`: Handle special tool usage

#### Question Bank Management:
- `question_bank_page()`: Display the question bank
- `edit_category(category_id)`: Edit a category
- `view_questions(category_id)`: View questions in a category
- `edit_question(question_id)`: Edit a question
- `delete_question(question_id)`: Delete a question
- `add_question_page()`: Add a new question
- `delete_category(category_id)`: Delete a category

#### Import/Export:
- `bulk_import_page()`: Bulk import questions
- `export_template_route(format)`: Export a template
- `export_questions(category_id)`: Export questions
- `export_questions_xlsx(category_id)`: Export questions as XLSX

### Question Bank (avirta/question_bank.py)

The question bank module manages the storage, retrieval, and categorization of questions. It provides both a `QuestionBank` class and standalone convenience functions.

#### QuestionBank Class Methods:
- `__init__(self, storage_path="questions")`: Initialize with a storage path
- `add_question(self, question_data, category_id="general", points=30)`: Add a question to the bank
- `get_question(self, category_id, points=None, prevent_repeats=True)`: Get a question from the bank
- `get_questions_by_category(self, category_id, points=None, limit=None)`: Get questions by category
- `reset_used_questions(self, category_id=None)`: Reset tracking of used questions
- `load_questions(self)`: Load questions from storage
- `_generate_question_id(self)`: Generate a unique question ID
- `_save_question(self, question_id, question_data)`: Save a question to storage

#### Standalone Functions:
- `add_question(question_data, category_id="general", points=30)`: Add a question to the bank
- `get_question(category_id, points=None, prevent_repeats=True)`: Get a question from the bank
- `get_questions_by_category(category_id, points=None, limit=None)`: Get questions by category
- `reset_used_questions(category_id=None)`: Reset tracking of used questions

### Game Room (contents/game_room/game_room.py)

The game room module manages the multiplayer game sessions through the `GameRoom` class.

#### GameRoom Class Methods:
- `__init__(self, room_id, name, host, categories=None, max_players=4)`: Initialize a game room
- `add_player(self, player_name)`: Add a player to the room
- `remove_player(self, player_name)`: Remove a player from the room
- `start_game(self, game_session)`: Start a new game
- `end_game(self)`: End the current game
- `create_board(self, question_uploader)`: Create the game board with questions
- `select_question(self, category_id, points, player_name, acting_player=None)`: Select a question
- `get_available_questions(self)`: Get available questions on the board
- `is_board_completed(self)`: Check if all questions have been answered
- `advance_turn(self)`: Move to the next player's turn

#### Special Game Tools:
- `use_double_points(self, player_name)`: Use the double points tool
- `use_change_question(self, player_name, category_id, current_points)`: Use the change question tool
- `use_steal_question(self, stealer_name, target_name, category_id, points)`: Use the steal question tool
- `has_tool_available(self, player_name, tool_name)`: Check if a player has a tool available
- `get_player_tools(self, player_name)`: Get all tools available to a player

### Question Files (contents/questions/*.json)

Questions are stored as individual JSON files in the contents/questions directory. Each file follows this format:

```json
{
  "id": "Q0000123",                  // Unique identifier for the question
  "type": "multiple_choice",         // Question type (multiple_choice, text, etc.)
  "category_id": "science",          // Category the question belongs to
  "points": "30",                    // Point value of the question
  "question": "Question text goes here?",  // The question text
  "options": ["Option A", "Option B", "Option C", "Option D"],  // For multiple_choice questions
  "correct_answer": "Option A",      // The correct answer
  "explanation": "Optional explanation of the answer",  // Optional explanation
  "created_at": "2025-05-12T23:57:03.530603",  // Creation timestamp
  "updated_at": "2025-05-13T00:04:41.471019",  // Last update timestamp
  "active": true                     // Whether the question is active
}
```

#### Question Types

The system supports multiple question types:

1. **multiple_choice**: Questions with multiple options where only one is correct
   - Requires `options` array and `correct_answer` that matches one of the options

2. **text**: Questions that require a text answer
   - Requires only `question` and `correct_answer`

3. **true_false**: True/False questions
   - `correct_answer` should be either "true" or "false"

#### Multilingual Support

The system supports questions in multiple languages, including Arabic. Unicode escape sequences are used for non-ASCII characters:

```json
{
  "type": "text",
  "question": "\u0645\u0627 \u0627\u0633\u0645 \u0627\u0644\u062f\u0648\u0644\u0629 ...",
  "correct_answer": "\u0642\u0637\u0631",
  "id": "Q0000061",
  "category_id": "general",
  "points": "20",
  "created_at": "2025-05-12T23:57:03.530603",
  "updated_at": "2025-05-13T00:04:41.471019",
  "active": true
}
```

## Common Workflows

### Adding a New Question

1. Create a new JSON file in contents/questions/
2. Use the add_new_questions.py script, or
3. Use the web interface at /add_question

### Creating a Game Room

1. Access the web interface at /create_room
2. Configure room settings (categories, difficulty, time limits)
3. Share the room code with players

### Joining a Game

1. Access the web interface at /join_room
2. Enter the room code provided by the room creator
3. Wait for the game to start

## CSS Styling

The application uses a custom CSS framework with CSS variables for consistent theming:

```css
:root {
    /* Primary Colors */
    --primary-color: #1e595e;
    --primary-color-light: #2d828a;
    --primary-color-dark: #113639;

    /* Secondary Colors */
    --secondary-color: #6c757d;
    --secondary-color-hover: #5a6268;

    /* Background Colors */
    --bg-color: #ffffff;
    --bg-color-light: #f8f8f8;
    /* ... more variables ... */
}
```

### Admin Controls (contents/admin_controls/admin_setup.py)

The admin controls module provides administrative functionality for the Avirta game through the `AdminSetup` class.

#### AdminSetup Class Methods:

- `__init__(self)`: Initialize a new admin setup instance with default settings
- `add_admin(self, username, permission_level='MODERATOR')`: Add a new admin user
- `remove_admin(self, username)`: Remove an admin user
- `update_permission(self, username, new_permission_level)`: Update an admin's permission level
- `update_game_setting(self, setting_name, value)`: Update a game setting
- `register_active_session(self, session_info)`: Register a new active game session
- `end_session(self, session_id)`: End an active game session
- `log_event(self, event_description)`: Log an event in the system
- `get_logs(self, count=10)`: Get the most recent system logs
- `has_permission(self, username, required_level)`: Check if a user has the required permission level
- `select_categories(self, categories, username=None, required_level='MODERATOR')`: Select categories for a game
- `set_question_timer(self, seconds, username=None, required_level='MODERATOR')`: Set the timer for answering questions
- `get_selected_categories(self)`: Get the currently selected categories

#### Permission Levels:

The system defines five permission levels for admin users:

```python
PERMISSION_LEVELS = {
    'SUPER_ADMIN': 100,
    'ADMIN': 75,
    'MODERATOR': 50,
    'CONTENT_CREATOR': 25,
    'VIEWER': 10
}
```

Higher values indicate higher permission levels. The `has_permission` method checks if a user's permission level is greater than or equal to the required level.

#### Game Settings:

The AdminSetup class manages the following game settings:

```python
game_settings = {
    'default_time_limit': 30,        # Time limit for answering questions (seconds)
    'max_players_per_room': 8,       # Maximum players allowed in a room
    'allow_public_rooms': True,      # Whether public rooms are allowed
    'profanity_filter': True,        # Whether to filter profanity
}
```

#### Integration with Web Application:

The AdminSetup class is instantiated in the web application:

```python
from contents.admin_controls.admin_setup import AdminSetup

admin_setup = AdminSetup()
```

A default admin user is added during application initialization:

```python
admin_setup.add_admin("admin", "ADMIN")
```

The admin functionality is primarily used for:
1. Managing game settings
2. Tracking active game sessions
3. Logging system events
4. Controlling access to administrative features

While there's no dedicated admin panel in the web interface, administrative functions are integrated into the question bank management interface, allowing authorized users to:
- Manage categories and questions
- Import and export questions
- Configure game settings

## Notes for Future Development

- The project follows a modular structure with clear separation of concerns
- The web interface is separate from the core game logic
- Question content is stored in individual JSON files for easy management
- The application supports multiple languages, including Arabic
- Admin controls provide a flexible permission system for managing access to features

## API Integration Points

The web application integrates with the core game logic through several key points:

1. **Question Bank Integration**:
   ```python
   from Avirta.avirta.question_bank import QuestionBank, add_question, get_question, get_questions_by_category, reset_used_questions
   ```

2. **Game Room Integration**:
   ```python
   from contents.game_room import GameRoom
   ```

3. **Category Management**:
   ```python
   from contents.categories_questions.category_manager import CategoryManager
   ```

4. **Question Management**:
   ```python
   from contents.game_content.question_manager import QuestionManager
   ```

## Update History

- Initial creation: Documented project structure, key components, and functionality
- First update: Added detailed information about QuestionBank, GameRoom, and Web Application implementations
- Second update: Enhanced documentation of question file format, including question types and multilingual support
- Third update: Added comprehensive information about admin controls, permission levels, and game settings

## TODO for Future Updates

- Document the authentication system
- Add information about deployment options
- Explore the bulk upload functionality in more detail
