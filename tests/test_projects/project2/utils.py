import logging

logging.basicConfig(level=logging.INFO)

def format_name(name):
    """Format name by stripping whitespace and converting to title case"""
    logging.info(f"Formatting name: {name}")
    return name.strip().title()

def validate_age(age):
    """Validate age is an integer between 0 and 150"""
    logging.info(f"Validating age: {age}")
    if not isinstance(age, int):
        raise TypeError("Age must be an integer")
    if age < 0 or age > 150:
        raise ValueError("Age must be between 0 and 150")
    return age