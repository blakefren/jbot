from cfg.main import ConfigReader
from twilio.rest import Client


class MessagingBot:
    """
    A Python library for sending Jeopardy! questions and answers via SMS using Twilio.
    """

    def __init__(self, account_sid=None, auth_token=None, twilio_phone_number=None):
        """
        Initializes the JeopardySMSBot with Twilio credentials.

        Args:
            account_sid (str, optional): Your Twilio Account SID. Defaults to
                                         TWILIO_ACCOUNT_SID environment variable.
            auth_token (str, optional): Your Twilio Auth Token. Defaults to
                                        TWILIO_AUTH_TOKEN environment variable.
            twilio_phone_number (str, optional): Your Twilio phone number (e.g., "+15017122661").
                                                 Defaults to TWILIO_PHONE_NUMBER environment variable.
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.twilio_phone_number = twilio_phone_number
        assert self.account_sid is not None, "Twilio Account SID must be provided."
        assert self.auth_token is not None, "Twilio Auth Token must be provided."
        assert (
            self.twilio_phone_number is not None
        ), "Twilio Phone Number must be provided."
        self.client = Client(self.account_sid, self.auth_token)

    def _send_message(self, receivers, message_body):
        raise notImplementedError(
            "Implement this method in a subclass to send messages."
        )

    def send_question(self, to_phone_number, category, value, question):
        """
        Sends a Jeopardy! question to a specified phone number.

        Args:
            to_phone_number (str): The recipient's phone number.
            category (str): The category of the Jeopardy! question.
            value (int or str): The point value of the question.
            question (str): The Jeopardy! question text.
        """
        message_body = f"Jeopardy! Question:\nCategory: {category}\nValue: ${value}\nQuestion: {question}"
        print(f"Attempting to send question to {to_phone_number}...")
        self._send_sms(to_phone_number, message_body)

    def send_answer(self, to_phone_number, category, value, question, answer):
        """
        Sends the answer to a Jeopardy! question to a specified phone number.

        Args:
            to_phone_number (str): The recipient's phone number.
            category (str): The category of the Jeopardy! question.
            value (int or str): The point value of the question.
            question (str): The original Jeopardy! question text.
            answer (str): The correct answer to the question.
        """
        message_body = (
            f"Jeopardy! Answer Time!\n"
            f"Category: {category}\n"
            f"Value: ${value}\n"
            f"Question: {question}\n"
            f"Correct Answer: {answer}"
        )
        print(f"Attempting to send answer to {to_phone_number}...")
        self._send_sms(to_phone_number, message_body)

    def recieve_guesses(self, to_phone_number, guess):
        """
        Parses a player's guess and saves it for later.

        Args:
            to_phone_number (str): The recipient's phone number.
            guess (str): The player's guess.
        """
        # TODO


class SMSBot(MessagingBot):
    """
    A subclass of MessagingBot that implements the _send_message method to send SMS messages using Twilio.
    """

    def _send_sms(self, to_phone_number, message_body):
        """
        Sends an SMS message using Twilio.

        Args:
            to_phone_number (str): The recipient's phone number.
            message_body (str): The body of the SMS message.
        """
        try:
            message = self.client.messages.create(
                body=message_body, from_=self.twilio_phone_number, to=to_phone_number,
            )
            print(f"Message sent successfully: {message.sid}")
        except Exception as e:
            print(f"Failed to send message: {e}")
