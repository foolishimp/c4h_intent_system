public class UserManager {
    public void createUser(String username, String email) {
        System.out.printf("Creating user with username: %s and email: %s%n", username, email);
        
        if (validateUser(username, email)) {
            System.out.printf("User %s validated successfully%n", username);
            saveUser(username, email);
        } else {
            System.out.printf("Error: Failed to validate user %s%n", username);
        }
    }
    
    private boolean validateUser(String username, String email) {
        System.out.printf("Validating user data for %s%n", username);
        if (username == null || email == null) {
            System.out.printf("Validation failed - null values detected%n");
            return false;
        }
        return true;
    }
    
    private void saveUser(String username, String email) {
        System.out.printf("Saving user %s to database%n", username);
        // Database operations here
        System.out.printf("Successfully saved user %s%n", username);
    }
}