import json
import os
import sys

def convert_json_file(file_path):
    """
    Convert a JSON file with Unicode escapes to normal text.
    
    Args:
        file_path (str): Path to the JSON file
        
    Returns:
        bool: True if conversion was successful, False otherwise
    """
    try:
        # Read the file
        with open(file_path, 'r', encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON in {file_path}: {e}")
                return False
        
        # Write it back with ensure_ascii=False
        with open(file_path, 'w', encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        print(f"Error converting {file_path}: {e}")
        return False

def find_and_convert_json_files(directory):
    """
    Find all JSON files in a directory and its subdirectories and convert them.
    
    Args:
        directory (str): Directory to search in
        
    Returns:
        tuple: (total_files, successful_conversions)
    """
    total_files = 0
    successful_conversions = 0
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.json'):
                total_files += 1
                file_path = os.path.join(root, file)
                print(f"Converting {file_path}...")
                
                if convert_json_file(file_path):
                    successful_conversions += 1
                    print(f"Successfully converted {file_path}")
                else:
                    print(f"Failed to convert {file_path}")
    
    return total_files, successful_conversions

if __name__ == "__main__":
    # Get directory from command line argument or use current directory
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    
    print(f"Converting JSON files in {directory}...")
    total, successful = find_and_convert_json_files(directory)
    
    print(f"\nConversion complete.")
    print(f"Total JSON files: {total}")
    print(f"Successfully converted: {successful}")
    print(f"Failed: {total - successful}")