class Subscriber:
    """
    Represents a subscriber to the Jeopardy! bot, which can be a user or a channel.
    """
    def __init__(self, ctx):
        self.id = ctx.channel.id if ctx.guild else ctx.author.id
        self.display_name = ctx.author.display_name
        self.is_channel = ctx.guild is not None
        self.ctx = ctx

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other, Subscriber) and self.id == other.id
