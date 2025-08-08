import unittest
from unittest.mock import Mock
from bot.subscriber import Subscriber

class TestSubscriber(unittest.TestCase):
    def test_init(self):
        s = Subscriber(123, "test_user", False)
        self.assertEqual(s.id, 123)
        self.assertEqual(s.display_name, "test_user")
        self.assertFalse(s.is_channel)
        self.assertIsNone(s.ctx)

    def test_hash(self):
        s1 = Subscriber(123, "test_user", False)
        s2 = Subscriber(123, "test_user", False)
        self.assertEqual(hash(s1), hash(s2))

    def test_eq(self):
        s1 = Subscriber(123, "test_user", False)
        s2 = Subscriber(123, "test_user", False)
        s3 = Subscriber(456, "another_user", True)
        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)

    def test_from_ctx_user(self):
        mock_ctx = Mock()
        mock_ctx.guild = None
        mock_ctx.author.id = 456
        mock_ctx.author.display_name = "test_author"
        
        s = Subscriber.from_ctx(mock_ctx)
        
        self.assertEqual(s.id, 456)
        self.assertEqual(s.display_name, "test_author")
        self.assertFalse(s.is_channel)
        self.assertEqual(s.ctx, mock_ctx)

    def test_from_ctx_channel(self):
        mock_ctx = Mock()
        mock_ctx.guild.id = 789
        mock_ctx.channel.id = 123
        mock_ctx.author.display_name = "test_author_channel"
        
        s = Subscriber.from_ctx(mock_ctx)
        
        self.assertEqual(s.id, 123)
        self.assertEqual(s.display_name, "test_author_channel")
        self.assertTrue(s.is_channel)
        self.assertEqual(s.ctx, mock_ctx)

    def test_to_csv_row(self):
        s = Subscriber(123, "csv_user", True)
        self.assertEqual(s.to_csv_row(), [123, "csv_user", True])

    def test_from_csv_row(self):
        row = ["789", "csv_user_2", "False"]
        s = Subscriber.from_csv_row(row)
        self.assertEqual(s.id, 789)
        self.assertEqual(s.display_name, "csv_user_2")
        self.assertFalse(s.is_channel)

    def test_from_csv_row_true(self):
        row = ["987", "csv_user_3", "True"]
        s = Subscriber.from_csv_row(row)
        self.assertEqual(s.id, 987)
        self.assertEqual(s.display_name, "csv_user_3")
        self.assertTrue(s.is_channel)

if __name__ == '__main__':
    unittest.main()
