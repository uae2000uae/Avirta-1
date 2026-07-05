"""
Game Status Manager Module for Avirta

This module provides a centralized system for managing game status updates and events.
It ensures that all game events are collected in one place and can be accessed by different
parts of the application in a consistent manner.

As per PRJ-006, this system serves as the single source of truth for all game events,
tracking and recording all key game events including game start, turn changes, question selection,
answer results, score changes, tool activation, players joining/leaving, and game end.
"""

from datetime import datetime
import json
import os
from typing import Dict, List, Optional, Any, Union

# Global instance of GameStatusManager
_game_status_manager = None

# Optional stats sink (e.g. AdminSetup). When set, every game event is also
# forwarded to it via record_game_event() so admin dashboard stats stay current.
_stats_sink = None

def get_game_status_manager():
    """
    Get the global GameStatusManager instance.

    Returns:
        GameStatusManager: The global GameStatusManager instance
    """
    global _game_status_manager
    return _game_status_manager

def set_game_status_manager(manager):
    """
    Set the global GameStatusManager instance.

    Args:
        manager (GameStatusManager): The GameStatusManager instance to set
    """
    global _game_status_manager
    _game_status_manager = manager

def set_stats_sink(sink):
    """
    Register an object that records gameplay stats.

    The sink must expose ``record_game_event(event_type, room_id, event_data)``.
    Used to feed the admin dashboard's live gameplay counters.

    Args:
        sink: Object implementing record_game_event(...), or None to disable.
    """
    global _stats_sink
    _stats_sink = sink

def add_game_event(room_id, event_type, event_data):
    """
    Add an event to the centralized game status manager for a specific room.
    As per PRJ-006, this function serves as the centralized method for adding game events.

    Args:
        room_id (str): The ID of the room where the event occurred
        event_type (str): The type of event (e.g., 'player_joined', 'question_selected')
        event_data (dict): Additional data about the event

    Returns:
        bool: True if the event was added successfully, False otherwise
    """
    global _game_status_manager
    if _game_status_manager is None:
        print("Warning: GameStatusManager not initialized")
        return False

    # Ensure message field exists in event_data
    if 'message' not in event_data:
        # Try to generate a default message based on event type and data
        if event_type == 'player_joined' and 'player_name' in event_data:
            event_data['message'] = f"{event_data['player_name']} joined the room"
        elif event_type == 'player_left' and 'player_name' in event_data:
            event_data['message'] = f"{event_data['player_name']} left the room"
        elif event_type == 'question_selected' and 'player_name' in event_data:
            points = event_data.get('points', 'unknown')
            category = event_data.get('category', 'unknown')
            event_data['message'] = f"{event_data['player_name']} selected a {points}-point question from {category}"
        elif event_type == 'answer_submitted' and 'player_name' in event_data:
            result = 'correct' if event_data.get('is_correct', False) else 'incorrect'
            points = event_data.get('points', 0)
            earned = points if event_data.get('is_correct', False) else 0
            event_data['message'] = f"{event_data['player_name']} answered {result} and earned {earned} points"
        elif event_type == 'turn_switch' and 'previous_player' in event_data and 'new_player' in event_data:
            event_data['message'] = f"Turn switched from {event_data['previous_player']} to {event_data['new_player']}"
        elif event_type == 'tool_used' and 'player_name' in event_data and 'tool_name' in event_data:
            event_data['message'] = f"{event_data['player_name']} used the {event_data['tool_name']} tool"
        elif event_type == 'game_ended' and 'player_name' in event_data:
            event_data['message'] = f"The game has been ended by {event_data['player_name']}"
        else:
            # Default message if we can't generate a specific one
            event_data['message'] = f"Event: {event_type}"

    # Use the centralized game status manager to add the event
    success = _game_status_manager.add_event(room_id, event_type, event_data)

    if not success:
        print(f"Warning: Failed to add event of type '{event_type}' for room '{room_id}'")
    elif _stats_sink is not None:
        # Forward successful events to the admin stats sink. Never let stats
        # bookkeeping break gameplay, so swallow any errors here.
        try:
            _stats_sink.record_game_event(event_type, room_id, event_data)
        except Exception as e:
            print(f"Warning: stats sink failed for event '{event_type}': {e}")
    return success

class GameStatusManager:
    """
    A class to manage game status updates and events for Avirta games.

    This class provides a centralized system for tracking game events, ensuring
    that all pages and components have access to the same, consistent information.

    Attributes:
        events (dict): Dictionary mapping room IDs to lists of events
        max_events_per_room (int): Maximum number of events to store per room
        valid_event_types (set): Set of valid event types
        required_data_fields (dict): Dictionary mapping event types to required data fields
        persistence_dir (str): Directory to store event logs and game rooms for persistence
    """

    # Define valid event types as per PRJ-006
    VALID_EVENT_TYPES = {
        'game_started',       # Game has started
        'player_joined',      # Player joined the room
        'player_left',        # Player left the room
        'turn_switch',        # Turn switched to another player
        'question_selected',  # Player selected a question
        'answer_submitted',   # Player submitted an answer
        'answer_evaluated',   # Host evaluated an answer
        'tool_used',          # Player used a tool
        'score_changed',      # Player's score changed
        'game_ended'          # Game has ended
    }

    # Define required data fields for each event type
    REQUIRED_DATA_FIELDS = {
        'game_started': ['message'],
        'player_joined': ['player_name', 'message'],
        'player_left': ['player_name', 'message'],
        'turn_switch': ['previous_player', 'new_player', 'message'],
        'question_selected': ['player_name', 'category', 'points', 'message'],
        'answer_submitted': ['player_name', 'category', 'points', 'is_correct', 'message'],
        'answer_evaluated': ['player_name', 'is_correct', 'message'],
        'tool_used': ['player_name', 'tool_name', 'message'],
        'score_changed': ['player_name', 'old_score', 'new_score', 'message'],
        'game_ended': ['player_name', 'message']
    }

    def __init__(self, max_events_per_room=50, persistence_dir=None):
        """
        Initialize a new GameStatusManager.

        Args:
            max_events_per_room (int, optional): Maximum number of events to store per room. Defaults to 50.
            persistence_dir (str, optional): Directory to store event logs for persistence. Defaults to None.
        """
        self.events: Dict[str, List[Dict[str, Any]]] = {}
        self.max_events_per_room = max_events_per_room
        self.persistence_dir = persistence_dir

        # Create persistence directory if specified and doesn't exist
        if self.persistence_dir and not os.path.exists(self.persistence_dir):
            os.makedirs(self.persistence_dir)

        # Create separate folders for rooms and events
        if self.persistence_dir:
            self.rooms_dir = os.path.join(self.persistence_dir, 'rooms')
            self.events_dir = os.path.join(self.persistence_dir, 'events')

            if not os.path.exists(self.rooms_dir):
                os.makedirs(self.rooms_dir)

            if not os.path.exists(self.events_dir):
                os.makedirs(self.events_dir)
        else:
            self.rooms_dir = None
            self.events_dir = None

        # Load any existing events from persistence
        self._load_events_from_persistence()

    def add_event(self, room_id: str, event_type: str, event_data: Dict[str, Any]) -> bool:
        """
        Add an event to the events dictionary for a specific room.
        Validates the event type and data before adding.

        Args:
            room_id (str): The ID of the room where the event occurred
            event_type (str): The type of event (e.g., 'player_joined', 'question_selected')
            event_data (dict): Additional data about the event

        Returns:
            bool: True if the event was added successfully, False otherwise
        """
        # Validate event type
        if event_type not in self.VALID_EVENT_TYPES:
            print(f"Warning: Invalid event type '{event_type}'. Valid types are: {', '.join(self.VALID_EVENT_TYPES)}")
            return False

        # Validate event data
        if not self._validate_event_data(event_type, event_data):
            print(f"Warning: Invalid event data for event type '{event_type}'. Required fields: {self.REQUIRED_DATA_FIELDS.get(event_type, [])}")
            return False

        if room_id not in self.events:
            self.events[room_id] = []

        # Add timestamp to the event
        event = {
            'type': event_type,
            'data': event_data,
            'timestamp': datetime.now().isoformat()
        }

        # Add the event to the list for this room
        self.events[room_id].append(event)

        # Keep only the last max_events_per_room events
        if len(self.events[room_id]) > self.max_events_per_room:
            self.events[room_id] = self.events[room_id][-self.max_events_per_room:]

        # Persist the event if persistence is enabled
        self._persist_event(room_id, event)

        return True

    def _validate_event_data(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """
        Validate event data against required fields for the event type.

        Args:
            event_type (str): The type of event
            event_data (dict): The event data to validate

        Returns:
            bool: True if the event data is valid, False otherwise
        """
        required_fields = self.REQUIRED_DATA_FIELDS.get(event_type, [])
        for field in required_fields:
            if field not in event_data:
                return False
        return True

    def _persist_event(self, room_id: str, event: Dict[str, Any]) -> None:
        """
        Persist an event to disk if persistence is enabled.

        Args:
            room_id (str): The ID of the room where the event occurred
            event (dict): The event to persist
        """
        if not self.persistence_dir or not self.events_dir:
            return

        # Create a file for each room in the events subfolder with yymmdd_hhmm timestamp
        current_time = datetime.now()
        timestamp = current_time.strftime("%y%m%d_%H%M")
        file_path = os.path.join(self.events_dir, f"{timestamp}_{room_id}.jsonl")

        try:
            # Append the event to the file
            with open(file_path, 'a', encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"Error persisting event: {e}")

    def _load_events_from_persistence(self) -> None:
        """
        Load events from persistence if enabled.
        """
        if not self.persistence_dir or not self.events_dir or not os.path.exists(self.events_dir):
            return

        try:
            # Get all event files in the events subfolder with the new naming convention
            for filename in os.listdir(self.events_dir):
                if filename.endswith('.jsonl'):
                    # New format: yymmdd_hhmm_roomid.jsonl
                    # Extract room_id from the filename (everything after the timestamp)
                    parts = filename.split('_', 2)  # Split into [yymm, dd, hhmm_roomid.jsonl]
                    if len(parts) >= 3:
                        # Further split the third part to get roomid
                        room_parts = parts[2].split('.')
                        if len(room_parts) >= 1:
                            room_id = room_parts[0]

                            if room_id not in self.events:
                                self.events[room_id] = []

                            # Read events from the file
                            file_path = os.path.join(self.events_dir, filename)
                            with open(file_path, 'r', encoding="utf-8") as f:
                                for line in f:
                                    try:
                                        event = json.loads(line.strip())
                                        self.events[room_id].append(event)
                                    except json.JSONDecodeError:
                                        continue

                            # Keep only the last max_events_per_room events
                            if len(self.events[room_id]) > self.max_events_per_room:
                                self.events[room_id] = self.events[room_id][-self.max_events_per_room:]
        except Exception as e:
            print(f"Error loading events from persistence: {e}")

    def get_events(self, room_id: str) -> List[Dict[str, Any]]:
        """
        Get all events for a specific room.

        Args:
            room_id (str): The ID of the room to get events for

        Returns:
            list: List of events for the room, or an empty list if the room has no events
        """
        return self.events.get(room_id, [])

    def get_events_by_type(self, room_id: str, event_type: str) -> List[Dict[str, Any]]:
        """
        Get events of a specific type for a room.

        Args:
            room_id (str): The ID of the room to get events for
            event_type (str): The type of events to get

        Returns:
            list: List of events of the specified type for the room
        """
        # Validate event type
        if event_type not in self.VALID_EVENT_TYPES:
            print(f"Warning: Invalid event type '{event_type}'. Valid types are: {', '.join(self.VALID_EVENT_TYPES)}")
            return []

        events = self.get_events(room_id)
        return [event for event in events if event['type'] == event_type]

    def get_events_by_player(self, room_id: str, player_name: str) -> List[Dict[str, Any]]:
        """
        Get events for a specific player in a room.

        Args:
            room_id (str): The ID of the room to get events for
            player_name (str): The name of the player to get events for

        Returns:
            list: List of events for the player in the room
        """
        events = self.get_events(room_id)
        return [event for event in events if 
                'data' in event and 
                'player_name' in event['data'] and 
                event['data']['player_name'] == player_name]

    def get_events_by_time_range(self, room_id: str, start_time: str, end_time: str) -> List[Dict[str, Any]]:
        """
        Get events within a specific time range for a room.

        Args:
            room_id (str): The ID of the room to get events for
            start_time (str): The start time in ISO format
            end_time (str): The end time in ISO format

        Returns:
            list: List of events within the time range for the room
        """
        events = self.get_events(room_id)
        return [event for event in events if 
                'timestamp' in event and 
                start_time <= event['timestamp'] <= end_time]

    def get_latest_event(self, room_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent event for a room.

        Args:
            room_id (str): The ID of the room to get the latest event for

        Returns:
            dict: The most recent event for the room, or None if the room has no events
        """
        events = self.get_events(room_id)
        return events[-1] if events else None

    def get_latest_event_by_type(self, room_id: str, event_type: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent event of a specific type for a room.

        Args:
            room_id (str): The ID of the room to get the latest event for
            event_type (str): The type of event to get

        Returns:
            dict: The most recent event of the specified type for the room, or None if no such event exists
        """
        events = self.get_events_by_type(room_id, event_type)
        return events[-1] if events else None

    def get_player_score_history(self, room_id: str, player_name: str) -> List[Dict[str, Any]]:
        """
        Get the score history for a specific player in a room.

        Args:
            room_id (str): The ID of the room to get the score history for
            player_name (str): The name of the player to get the score history for

        Returns:
            list: List of score change events for the player in the room
        """
        return self.get_events_by_player(room_id, player_name)

    def get_room_statistics(self, room_id: str) -> Dict[str, Any]:
        """
        Get statistics for a specific room.

        Args:
            room_id (str): The ID of the room to get statistics for

        Returns:
            dict: Dictionary containing statistics for the room
        """
        events = self.get_events(room_id)

        # Initialize statistics
        stats = {
            'total_events': len(events),
            'event_types': {},
            'player_events': {},
            'questions_answered': 0,
            'correct_answers': 0,
            'tools_used': 0
        }

        # Calculate statistics
        for event in events:
            # Count events by type
            event_type = event.get('type')
            if event_type:
                stats['event_types'][event_type] = stats['event_types'].get(event_type, 0) + 1

            # Count events by player
            if 'data' in event and 'player_name' in event['data']:
                player_name = event['data']['player_name']
                if player_name not in stats['player_events']:
                    stats['player_events'][player_name] = 0
                stats['player_events'][player_name] += 1

            # Count questions answered
            if event_type == 'answer_submitted' or event_type == 'answer_evaluated':
                stats['questions_answered'] += 1

                # Count correct answers
                if 'data' in event and 'is_correct' in event['data'] and event['data']['is_correct']:
                    stats['correct_answers'] += 1

            # Count tools used
            if event_type == 'tool_used':
                stats['tools_used'] += 1

        return stats

    def clear_events(self, room_id: str) -> None:
        """
        Clear all events for a specific room.

        Args:
            room_id (str): The ID of the room to clear events for
        """
        if room_id in self.events:
            self.events[room_id] = []

        # Remove all event files for this room_id from the events subfolder
        if self.events_dir:
            try:
                for filename in os.listdir(self.events_dir):
                    if filename.endswith(f"{room_id}.jsonl"):
                        file_path = os.path.join(self.events_dir, filename)
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            print(f"Error removing events file {filename}: {e}")
            except Exception as e:
                print(f"Error listing event files: {e}")

    def room_exists(self, room_id: str) -> bool:
        """
        Check if a room has any events.

        Args:
            room_id (str): The ID of the room to check

        Returns:
            bool: True if the room has events, False otherwise
        """
        return room_id in self.events

    def cleanup_room_data(self, room_id: str) -> bool:
        """
        Clean up all data for a specific room when a game ends.
        This removes both the room file and events file.

        Args:
            room_id (str): The ID of the room to clean up

        Returns:
            bool: True if the cleanup was successful, False otherwise
        """
        success = True

        # Clear events from memory
        if room_id in self.events:
            self.events[room_id] = []

        # Remove all event files for this room_id from the events subfolder
        if self.events_dir:
            try:
                for filename in os.listdir(self.events_dir):
                    if filename.endswith(f"{room_id}.jsonl"):
                        events_file_path = os.path.join(self.events_dir, filename)
                        try:
                            os.remove(events_file_path)
                        except Exception as e:
                            print(f"Error removing events file {filename}: {e}")
                            success = False
            except Exception as e:
                print(f"Error listing event files: {e}")
                success = False

        # Remove all room files for this room_id from the rooms subfolder
        if self.rooms_dir:
            try:
                for filename in os.listdir(self.rooms_dir):
                    if filename.endswith(f"{room_id}.json"):
                        room_file_path = os.path.join(self.rooms_dir, filename)
                        try:
                            os.remove(room_file_path)
                        except Exception as e:
                            print(f"Error removing room file {filename}: {e}")
                            success = False
            except Exception as e:
                print(f"Error listing room files: {e}")
                success = False

        return success

    def persist_game_room(self, room_id: str, game_room: 'GameRoom') -> bool:
        """
        Persist a game room to disk.

        Args:
            room_id (str): The ID of the room to persist
            game_room (GameRoom): The game room object to persist

        Returns:
            bool: True if the room was persisted successfully, False otherwise
        """
        if not self.persistence_dir or not self.rooms_dir:
            return False

        # Create a file for the room in the rooms subfolder with yymmdd_hhmm timestamp
        current_time = datetime.now()
        timestamp = current_time.strftime("%y%m%d_%H%M")
        file_path = os.path.join(self.rooms_dir, f"{timestamp}_{room_id}.json")

        try:
            # Serialize the game room to JSON
            room_data = {
                'room_id': game_room.room_id,
                'name': game_room.name,
                'host': game_room.host,
                'players': game_room.players,
                'max_players': game_room.max_players,
                'is_active': game_room.is_active,
                'current_player': game_room.current_player,
                'question_active': game_room.question_active,
                'categories': game_room.categories,
                'board': game_room.board,
                'answered_questions': list(game_room.answered_questions),  # Convert set to list for JSON serialization
                'player_tools': game_room.player_tools
            }

            # Write to file
            with open(file_path, 'w', encoding="utf-8") as f:
                json.dump(room_data, f, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"Error persisting game room: {e}")
            return False

    def load_game_room(self, room_id: str) -> Optional['GameRoom']:
        """
        Load a game room from disk.

        Args:
            room_id (str): The ID of the room to load

        Returns:
            GameRoom: The loaded game room object, or None if not found or error
        """
        if not self.persistence_dir or not self.rooms_dir:
            return None

        # Find the most recent room file for this room_id with the new naming convention
        latest_file = None
        latest_timestamp = None

        try:
            for filename in os.listdir(self.rooms_dir):
                if filename.endswith(f"{room_id}.json"):
                    # New format: yymmdd_hhmm_roomid.json
                    # Extract timestamp from the filename
                    parts = filename.split('_', 2)  # Split into [yymm, dd, hhmm_roomid.json]
                    if len(parts) >= 2:
                        timestamp = f"{parts[0]}_{parts[1]}"
                        if latest_timestamp is None or timestamp > latest_timestamp:
                            latest_timestamp = timestamp
                            latest_file = filename
        except Exception as e:
            print(f"Error finding room file: {e}")

        if latest_file:
            file_path = os.path.join(self.rooms_dir, latest_file)
            return self._load_game_room_from_file(file_path)

        return None

    def _load_game_room_from_file(self, file_path: str) -> Optional['GameRoom']:
        """
        Load a game room from a specific file.

        Args:
            file_path (str): Path to the room file

        Returns:
            GameRoom: The loaded game room object, or None if error
        """
        try:
            with open(file_path, 'r', encoding="utf-8") as f:
                room_data = json.load(f)

            # Import here to avoid circular imports
            from contents.game_room.game_room import GameRoom

            # Create a new GameRoom instance from the data
            game_room = GameRoom(
                room_id=room_data['room_id'],
                name=room_data['name'],
                host=room_data['host'],
                categories=room_data['categories'],
                max_players=room_data.get('max_players', 10)
            )

            # Set other properties
            game_room.players = room_data['players']
            game_room.is_active = room_data['is_active']
            game_room.current_player = room_data['current_player']
            game_room.question_active = room_data['question_active']
            game_room.board = room_data['board']
            game_room.answered_questions = set(room_data['answered_questions'])  # Convert list back to set
            game_room.player_tools = room_data['player_tools']

            return game_room
        except Exception as e:
            print(f"Error loading game room from file {file_path}: {e}")
            return None
