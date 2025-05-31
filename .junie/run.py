import os
import sys
import platform
import subprocess
import importlib.util

print("=== Avirta Application Runner ===")
print("This script will check for dependencies and run the Avirta application.")
print("Performing pre-flight checks...")

# Check Python version
print("Checking Python version...")
MIN_PYTHON_VERSION = (3, 8)
if sys.version_info < MIN_PYTHON_VERSION:
    print(f"Error: Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} or higher is required.")
    print(f"Current Python version: {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)
print(f"✓ Python version {sys.version_info.major}.{sys.version_info.minor} is compatible.")

# Get the absolute path to app.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
app_path = os.path.join(parent_dir, 'app.py')
venv_path = os.path.join(parent_dir, '.venv')
requirements_path = os.path.join(parent_dir, 'requirements.txt')

# Function to check if a module is installed
def is_module_installed(module_name):
    return importlib.util.find_spec(module_name) is not None

# Check for required dependencies
print("Checking required Python modules...")
required_modules = [
    'flask',  # Web framework
    'jinja2',  # Template engine
    'werkzeug',  # WSGI utility library
    'uuid',  # For generating unique IDs
    'datetime',  # For date/time handling
    'random',  # For random number generation
    'tempfile',  # For temporary file handling
    'json'  # For JSON handling
]
missing_modules = [module for module in required_modules if not is_module_installed(module)]
if not missing_modules:
    print("✓ All required Python modules are installed.")

# Determine the Python interpreter path based on the platform
print("Checking for virtual environment...")
if platform.system() == 'Windows':
    python_path = os.path.join(venv_path, 'Scripts', 'python.exe')
    pip_path = os.path.join(venv_path, 'Scripts', 'pip.exe')
    activate_cmd = os.path.join(venv_path, 'Scripts', 'activate.bat')
else:
    python_path = os.path.join(venv_path, 'bin', 'python')
    pip_path = os.path.join(venv_path, 'bin', 'pip')
    activate_cmd = f"source {os.path.join(venv_path, 'bin', 'activate')}"

# Check if the virtual environment Python exists
if os.path.exists(python_path):
    print(f"✓ Virtual environment found at: {venv_path}")
    print(f"✓ Using Python interpreter: {python_path}")
else:
    print("! Virtual environment not found or not activated.")
    print("! Falling back to system Python.")
    # Fall back to system Python
    python_path = 'python'
    pip_path = 'pip'

# Check for missing dependencies
if missing_modules:
    print(f"Warning: The following required modules are missing: {', '.join(missing_modules)}")

    # Check if requirements.txt exists
    if os.path.exists(requirements_path):
        print(f"Found requirements.txt. Attempting to install all dependencies...")
        try:
            if os.path.exists(pip_path):
                subprocess.run([pip_path, 'install', '-r', requirements_path], check=True)
            else:
                subprocess.run(['pip', 'install', '-r', requirements_path], check=True)
            print("Successfully installed dependencies from requirements.txt")
        except subprocess.CalledProcessError:
            print("Failed to install dependencies from requirements.txt")
            print("Attempting to install just the required modules...")

            # Try to install missing modules individually
            for module in missing_modules:
                print(f"Installing {module}...")
                try:
                    if os.path.exists(pip_path):
                        subprocess.run([pip_path, 'install', module], check=True)
                    else:
                        subprocess.run(['pip', 'install', module], check=True)
                except subprocess.CalledProcessError:
                    print(f"Failed to install {module}")
    else:
        print("No requirements.txt found. Attempting to install just the required modules...")
        # Try to install missing modules individually
        for module in missing_modules:
            print(f"Installing {module}...")
            try:
                if os.path.exists(pip_path):
                    subprocess.run([pip_path, 'install', module], check=True)
                else:
                    subprocess.run(['pip', 'install', module], check=True)
            except subprocess.CalledProcessError:
                print(f"Failed to install {module}")

    # Check again after installation attempt
    still_missing = [module for module in required_modules if not is_module_installed(module)]
    if still_missing:
        print(f"Error: Could not install all required modules. Still missing: {', '.join(still_missing)}")
        print("Please install them manually:")
        print(f"cd {parent_dir}")
        if platform.system() == 'Windows':
            print(r".venv\Scripts\activate")
        else:
            print("source .venv/bin/activate")
        print(f"pip install {' '.join(still_missing)}")
        sys.exit(1)

# Check for required directories and files
print("Checking for required directories...")
required_dirs = [
    os.path.join(parent_dir, 'static'),
    os.path.join(parent_dir, 'templates'),
    os.path.join(parent_dir, 'contents')
]

missing_dirs = [d for d in required_dirs if not os.path.isdir(d)]
if missing_dirs:
    print(f"Error: The following required directories are missing: {', '.join(missing_dirs)}")
    print("Please make sure these directories exist before running the application.")
    sys.exit(1)
else:
    print("✓ All required directories exist.")

# Check if app.py exists
print("Checking for app.py...")
if not os.path.exists(app_path):
    print(f"Error: Could not find {app_path}")
    sys.exit(1)
print(f"✓ Found app.py at: {app_path}")

# All checks passed, ready to run
print("\n=== All checks passed! ===")
print("Starting Avirta application...\n")

# Execute app.py
print(f"Running app.py with Python interpreter: {python_path}")
try:
    # Check if app.py exists
    if not os.path.exists(app_path):
        print(f"Error: app.py not found at {app_path}")
        sys.exit(1)
    else:
        print(f"✓ Found app.py at: {app_path}")

    # Use subprocess.run instead of os.system for better error handling
    print("All checks passed. Starting application...")
    result = subprocess.run([python_path, app_path], check=True)
    print("\n=== Avirta application has stopped ===")
    print("The application has exited successfully.")
except subprocess.CalledProcessError as e:
    print(f"\nError: app.py exited with code {e.returncode}")
    print("This might be due to missing dependencies. Try activating the virtual environment and installing requirements:")
    print(f"cd {parent_dir}")
    if platform.system() == 'Windows':
        print(r".venv\Scripts\activate")
    else:
        print("source .venv/bin/activate")
    print("pip install -r requirements.txt")
    sys.exit(e.returncode)
except Exception as e:
    print(f"\nError: Failed to run app.py: {e}")
    sys.exit(1)
