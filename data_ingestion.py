import json
from pydantic import ValidationError
from data_schema import CallRecordSchema

def validate_call_record(file_path: str):
    """
    Loads a call.json file from disk and validates it against 
    the CallRecordSchema Pydantic model.
    """
    # Open and parse the JSON file contents
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    try:
        # Pass raw dictionary into Pydantic for validation and type casting
        validated_record = CallRecordSchema(**raw_data)
        print(f"Successfully validated call ID: {validated_record.call_id}")
        return validated_record
        
    except ValidationError as e:
        # Catch and report any structural or type mismatches
        print(f"Schema validation failed: {e}")
        raise