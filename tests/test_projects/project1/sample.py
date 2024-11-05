import logging

logging.basicConfig(level=logging.INFO)

def greet(name):
    logging.info(f"Greeting: {name}")
    print(f"Hello, {name}!")

def calculate_sum(numbers):
    logging.info(f"Calculating sum: {numbers}")
    return sum(numbers)

if __name__ == "__main__":
    greet("World")
    print(calculate_sum([1, 2, 3, 4, 5]))