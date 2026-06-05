"""Sample Python app for testing."""


def main():
    """Entry point."""
    print("Hello from fixture project")


class UserService:
    """Handles user operations."""

    def __init__(self, db):
        self.db = db

    def get_user(self, user_id: int) -> dict:
        """Fetch a user by ID."""
        return {"id": user_id, "name": "Test User"}


if __name__ == "__main__":
    main()
