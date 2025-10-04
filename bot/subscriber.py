class Subscriber:
    """
    Represents a subscriber to the trivia bot, which can be a user or a channel.
    """

    def __init__(self, sub_id, display_name, is_channel, db_conn):
        self.sub_id = sub_id
        self.display_name = display_name
        self.is_channel = is_channel
        self.db_conn = db_conn

    def __hash__(self):
        return hash(self.sub_id)

    def __eq__(self, other):
        return isinstance(other, Subscriber) and self.sub_id == other.sub_id

    def save(self):
        """Saves the subscriber to the database."""
        with self.db_conn.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO subscribers (id, display_name, is_channel) VALUES (?, ?, ?)",
                (self.sub_id, self.display_name, self.is_channel),
            )

    def delete(self):
        """Deletes the subscriber from the database."""
        with self.db_conn.get_conn() as conn:
            conn.execute("DELETE FROM subscribers WHERE id = ?", (self.sub_id,))

    @classmethod
    def get_all(cls, db_conn):
        """Gets all subscribers from the database."""
        rows = db_conn.execute_query("SELECT id, display_name, is_channel FROM subscribers")
        return {cls(row['id'], row['display_name'], row['is_channel'], db_conn) for row in rows}
