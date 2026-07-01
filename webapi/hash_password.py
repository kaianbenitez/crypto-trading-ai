"""Run once to generate WEBAPI_PASSWORD_HASH for your .env.
Usage: py webapi/hash_password.py
"""
import getpass
from webapi.auth import hash_password

if __name__ == "__main__":
    pw = getpass.getpass("Choose a dashboard password: ")
    print("\nAdd this to your .env file:")
    print(f"WEBAPI_PASSWORD_HASH={hash_password(pw)}")
