# Game Status Manager

## Overview

The Game Status Manager is a centralized system for managing game status updates and events in Avirta. It serves as the single source of truth for all game events, ensuring consistent information across all pages and components.

This implementation follows the PRJ-006 rule from the Avirta Rule Book, which requires that all game status updates and events be managed through a centralized system.

## Features

- **Event Validation**: Validates event types and data to ensure consistency and completeness
- **Event Persistence**: Optionally persists events to disk for durability across server restarts
- **Filtering Capabilities**: Provides methods for filtering events by type, player, time range, etc.
- **Analysis and Reporting**: Includes methods for analyzing event data and generating reports
- **Centralized API**: All game events are added through a single function and accessed through a single endpoint

## Event Types

The following event types are supported:

- `game_started`: Game has started
- `player_joined`: Player joined the room
- `player_left`: Player left the room
- `turn_switch`: Turn switched to another player
- `question_selected`: Player selected a question
- `answer_submitted`: Player submitted an answer
- `answer_evaluated`: Host evaluated an answer
- `tool_used`: Player used a tool
- `score_changed`: Player's score changed
- `game_ended`: Game has ended

## Usage

### Adding Events

Events should be added using the `add_game_event` function in app.py:

```python
add_game_event(room_id, event_type, event_data)
```

Example:

```python
add_game_event(room_id, 'player_joined', {
    'player_name': player_name,
    'message': f'{player_name} joined the room'
})
```

### Retrieving Events

Events can be retrieved through the `/api/game_updates/<room_id>` endpoint, which returns all events for a room along with other game state information.

For more specific queries, the GameStatusManager class provides several methods:

- `get_events(room_id)`: Get all events for a room
- `get_events_by_type(room_id, event_type)`: Get events of a specific type
- `get_events_by_player(room_id, player_name)`: Get events for a specific player
- `get_events_by_time_range(room_id, start_time, end_time)`: Get events within a time range
- `get_latest_event(room_id)`: Get the most recent event
- `get_latest_event_by_type(room_id, event_type)`: Get the most recent event of a specific type
- `get_room_statistics(room_id)`: Get statistics for a room

## Implementation Details

### Event Structure

Each event has the following structure:

```json
{
  "type": "event_type",
  "data": {
    "player_name": "player_name",
    "message": "Event message",
    ...
  },
  "timestamp": "2023-01-01T12:00:00.000000"
}
```

### Required Data Fields

Each event type has required data fields:

- `game_started`: `message`
- `player_joined`: `player_name`, `message`
- `player_left`: `player_name`, `message`
- `turn_switch`: `previous_player`, `new_player`, `message`
- `question_selected`: `player_name`, `category`, `points`, `message`
- `answer_submitted`: `player_name`, `category`, `points`, `is_correct`, `message`
- `answer_evaluated`: `player_name`, `is_correct`, `message`
- `tool_used`: `player_name`, `tool_name`, `message`
- `score_changed`: `player_name`, `old_score`, `new_score`, `message`
- `game_ended`: `player_name`, `message`

### Persistence

Events can be persisted to disk by providing a `persistence_dir` parameter when creating the GameStatusManager:

```python
game_status_manager = GameStatusManager(persistence_dir='path/to/directory')
```

Events are stored in JSONL files, one per room, with each line containing a single event in JSON format.

## Recent Improvements

The following improvements have been made to the GameStatusManager class:

1. Added event type validation and standardization
2. Added event data validation to ensure all required fields are present
3. Added methods for filtering events by player, time range, and other criteria
4. Added methods for analyzing event data and generating reports
5. Added support for event persistence to disk
6. Enhanced the API endpoint to provide more detailed game state information
7. Added a 'game_started' event when a game is created
8. Improved documentation to help developers understand and use the system

These improvements ensure that the GameStatusManager fully satisfies the requirements in PRJ-006 and provides a robust centralized system for tracking game events.