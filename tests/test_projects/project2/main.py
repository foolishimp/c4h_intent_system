from utils import format_name

def process_user(user_data):
    name = format_name(user_data["name"])
    age = user_data["age"]
    return f"{name} is {age} years old"
# Continue creating test project2 files
cat > tests/test_projects/project2/utils.py << 'EOF'
def format_name(name):
    return name.strip().title()

def validate_age(age):
    if not isinstance(age, int):
        raise TypeError("Age must be an integer")
    if age < 0 or age > 150:
        raise ValueError("Age must be between 0 and 150")
    return age
