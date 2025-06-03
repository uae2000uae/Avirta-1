import json
import os

def test_json_write_read():
    """Test writing and reading Arabic text in JSON files."""
    print("Testing JSON write/read with Arabic text...")
    
    # Sample data with Arabic text
    data = {
        "arabic_text": "هذا نص عربي للاختبار",
        "mixed_text": "This is English with Arabic: مرحبا بالعالم",
        "nested": {
            "arabic_key": "مفتاح",
            "arabic_value": "قيمة"
        },
        "list_with_arabic": ["عنصر١", "عنصر٢", "عنصر٣"]
    }
    
    # Write to file
    test_file = "arabic_test.json"
    with open(test_file, 'w', encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Data written to {test_file}")
    
    # Read from file
    with open(test_file, 'r', encoding="utf-8") as f:
        loaded_data = json.load(f)
    
    print("Data read from file:")
    print(json.dumps(loaded_data, indent=2, ensure_ascii=False))
    
    # Verify data is the same
    if loaded_data == data:
        print("SUCCESS: Data read matches data written")
    else:
        print("ERROR: Data read does not match data written")
    
    # Clean up
    os.remove(test_file)
    print(f"Removed test file: {test_file}")

if __name__ == "__main__":
    test_json_write_read()