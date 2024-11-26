import logging

from utils import format_name, validate_age

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def greet(name):
    logger.info(f"Greeting user: {name}")
    print(f"Hello, {name}!")

def calculate_sum(numbers):
    logger.debug(f"Calculating sum of numbers: {numbers}")
    result = sum(numbers)
    logger.info(f"Sum calculated: {result}")
    return result

def process_user(user_data):
    """Process user data and return formatted string"""
    name = format_name(user_data["name"])
    age = validate_age(user_data["age"])
    return f"{name} is {age} years old"

def format_name(name):
    """Format name by stripping whitespace and converting to title case"""
    logger.debug(f"Formatting name: {name}")
    return name.strip().title()

def validate_age(age):
    """Validate age is an integer between 0 and 150"""
    logger.debug(f"Validating age: {age}")
    if not isinstance(age, int):
        logger.error("Age must be an integer")
        raise TypeError("Age must be an integer")
    if age < 0 or age > 150:
        logger.error("Age must be between 0 and 150")
        raise ValueError("Age must be between 0 and 150")
    return age

if __name__ == "__main__":
    greet("World")
    print(calculate_sum([1, 2, 3, 4, 5]))
    
    test_data = {
        "name": "john doe",
        "age": 25
    }
    logger.info(process_user(test_data))