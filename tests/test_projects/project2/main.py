from utils import format_name, validate_age
import logging

logging.basicConfig(level=logging.INFO)

def process_user(user_data):
    """Process user data and return formatted string"""
    logging.info(f"Processing user data: {user_data}")
    name = format_name(user_data["name"])
    age = validate_age(user_data["age"])
    return f"{name} is {age} years old"

if __name__ == "__main__":
    test_data = {
        "name": "john doe",
        "age": 25
    }
    print(process_user(test_data))