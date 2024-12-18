import logging

logging.basicConfig(level=logging.INFO)

def greet(name):
    logging.info(f"Greeting user: {name}")
    logging.info(f"Hello, {name}!")

def calculate_sum(numbers):
    logging.info(f"Calculating sum of numbers: {numbers}")
    return sum(numbers)

if __name__ == "__main__":
    greet("World")
    result = calculate_sum([1, 2, 3, 4, 5])
    logging.info(f"Sum result: {result}")