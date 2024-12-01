```python
import logging

from utils import format_name, validate_age

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_user(user_data):
    """Process user data and return formatted string"""
    logger.debug(f"Processing user data: {user_data}")
    name = format_name(user_data["name"])
    age = validate_age(user_data["age"])
    result = f"{name} is {age} years old"
    logger.debug(f"Processed result: {result}")
    return result

if __name__ == "__main__":
    test_data = {
        "name": "john doe",
        "age": 25
    }
    logger.info(process_user(test_data))
```