import unittest
from unittest.mock import Mock, MagicMock
from bot.subscriber import Subscriber


class TestSubscriber(unittest.TestCase):
    def setUp(self):
        self.mock_db_conn = MagicMock()

    def test_init(self):
        s = Subscriber(123, "test_user", False, self.mock_db_conn)
        self.assertEqual(s.sub_id, 123)
        self.assertEqual(s.display_name, "test_user")
        self.assertFalse(s.is_channel)
        self.assertEqual(s.db_conn, self.mock_db_conn)

    def test_hash(self):
        s1 = Subscriber(123, "test_user", False, self.mock_db_conn)
        s2 = Subscriber(123, "test_user", False, self.mock_db_conn)
        self.assertEqual(hash(s1), hash(s2))

    def test_eq(self):
        s1 = Subscriber(123, "test_user", False, self.mock_db_conn)
        s2 = Subscriber(123, "test_user", False, self.mock_db_conn)
        s3 = Subscriber(456, "another_user", True, self.mock_db_conn)
        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)

    def test_save(self):
        s = Subscriber(123, "test_user", False, self.mock_db_conn)
        s.save()
        self.mock_db_conn.__enter__().execute.assert_called_once_with(
            "INSERT OR REPLACE INTO subscribers (id, display_name, is_channel) VALUES (?, ?, ?)",
            (123, "test_user", False),
        )

    def test_delete(self):
        s = Subscriber(123, "test_user", False, self.mock_db_conn)
        s.delete()
        self.mock_db_conn.__enter__().execute.assert_called_once_with(
            "DELETE FROM subscribers WHERE id = ?", (123,)
        )

    def test_get_all(self):
        mock_cursor = self.mock_db_conn.__enter__().execute.return_value
        mock_cursor.fetchall.return_value = [
            (123, "test_user_1", False),
            (456, "test_user_2", True),
        ]

        subscribers = Subscriber.get_all(self.mock_db_conn)

        self.assertEqual(len(subscribers), 2)
        self.assertEqual(subscribers[0].sub_id, 123)
        self.assertEqual(subscribers[1].sub_id, 456)
        self.assertTrue(subscribers[1].is_channel)



if __name__ == "__main__":
    unittest.main()
