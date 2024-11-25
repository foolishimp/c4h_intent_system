import logging

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

if __name__ == "__main__":
    greet("World")
    print(calculate_sum([1, 2, 3, 4, 5]))