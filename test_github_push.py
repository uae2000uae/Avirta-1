import os
import sys
import json
from flask import Flask, jsonify

# Create a Flask app for testing
app = Flask(__name__)

# Set necessary environment variables for testing
# Replace these with your actual values or use environment variables
os.environ['GITHUB_TOKEN'] = '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'  # Replace with your actual token
os.environ['REPO_OWNER'] = 'uae2000uae'  # Replace with your GitHub username
os.environ['REPO_NAME'] = 'Avirta-WebApp'  # Replace with your repository name
os.environ['LOCAL_FOLDER'] = 'contents/questions'  # Path to your questions folder
os.environ['BRANCH'] = 'Avirta-1.1.4'  # Branch to push to, default is 'main'

print("Configuration:")
print(f"- Repository: {os.environ['REPO_OWNER']}/{os.environ['REPO_NAME']}")
print(f"- Local folder: {os.environ['LOCAL_FOLDER']}")
print(f"- Branch: {os.environ['BRANCH']}")
print(f"- GitHub token: {'Configured' if os.environ['GITHUB_TOKEN'] != 'your_github_token' else 'NOT CONFIGURED - Please update'}")
print()

# Import the push_to_github function from app.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import push_to_github

# Test the function within the Flask app context
with app.app_context():
    print("Testing push_to_github function...")
    try:
        # Call the function
        response = push_to_github()

        # Convert response to a dictionary if it's a Flask response
        if hasattr(response, 'get_json'):
            result = response.get_json()
        else:
            # If it's a tuple (response, status_code)
            if isinstance(response, tuple) and len(response) == 2:
                result = response[0].get_json() if hasattr(response[0], 'get_json') else response[0]
                status_code = response[1]
                print(f"Status code: {status_code}")
            else:
                result = response

        # Pretty print the result
        print("Result:")
        print(json.dumps(result, indent=2))

        # Check if there was an error
        if isinstance(result, dict) and 'error' in result:
            print(f"Error: {result['error']}")
            if 'GitHub token not configured' in result.get('error', ''):
                print("\nNOTE: You need to set a valid GitHub token in the script or environment variables.")
            sys.exit(1)

        # Check results
        if isinstance(result, dict) and 'results' in result:
            success_count = sum(1 for item in result['results'] 
                              for file_data in item.values() 
                              if file_data.get('status') == 'success')
            error_count = sum(1 for item in result['results'] 
                            for file_data in item.values() 
                            if file_data.get('status') == 'error')

            print(f"\nSummary: {success_count} files successfully pushed, {error_count} errors")

            # Print errors if any
            if error_count > 0:
                print("\nErrors:")
                for item in result['results']:
                    for filename, file_data in item.items():
                        if file_data.get('status') == 'error':
                            print(f"  {filename}: {file_data.get('message', 'Unknown error')}")

        print("\nTest completed successfully!")

    except Exception as e:
        print(f"Error testing push_to_github: {str(e)}")
        sys.exit(1)
