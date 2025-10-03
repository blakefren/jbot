class Subscriber:
    """
    Represents a subscriber to the trivia bot, which can be a user or a channel.
    """

    def __init__(self, sub_id, display_name, is_channel, ctx=None):
        self.sub_id = sub_id
        self.display_name = display_name
        self.is_channel = is_channel
        self.ctx = ctx

    def __hash__(self):
        return hash(self.sub_id)

    def __eq__(self, other):
        return isinstance(other, Subscriber) and self.sub_id == other.sub_id

    @classmethod
    def from_ctx(cls, ctx):
        _id = ctx.channel.id if ctx.guild else ctx.author.id
        display_name = ctx.author.display_name
        is_channel = ctx.guild is not None
        return cls(_id, display_name, is_channel, ctx=ctx)

    def to_csv_row(self):
        return [self.sub_id, self.display_name, self.is_channel]

    @classmethod
    def from_csv_row(cls, row):
        # row is a list of strings [id, display_name, is_channel]
        _id = int(row[0])
        display_name = row[1]
        is_channel = row[2].lower() == "true"
        return cls(_id, display_name, is_channel)
