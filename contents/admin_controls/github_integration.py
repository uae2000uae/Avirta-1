"""
GitHub Integration Module for Avirta

This module provides functionality to push question files to GitHub.
It detects changes in the question JSON files and pushes them to a GitHub repository.

The correct GitHub repository path structure is:
https://github.com/uae2000uae/Avirta-WebApp/tree/Avirta-1/contents/questions
which follows the pattern: github.com/username/reponame/tree/branchname/contents/questions
"""

import os
import json
import requests
import base64
from datetime import datetime
import logging

class GitHubIntegration:
    """
    A class to handle GitHub integration for pushing question files.

    Attributes:
        github_token (str): GitHub personal access token
        repo_owner (str): GitHub repository owner (username or organization)
        repo_name (str): GitHub repository name
        branch (str): GitHub branch name
        questions_dir (str): Directory containing question JSON files
    """

    def __init__(self, github_token, repo_owner, repo_name, branch="main"):
        """
        Initialize a new GitHub integration instance.

        Args:
            github_token (str): GitHub personal access token
            repo_owner (str): GitHub repository owner (username or organization)
            repo_name (str): GitHub repository name
            branch (str, optional): GitHub branch name. Defaults to "main".
        """
        self.github_token = github_token
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch

        # Set the questions directory path
        self.questions_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'questions')

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        # Log initialization
        self.logger.info(f"GitHub Integration initialized for repo: {repo_owner}/{repo_name}, branch: {branch}")
        self.logger.info(f"Questions directory: {self.questions_dir}")

        # Check if questions directory exists
        if not os.path.exists(self.questions_dir):
            self.logger.error(f"Questions directory not found: {self.questions_dir}")
        else:
            question_files = [f for f in os.listdir(self.questions_dir) if f.endswith('.json')]
            self.logger.info(f"Found {len(question_files)} question files in {self.questions_dir}")

    def validate_credentials(self):
        """
        Validate GitHub credentials by making a test API call.

        Returns:
            tuple: (success, message)
        """
        try:
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            # Test API call to get user info
            response = requests.get('https://api.github.com/user', headers=headers)

            if response.status_code == 200:
                user_data = response.json()
                return True, f"Successfully authenticated as {user_data.get('login')}"
            else:
                error_msg = response.json().get('message', 'Unknown error')
                return False, f"Authentication failed: {error_msg}"

        except Exception as e:
            self.logger.error(f"Error validating GitHub credentials: {str(e)}")
            return False, f"Error validating GitHub credentials: {str(e)}"

    def get_file_from_github(self, file_path):
        """
        Get a file from GitHub repository.

        Args:
            file_path (str): Path to the file in the repository

        Returns:
            dict: File data including content and sha, or None if file doesn't exist
        """
        try:
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            # Convert Windows path to GitHub path format
            github_path = file_path.replace('\\', '/')

            # API call to get file content
            url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{github_path}?ref={self.branch}'
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                # File doesn't exist in the repository
                return None
            else:
                error_msg = response.json().get('message', 'Unknown error')
                self.logger.error(f"Error getting file from GitHub: {error_msg}")
                return None

        except Exception as e:
            self.logger.error(f"Error getting file from GitHub: {str(e)}")
            return None

    def push_file_to_github(self, file_path, content, commit_message=None):
        """
        Push a file to GitHub repository.

        Args:
            file_path (str): Path to the file in the repository
            content (str): Content of the file
            commit_message (str, optional): Commit message. Defaults to None.

        Returns:
            tuple: (success, message)
        """
        try:
            self.logger.info(f"Pushing file to GitHub: {file_path}")

            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            # Convert Windows path to GitHub path format
            github_path = file_path.replace('\\', '/')
            self.logger.info(f"GitHub path: {github_path}")

            # Get the file from GitHub to check if it exists and get its SHA
            file_data = self.get_file_from_github(github_path)
            if file_data:
                self.logger.info(f"File exists in GitHub repository: {github_path}")
            else:
                self.logger.info(f"File does not exist in GitHub repository: {github_path} (will be created)")

            # Encode content to base64
            content_bytes = content.encode('utf-8')
            base64_content = base64.b64encode(content_bytes).decode('utf-8')

            # Prepare request data
            data = {
                'message': commit_message or f'Update {os.path.basename(file_path)} - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                'content': base64_content,
                'branch': self.branch
            }

            # If file exists, include its SHA
            if file_data:
                data['sha'] = file_data['sha']

            # API call to create or update file
            url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{github_path}'
            response = requests.put(url, headers=headers, json=data)

            if response.status_code in [200, 201]:
                return True, f"Successfully pushed {os.path.basename(file_path)} to GitHub"
            else:
                error_msg = response.json().get('message', 'Unknown error')
                error_details = response.json().get('documentation_url', '')
                self.logger.error(f"Error pushing file to GitHub: {error_msg} - {error_details}")
                return False, f"Error pushing file to GitHub: {error_msg} - {error_details}"

        except Exception as e:
            self.logger.error(f"Error pushing file to GitHub: {str(e)}")
            return False, f"Error pushing file to GitHub: {str(e)}"

    def delete_file_from_github(self, file_path, commit_message=None):
        """
        Delete a file from GitHub repository.

        Args:
            file_path (str): Path to the file in the repository
            commit_message (str, optional): Commit message. Defaults to None.

        Returns:
            tuple: (success, message)
        """
        try:
            self.logger.info(f"Deleting file from GitHub: {file_path}")

            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            # Convert Windows path to GitHub path format
            github_path = file_path.replace('\\', '/')
            self.logger.info(f"GitHub path: {github_path}")

            # Get the file from GitHub to check if it exists and get its SHA
            file_data = self.get_file_from_github(github_path)

            if not file_data:
                self.logger.warning(f"File not found in GitHub repository: {github_path}")
                return False, f"File {os.path.basename(file_path)} not found in GitHub repository"

            self.logger.info(f"File found in GitHub repository: {github_path}, SHA: {file_data['sha']}")

            # Prepare request data
            data = {
                'message': commit_message or f'Delete {os.path.basename(file_path)} - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                'sha': file_data['sha'],
                'branch': self.branch
            }

            # API call to delete file
            url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{github_path}'
            response = requests.delete(url, headers=headers, json=data)

            if response.status_code == 200:
                return True, f"Successfully deleted {os.path.basename(file_path)} from GitHub"
            else:
                error_msg = response.json().get('message', 'Unknown error')
                error_details = response.json().get('documentation_url', '')
                self.logger.error(f"Error deleting file from GitHub: {error_msg} - {error_details}")
                return False, f"Error deleting file from GitHub: {error_msg} - {error_details}"

        except Exception as e:
            self.logger.error(f"Error deleting file from GitHub: {str(e)}")
            return False, f"Error deleting file from GitHub: {str(e)}"

    def push_all_question_files(self):
        """
        Push all question files to GitHub.

        Returns:
            tuple: (success_count, failed_count, messages)
        """
        success_count = 0
        failed_count = 0
        messages = []

        try:
            # Get all JSON files in the questions directory
            json_files = [f for f in os.listdir(self.questions_dir) if f.endswith('.json')]

            self.logger.info(f"Starting push_all_question_files operation. Found {len(json_files)} JSON files.")

            if not json_files:
                self.logger.warning("No question files found in the questions directory")
                return 0, 0, ["No question files found in the questions directory"]

            for file_name in json_files:
                file_path = os.path.join(self.questions_dir, file_name)

                try:
                    # Read the file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Push the file to GitHub using the correct path from issue description
                    github_file_path = f'contents/questions/{file_name}'
                    success, message = self.push_file_to_github(github_file_path, content)

                    # If the first path fails, try with a different path
                    if not success and "Not Found" in message:
                        self.logger.info(f"File not found at {github_file_path}, trying alternative path")
                        github_file_path = f'questions/{file_name}'
                        success, message = self.push_file_to_github(github_file_path, content)

                    if success:
                        success_count += 1
                    else:
                        failed_count += 1

                    messages.append(message)

                except Exception as e:
                    failed_count += 1
                    error_msg = f"Error processing file {file_name}: {str(e)}"
                    self.logger.error(error_msg)
                    messages.append(error_msg)

            return success_count, failed_count, messages

        except Exception as e:
            self.logger.error(f"Error pushing question files to GitHub: {str(e)}")
            return 0, 0, [f"Error pushing question files to GitHub: {str(e)}"]

    def get_github_question_files(self):
        """
        Get a list of question files from GitHub repository.

        Returns:
            list: List of file names in the GitHub repository
        """
        try:
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }

            # API call to get directory contents using the correct path from issue description
            # The correct path is: https://github.com/uae2000uae/Avirta-WebApp/tree/Avirta-1/contents/questions
            url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/contents/questions?ref={self.branch}'
            self.logger.info(f"Getting question files from GitHub: {url}")
            response = requests.get(url, headers=headers)

            # If the first URL fails, try with a different path (without 'contents/' prefix)
            if response.status_code == 404:
                self.logger.info("Directory not found, trying alternative path without 'contents/' prefix")
                url = f'https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/questions?ref={self.branch}'
                self.logger.info(f"Getting question files from GitHub (alternative path): {url}")
                response = requests.get(url, headers=headers)

            # Log the response for debugging
            if response.status_code != 200:
                self.logger.error(f"GitHub API response: {response.status_code} - {response.text}")

            if response.status_code == 200:
                files = response.json()
                json_files = [file['name'] for file in files if file['type'] == 'file' and file['name'].endswith('.json')]
                self.logger.info(f"Successfully retrieved {len(json_files)} JSON files from GitHub repository")
                return json_files
            else:
                error_msg = response.json().get('message', 'Unknown error')
                self.logger.error(f"Error getting question files from GitHub: {error_msg}")
                return []

        except Exception as e:
            self.logger.error(f"Error getting question files from GitHub: {str(e)}")
            return []

    def sync_question_files(self):
        """
        Synchronize question files between local directory and GitHub repository.
        This will:
        1. Push new or updated local files to GitHub
        2. Delete files from GitHub that don't exist locally

        Returns:
            tuple: (success_count, failed_count, messages)
        """
        success_count = 0
        failed_count = 0
        messages = []

        try:
            # Get local question files
            local_files = [f for f in os.listdir(self.questions_dir) if f.endswith('.json')]
            self.logger.info(f"Starting sync_question_files operation. Found {len(local_files)} local JSON files.")

            # Get GitHub question files
            github_files = self.get_github_question_files()
            self.logger.info(f"Found {len(github_files)} JSON files in GitHub repository.")

            # Push new or updated local files to GitHub
            for file_name in local_files:
                file_path = os.path.join(self.questions_dir, file_name)

                try:
                    # Read the file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Push the file to GitHub using the correct path from issue description
                    github_file_path = f'contents/questions/{file_name}'
                    success, message = self.push_file_to_github(github_file_path, content)

                    # If the first path fails, try with a different path
                    if not success and "Not Found" in message:
                        self.logger.info(f"File not found at {github_file_path}, trying alternative path")
                        github_file_path = f'questions/{file_name}'
                        success, message = self.push_file_to_github(github_file_path, content)

                    if success:
                        success_count += 1
                    else:
                        failed_count += 1

                    messages.append(message)

                except Exception as e:
                    failed_count += 1
                    error_msg = f"Error processing file {file_name}: {str(e)}"
                    self.logger.error(error_msg)
                    messages.append(error_msg)

            # Delete files from GitHub that don't exist locally
            for file_name in github_files:
                if file_name not in local_files:
                    try:
                        # Delete the file from GitHub using the correct path from issue description
                        github_file_path = f'contents/questions/{file_name}'
                        success, message = self.delete_file_from_github(github_file_path)

                        # If the first path fails, try with a different path
                        if not success and "not found" in message.lower():
                            self.logger.info(f"File not found at {github_file_path}, trying alternative path")
                            github_file_path = f'questions/{file_name}'
                            success, message = self.delete_file_from_github(github_file_path)

                        if success:
                            success_count += 1
                        else:
                            failed_count += 1

                        messages.append(message)

                    except Exception as e:
                        failed_count += 1
                        error_msg = f"Error deleting file {file_name} from GitHub: {str(e)}"
                        self.logger.error(error_msg)
                        messages.append(error_msg)

            return success_count, failed_count, messages

        except Exception as e:
            self.logger.error(f"Error synchronizing question files with GitHub: {str(e)}")
            return 0, 0, [f"Error synchronizing question files with GitHub: {str(e)}"]
