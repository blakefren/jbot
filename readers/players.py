import csv
import re


def read_and_validate_contacts(csv_filepath: str):
    """
    Reads a CSV file containing phone numbers, first names, and last names,
    validates the data, and returns a list of valid contact dictionaries.

    Args:
        csv_filepath (str): The path to the CSV file.

    Returns:
        list: A list of dictionaries, where each dictionary represents a valid contact.
    """
    valid_contacts = []
    # Regex for a common North American phone number format: +1XXXXXXXXXX
    phone_number_pattern = re.compile(r"^\+1[\d]{10}$")

    try:
        with open(csv_filepath, mode="r", newline="", encoding="utf-8") as file:
            # Use DictReader to access columns by their header names
            reader = csv.DictReader(file)

            # Check if required headers exist
            required_headers = ["firstname", "lastname", "phone_number", "discord_id"]
            if not all(header in reader.fieldnames for header in required_headers):
                print(
                    f"Error: CSV file must contain all required headers: {', '.join(required_headers)}"
                )
                return []

            for i, row in enumerate(reader):
                row_num = i + 2  # +2 because of 0-indexing and header row
                firstname = row.get("firstname", "").strip()
                lastname = row.get("lastname", "").strip()
                phone_number = row.get("phone_number", "").strip()
                discord_id = row.get("discord_id", "").strip()

                is_valid_row = True

                # 1. Validate Phone Number
                if not phone_number and not discord_id:
                    print(
                        f"Warning: Row {row_num}: contact info is missing. Skipping row."
                    )
                    is_valid_row = False
                elif not phone_number_pattern.match(phone_number):
                    print(
                        f"Warning: Row {row_num}: Invalid phone number format '{phone_number}'. Skipping row."
                    )
                    is_valid_row = False

                # 2. Validate First Name
                if not firstname:
                    print(
                        f"Warning: Row {row_num}: First name is missing. Using 'Unknown'."
                    )
                    firstname = "Unknown"
                elif (
                    not firstname.isalpha()
                ):  # Check if it contains only alphabetic characters
                    print(
                        f"Warning: Row {row_num}: First name '{firstname}' contains non-alphabetic characters. Sanitizing."
                    )
                    firstname = "".join(
                        filter(str.isalpha, firstname)
                    )  # Remove non-alphabetic characters
                    if not firstname:  # If sanitization results in empty string
                        firstname = "Unknown"

                # 3. Validate Last Name
                if not lastname:
                    print(
                        f"Warning: Row {row_num}: Last name is missing. Using 'Unknown'."
                    )
                    lastname = "Unknown"
                elif (
                    not lastname.isalpha()
                ):  # Check if it contains only alphabetic characters
                    print(
                        f"Warning: Row {row_num}: Last name '{lastname}' contains non-alphabetic characters. Sanitizing."
                    )
                    lastname = "".join(
                        filter(str.isalpha, lastname)
                    )  # Remove non-alphabetic characters
                    if not lastname:  # If sanitization results in empty string
                        lastname = "Unknown"

                if is_valid_row:
                    valid_contacts.append(
                        {
                            "firstname": firstname,
                            "lastname": lastname,
                            "phone_number": phone_number,
                            "discord_id": discord_id,
                        }
                    )
    except FileNotFoundError:
        print(f"Error: The file '{csv_filepath}' was not found.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return valid_contacts
