"""
Admin Setup Module for Avirta

This module handles administrative functions such as configuring game settings,
managing user permissions, and monitoring game activity.
"""
import os
import json
import glob
from datetime import datetime

class AdminSetup:
    """
    A class to handle administrative setup and controls for the Avirta game.

    Attributes:
        admins (dict): Dictionary of admin users and their permission levels
        game_settings (dict): Dictionary of game configuration settings
        active_sessions (list): List of currently active game sessions
        logs (list): List of system logs and events
    """

    # Permission levels
    PERMISSION_LEVELS = {
        'SUPER_ADMIN': 100,
        'ADMIN': 75,
        'MODERATOR': 50,
        'CONTENT_CREATOR': 25,
        'VIEWER': 10
    }

    def __init__(self):
        """
        Initialize a new admin setup instance.
        """
        self.admins = {}
        self.saved_api_settings = {}
        # Initialize with default settings
        self.game_settings = {
            # Game settings
            'default_time_limit': 45,
            'max_players_per_room': 10,
            'max_categories_per_room': 6,  # Maximum number of categories per game room (1-6)

            # OpenAI settings
            'openai_api_key': '',
            'openai_model': 'gpt-4o',
            'openai_temperature': 0.7,
            'openai_max_tokens': 3000,

            # GitHub settings
            'github_token': '',
            'github_repo_owner': '',
            'github_repo_name': '',
            'github_branch': '',

            # Look and Feel settings - Primary Colors
            'primary_color': '#1e595e',
            'primary_color_light': '#2d828a',
            'primary_color_dark': '#113639',

            # Secondary Colors
            'secondary_color': '#6c757d',
            'secondary_color_hover': '#5a6268',

            # Background Colors
            'bg_color': '#ffffff',
            'bg_color_light': '#f8f8f8',
            'bg_color_lighter': '#f1f1f1',
            'bg_color_dark': '#c3d9dc',
            'bg_color_darker': '#9ab8bc',
            'bg_color_darkest': '#6d8c8f',

            # Text Colors
            'text_color': '#333',
            'text_color_light': '#666',
            'text_color_white': '#ffffff',

            # Status Colors
            'success_color': '#28a745',
            'success_color_light': '#d4edda',
            'success_color_dark': '#155724',
            'success_bg': '#e8f5e9',
            'success_text': '#1b5e20',

            'error_color': '#dc3545',
            'error_color_light': '#f8d7da',
            'error_color_dark': '#721c24',
            'error_bg': '#ffebee',
            'error_text': '#b71c1c',

            'info_color': '#000000',
            'info_color_light': '#e0f7fa',
            'info_color_dark': '#006064',

            # Border Colors
            'border_color': '#ddd',
            'border_color_light': '#eee',

            # Common Styling
            'border_radius_small': '3px',
            'border_radius': '4px',
            'border_radius_large': '5px',
            'box_shadow': '0 2px 5px rgba(0, 0, 0, 0.1)',

            # Spacing
            'spacing_xs': '5px',
            'spacing_sm': '10px',
            'spacing_md': '15px',
            'spacing_lg': '20px',
            'spacing_xl': '30px',

            # Typography
            'font_family': 'Cairo, sans-serif',
            'font_size_base': '16px',
            'line_height': '1.6'
        }
        self.active_sessions = []
        self.logs = []

        # Load saved settings from file (if available)
        self.load_game_settings()
        self.load_saved_api_settings_from_file()
        self.selected_categories = []

    def add_admin(self, username, permission_level='MODERATOR'):
        """
        Add a new admin user with specified permission level.

        Args:
            username (str): Username of the admin
            permission_level (str, optional): Permission level. Defaults to 'MODERATOR'.

        Returns:
            bool: True if admin was added successfully, False otherwise
        """
        if username in self.admins:
            return False

        if permission_level not in self.PERMISSION_LEVELS:
            return False

        self.admins[username] = {
            'permission_level': permission_level,
            'permission_value': self.PERMISSION_LEVELS[permission_level]
        }

        self.log_event(f"Added admin {username} with permission level {permission_level}")
        return True

    def remove_admin(self, username):
        """
        Remove an admin user.

        Args:
            username (str): Username of the admin to remove

        Returns:
            bool: True if admin was removed successfully, False otherwise
        """
        if username not in self.admins:
            return False

        del self.admins[username]
        self.log_event(f"Removed admin {username}")
        return True

    def update_permission(self, username, new_permission_level):
        """
        Update the permission level of an admin user.

        Args:
            username (str): Username of the admin
            new_permission_level (str): New permission level

        Returns:
            bool: True if permission was updated successfully, False otherwise
        """
        if username not in self.admins:
            return False

        if new_permission_level not in self.PERMISSION_LEVELS:
            return False

        old_level = self.admins[username]['permission_level']
        self.admins[username] = {
            'permission_level': new_permission_level,
            'permission_value': self.PERMISSION_LEVELS[new_permission_level]
        }

        self.log_event(f"Updated {username}'s permission from {old_level} to {new_permission_level}")
        return True

    def update_game_setting(self, setting_name, value):
        """
        Update a game setting and save it to file for persistence.

        Args:
            setting_name (str): Name of the setting to update
            value: New value for the setting

        Returns:
            bool: True if setting was updated successfully, False otherwise
        """
        if setting_name not in self.game_settings:
            return False

        old_value = self.game_settings[setting_name]
        self.game_settings[setting_name] = value

        # Save settings to file to make changes permanent
        self.save_game_settings()

        self.log_event(f"Updated game setting {setting_name} from {old_value} to {value}")
        return True

    def save_game_settings(self):
        """
        Save the game settings to a JSON file for persistence.

        Returns:
            tuple: (success, message)
        """
        try:
            # Path to the settings file
            settings_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                             'admin_controls', 'game_settings.json')

            # Save the settings to the file
            with open(settings_file_path, 'w', encoding="utf-8") as f:
                json.dump(self.game_settings, f, indent=4, ensure_ascii=False)

            self.log_event("Game settings saved to file")
            return True, "Game settings saved successfully"
        except Exception as e:
            self.log_event(f"Error saving game settings: {str(e)}")
            return False, f"Error saving game settings: {str(e)}"

    def load_game_settings(self):
        """
        Load game settings from a JSON file.

        Returns:
            tuple: (success, message)
        """
        try:
            # Path to the settings file
            settings_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                             'admin_controls', 'game_settings.json')

            # Check if the file exists
            if not os.path.exists(settings_file_path):
                self.log_event("Game settings file not found, using defaults")
                return False, "Game settings file not found, using defaults"

            # Load the settings from the file
            with open(settings_file_path, 'r') as f:
                loaded_settings = json.load(f)

            # Update the game_settings with the loaded settings
            for key, value in loaded_settings.items():
                self.game_settings[key] = value

            self.log_event("Game settings loaded from file")
            return True, "Game settings loaded successfully"
        except Exception as e:
            self.log_event(f"Error loading game settings: {str(e)}")
            return False, f"Error loading game settings: {str(e)}"

    def register_active_session(self, session_info):
        """
        Register a new active game session.

        Args:
            session_info (dict): Information about the game session

        Returns:
            bool: True if session was registered successfully
        """
        self.active_sessions.append(session_info)
        self.log_event(f"Registered new game session: {session_info.get('room_id', 'Unknown')}")
        return True

    def end_session(self, session_id):
        """
        End an active game session.

        Args:
            session_id (str): ID of the session to end

        Returns:
            bool: True if session was ended successfully, False otherwise
        """
        for i, session in enumerate(self.active_sessions):
            if session.get('room_id') == session_id:
                self.active_sessions.pop(i)
                self.log_event(f"Ended game session: {session_id}")
                return True

        return False

    def log_event(self, event_description):
        """
        Log an event in the system.

        Args:
            event_description (str): Description of the event
        """
        from datetime import datetime

        log_entry = {
            'timestamp': datetime.now(),
            'description': event_description
        }

        self.logs.append(log_entry)

    def get_logs(self, count=10):
        """
        Get the most recent system logs.

        Args:
            count (int, optional): Number of logs to retrieve. Defaults to 10.

        Returns:
            list: List of recent log entries
        """
        return self.logs[-count:] if self.logs else []

    def has_permission(self, username, required_level):
        """
        Check if a user has the required permission level.

        Args:
            username (str): Username to check
            required_level (str): Required permission level

        Returns:
            bool: True if user has required permission, False otherwise
        """
        if username not in self.admins:
            return False

        if required_level not in self.PERMISSION_LEVELS:
            return False

        user_level = self.admins[username]['permission_value']
        required_value = self.PERMISSION_LEVELS[required_level]

        return user_level >= required_value

    def select_categories(self, categories, username=None, required_level='MODERATOR'):
        """
        Select up to 5 categories for a game session.

        Args:
            categories (list): List of category IDs to select
            username (str, optional): Username of the admin making the selection. Defaults to None.
            required_level (str, optional): Required permission level. Defaults to 'MODERATOR'.

        Returns:
            tuple: (success, message or selected categories)
        """
        # Check permissions if username is provided
        if username and not self.has_permission(username, required_level):
            return False, "Insufficient permissions to select categories"

        # Limit to max_categories_per_room (default is 5)
        max_categories = self.game_settings.get('max_categories_per_room', 5)
        # Ensure max_categories is within valid range (1-6)
        max_categories = max(1, min(6, max_categories))
        if len(categories) > max_categories:
            categories = categories[:max_categories]

        # Store the selected categories
        self.selected_categories = categories

        # Log the event
        self.log_event(f"Selected categories: {', '.join(categories)}")

        return True, self.selected_categories

    def set_question_timer(self, seconds, username=None, required_level='MODERATOR'):
        """
        Set the timer for answering questions.

        Args:
            seconds (int): Number of seconds for the timer
            username (str, optional): Username of the admin making the change. Defaults to None.
            required_level (str, optional): Required permission level. Defaults to 'MODERATOR'.

        Returns:
            tuple: (success, message)
        """
        # Check permissions if username is provided
        if username and not self.has_permission(username, required_level):
            return False, "Insufficient permissions to set timer"

        # Validate the timer value
        if not isinstance(seconds, int) or seconds < 5 or seconds > 120:
            return False, "Timer must be between 5 and 120 seconds"

        # Update the game setting
        success = self.update_game_setting('default_time_limit', seconds)

        if success:
            return True, f"Question timer set to {seconds} seconds"
        else:
            return False, "Failed to update timer setting"

    def get_selected_categories(self):
        """
        Get the currently selected categories.

        Returns:
            list: List of selected category IDs
        """
        return self.selected_categories

    def generate_custom_css(self):
        """
        Generate custom CSS based on the current game settings.

        This method creates a CSS string with variables set to the values in game_settings.

        Returns:
            str: CSS content with custom variables
        """
        css = "/* Avirta Game - Custom Stylesheet */\n\n"
        css += "/* Generated on: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " */\n\n"

        css += ":root {\n"

        # Primary Colors
        css += "    /* Primary Colors */\n"
        css += f"    --primary-color: {self.game_settings['primary_color']};\n"
        css += f"    --primary-color-light: {self.game_settings['primary_color_light']};\n"
        css += f"    --primary-color-dark: {self.game_settings['primary_color_dark']};\n\n"

        # Secondary Colors
        css += "    /* Secondary Colors */\n"
        css += f"    --secondary-color: {self.game_settings['secondary_color']};\n"
        css += f"    --secondary-color-hover: {self.game_settings['secondary_color_hover']};\n\n"

        # Background Colors
        css += "    /* Background Colors */\n"
        css += f"    --bg-color: {self.game_settings['bg_color']};\n"
        css += f"    --bg-color-light: {self.game_settings['bg_color_light']};\n"
        css += f"    --bg-color-lighter: {self.game_settings['bg_color_lighter']};\n"
        css += f"    --bg-color-dark: {self.game_settings['bg_color_dark']};\n"
        css += f"    --bg-color-darker: {self.game_settings['bg_color_darker']};\n"
        css += f"    --bg-color-darkest: {self.game_settings['bg_color_darkest']};\n\n"

        # Text Colors
        css += "    /* Text Colors */\n"
        css += f"    --text-color: {self.game_settings['text_color']};\n"
        css += f"    --text-color-light: {self.game_settings['text_color_light']};\n"
        css += f"    --text-color-white: {self.game_settings['text_color_white']};\n\n"

        # Status Colors
        css += "    /* Status Colors */\n"
        css += f"    --success-color: {self.game_settings['success_color']};\n"
        css += f"    --success-color-light: {self.game_settings['success_color_light']};\n"
        css += f"    --success-color-dark: {self.game_settings['success_color_dark']};\n"
        css += f"    --success-bg: {self.game_settings['success_bg']};\n"
        css += f"    --success-text: {self.game_settings['success_text']};\n\n"

        css += f"    --error-color: {self.game_settings['error_color']};\n"
        css += f"    --error-color-light: {self.game_settings['error_color_light']};\n"
        css += f"    --error-color-dark: {self.game_settings['error_color_dark']};\n"
        css += f"    --error-bg: {self.game_settings['error_bg']};\n"
        css += f"    --error-text: {self.game_settings['error_text']};\n\n"

        css += f"    --info-color: {self.game_settings['info_color']};\n"
        css += f"    --info-color-light: {self.game_settings['info_color_light']};\n"
        css += f"    --info-color-dark: {self.game_settings['info_color_dark']};\n\n"

        # Border Colors
        css += "    /* Border Colors */\n"
        css += f"    --border-color: {self.game_settings['border_color']};\n"
        css += f"    --border-color-light: {self.game_settings['border_color_light']};\n\n"

        # Common Styling
        css += "    /* Common Styling */\n"
        css += f"    --border-radius-small: {self.game_settings['border_radius_small']};\n"
        css += f"    --border-radius: {self.game_settings['border_radius']};\n"
        css += f"    --border-radius-large: {self.game_settings['border_radius_large']};\n\n"

        css += f"    --box-shadow: {self.game_settings['box_shadow']};\n\n"

        # Spacing
        css += "    /* Spacing */\n"
        css += f"    --spacing-xs: {self.game_settings['spacing_xs']};\n"
        css += f"    --spacing-sm: {self.game_settings['spacing_sm']};\n"
        css += f"    --spacing-md: {self.game_settings['spacing_md']};\n"
        css += f"    --spacing-lg: {self.game_settings['spacing_lg']};\n"
        css += f"    --spacing-xl: {self.game_settings['spacing_xl']};\n"
        css += "}\n\n"

        # Typography
        css += "/* Base Typography */\n"
        css += "body {\n"
        css += f"    font-family: {self.game_settings['font_family']};\n"
        css += f"    font-size: {self.game_settings['font_size_base']};\n"
        css += f"    line-height: {self.game_settings['line_height']};\n"
        css += "}\n"

        return css

    def save_custom_css(self):
        """
        Save the custom CSS to a file.

        This method generates the custom CSS and saves it to a file in the static directory.

        Returns:
            tuple: (success, message)
        """
        try:
            css_content = self.generate_custom_css()

            # Path to the custom CSS file
            css_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                        'web', 'static', 'css', 'custom.css')

            # Save the CSS content to the file
            with open(css_file_path, 'w') as f:
                f.write(css_content)

            self.log_event("Custom CSS file generated and saved")
            return True, "Custom CSS file generated and saved successfully"
        except Exception as e:
            self.log_event(f"Error saving custom CSS: {str(e)}")
            return False, f"Error saving custom CSS: {str(e)}"

    def save_api_settings_to_file(self):
        """
        Save the saved API settings to a JSON file for persistence.

        Returns:
            tuple: (success, message)
        """
        try:
            # Path to the settings file
            settings_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                             'admin_controls', 'saved_api_settings.json')

            # Save the settings to the file
            with open(settings_file_path, 'w', encoding="utf-8") as f:
                json.dump(self.saved_api_settings, f, indent=4, ensure_ascii=False)

            self.log_event("Saved API settings saved to file")
            return True, "Saved API settings saved successfully"
        except Exception as e:
            self.log_event(f"Error saving API settings: {str(e)}")
            return False, f"Error saving API settings: {str(e)}"

    def load_saved_api_settings_from_file(self):
        """
        Load saved API settings from a JSON file.

        Returns:
            tuple: (success, message)
        """
        try:
            # Path to the settings file
            settings_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                             'admin_controls', 'saved_api_settings.json')

            # Check if the file exists
            if not os.path.exists(settings_file_path):
                self.log_event("Saved API settings file not found, using empty dictionary")
                return False, "Saved API settings file not found, using empty dictionary"

            # Load the settings from the file
            with open(settings_file_path, 'r') as f:
                self.saved_api_settings = json.load(f)

            self.log_event("Saved API settings loaded from file")
            return True, "Saved API settings loaded successfully"
        except Exception as e:
            self.log_event(f"Error loading saved API settings: {str(e)}")
            return False, f"Error loading saved API settings: {str(e)}"

    def save_api_settings(self, name):
        """
        Save the current API settings with a name.

        Args:
            name (str): Name to identify the saved settings

        Returns:
            tuple: (success, message)
        """
        if not name or not name.strip():
            return False, "Settings name cannot be empty"

        # Get GitHub settings from the first saved settings if available
        github_settings = {}
        if self.saved_api_settings:
            first_setting = list(self.saved_api_settings.values())[0]
            github_settings = {
                'github_token': first_setting.get('github_token', ''),
                'github_repo_owner': first_setting.get('github_repo_owner', ''),
                'github_repo_name': first_setting.get('github_repo_name', ''),
                'github_branch': first_setting.get('github_branch', '')
            }

        # Extract OpenAI settings from game_settings
        api_settings = {
            'openai_api_key': self.game_settings.get('openai_api_key', ''),
            'openai_model': self.game_settings.get('openai_model', 'gpt-3.5-turbo'),
            'openai_temperature': self.game_settings.get('openai_temperature', 0.7),
            'openai_max_tokens': self.game_settings.get('openai_max_tokens', 3000),
            # GitHub settings from saved settings
            'github_token': github_settings.get('github_token', ''),
            'github_repo_owner': github_settings.get('github_repo_owner', ''),
            'github_repo_name': github_settings.get('github_repo_name', ''),
            'github_branch': github_settings.get('github_branch', '')
        }

        # Save the settings with the given name
        self.saved_api_settings[name.strip()] = api_settings

        # Save to file to make changes permanent
        success, message = self.save_api_settings_to_file()
        if not success:
            return False, f"Failed to save settings permanently: {message}"

        self.log_event(f"API settings saved as '{name}'")
        return True, f"API settings saved as '{name}'"

    def load_api_settings(self, name):
        """
        Load saved API settings by name.

        Args:
            name (str): Name of the saved settings to load

        Returns:
            tuple: (success, message)
        """
        if name not in self.saved_api_settings:
            return False, f"No saved settings found with name '{name}'"

        # Get the saved settings
        api_settings = self.saved_api_settings[name]

        # Update only the OpenAI settings in game_settings
        for key, value in api_settings.items():
            if key.startswith('openai_'):
                self.game_settings[key] = value

        # Save settings to file to make changes permanent
        self.save_game_settings()

        self.log_event(f"Loaded API settings '{name}'")
        return True, f"Loaded API settings '{name}'"

    def get_saved_api_settings(self):
        """
        Get all saved API settings.

        Returns:
            dict: Dictionary of saved API settings
        """
        return self.saved_api_settings

    def delete_api_settings(self, name):
        """
        Delete saved API settings by name.

        Args:
            name (str): Name of the saved settings to delete

        Returns:
            tuple: (success, message)
        """
        if name not in self.saved_api_settings:
            return False, f"No saved settings found with name '{name}'"

        # Delete the saved settings
        del self.saved_api_settings[name]

        # Save to file to make changes permanent
        success, message = self.save_api_settings_to_file()
        if not success:
            return False, f"Failed to save changes permanently: {message}"

        self.log_event(f"Deleted API settings '{name}'")
        return True, f"Deleted API settings '{name}'"

    def get_available_themes(self):
        """
        Get a list of available CSS themes from the themes directory.

        Returns:
            list: List of theme dictionaries with name and path
        """
        themes = []

        # Path to the themes directory
        themes_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                'static', 'css', 'themes')

        # Check if the directory exists
        if not os.path.exists(themes_dir):
            # Try to create the directory if it doesn't exist
            try:
                os.makedirs(themes_dir)
                self.log_event(f"Created themes directory at {themes_dir}")
            except Exception as e:
                self.log_event(f"Error creating themes directory: {str(e)}")
            return themes

        # Get all CSS files in the themes directory
        theme_files = glob.glob(os.path.join(themes_dir, '*.css'))

        for theme_file in theme_files:
            # Get the theme name from the filename (without extension)
            theme_name = os.path.splitext(os.path.basename(theme_file))[0]

            # Format the theme name for display (replace underscores with spaces and capitalize)
            display_name = theme_name.replace('_', ' ').title()

            themes.append({
                'name': theme_name,
                'display_name': display_name,
                'path': theme_file
            })

        # If no themes were found, log a warning
        if not themes:
            self.log_event("No theme files found in the themes directory")

        return themes

    def apply_theme(self, theme_name):
        """
        Apply a CSS theme immediately.

        Args:
            theme_name (str): Name of the theme to apply

        Returns:
            tuple: (success, message)
        """
        # Log the current directory and theme name for debugging
        current_dir = os.getcwd()
        self.log_event(f"Current directory: {current_dir}")
        self.log_event(f"Applying theme: {theme_name}")

        # Path to the themes directory
        themes_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                'static', 'css', 'themes')
        self.log_event(f"Themes directory: {themes_dir}")

        # Path to the theme file
        theme_file = os.path.join(themes_dir, f"{theme_name}.css")
        self.log_event(f"Theme file path: {theme_file}")

        # Check if the theme file exists
        if not os.path.exists(theme_file):
            self.log_event(f"Theme file not found: {theme_file}")
            return False, f"Theme '{theme_name}' not found"

        try:
            # Read the theme file
            with open(theme_file, 'r') as f:
                theme_content = f.read()
            self.log_event(f"Successfully read theme file: {len(theme_content)} bytes")

            # Path to the custom CSS file
            custom_css_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                        'static', 'css', 'custom.css')
            self.log_event(f"Custom CSS path: {custom_css_path}")

            # Save the theme content to the custom CSS file
            with open(custom_css_path, 'w') as f:
                f.write(theme_content)
            self.log_event(f"Successfully wrote to custom CSS file")

            # Store the selected theme in game_settings (for session only)
            self.game_settings['selected_theme'] = theme_name

            self.log_event(f"Applied theme '{theme_name}'")
            return True, f"Theme '{theme_name}' applied successfully"
        except Exception as e:
            self.log_event(f"Error applying theme '{theme_name}': {str(e)}")
            return False, f"Error applying theme '{theme_name}': {str(e)}"
