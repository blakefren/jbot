class Subscriber:
    """
    Represents a subscriber to the trivia bot, which can be a user or a channel.
    """

    def __init__(self, sub_id, display_name, is_channel):
        self.sub_id = int(sub_id)
        self.display_name = display_name
        self.is_channel = is_channel

    def __hash__(self):
        return hash(self.sub_id)

    def __eq__(self, other):
        return isinstance(other, Subscriber) and self.sub_id == other.sub_id
