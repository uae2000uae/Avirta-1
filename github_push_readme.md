# GitHub Push Functionality

This document explains how to use the GitHub push functionality in the Avirta project.

## Overview

The `push_to_github` function allows you to automatically push JSON files from your local Avirta instance to a GitHub repository. This is useful for backing up question files or sharing them with others.

## Configuration

The function requires the following configuration:

1. **GitHub Token**: A personal access token with repository write permissions
2. **Repository Owner**: Your GitHub username or organization name
3. **Repository Name**: The name of the repository to push to
4. **Local Folder**: The local folder containing the files to push (default: 'contents/questions')
5. **Branch**: The branch to push to (default: 'main')

These can be set as environment variables or in the Flask app configuration.

## Setting Up GitHub Token

1. Go to your GitHub account settings
2. Navigate to Developer settings > Personal access tokens
3. Click "Generate new token"
4. Give it a descriptive name and select the "repo" scope
5. Click "Generate token" and copy the token

## Using the Function

### Via Web Interface

The function is exposed as a POST endpoint at `/update_json`. You can trigger it by sending a POST request to this endpoint.

### Via Test Script

1. Edit the `test_github_push.py` file to set your GitHub token, repository owner, repository name, and other configuration
2. Run the script using `python test_github_push.py` or by executing the `test_github_push.bat` file

## Troubleshooting

### Common Issues

1. **"GitHub token not configured"**: Make sure you've set a valid GitHub token
2. **"Repository information not configured"**: Make sure you've set the repository owner and name
3. **"Local folder not found"**: Make sure the local folder exists and contains the files you want to push

### Rate Limiting

The GitHub API has rate limits. The function includes a 1-second delay between requests to avoid hitting these limits.

## Security Considerations

- Never commit your GitHub token to version control
- Use environment variables or secure configuration management for sensitive information
- Consider using a dedicated GitHub account or token with limited permissions for automated operations