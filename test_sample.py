def greet(name: str, greeting: str = 'Hello') -> None:
    """
    Print a greeting message to the specified person.
    
    Args:
        name: The name of the person to greet
        greeting: The greeting to use (default is 'Hello')
    """
    print(f'{greeting}, {name}!')