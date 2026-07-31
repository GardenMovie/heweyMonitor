import os
import sys

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

from onboarding import populate_specifications

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]

if __name__ == "__main__":
    client = MongoClient(MONGO_URI, server_api=ServerApi("1"))
    try:
        populate_specifications(client)
        print("\nSpecifications updated.")
    except Exception as e:  # noqa: BLE001
        print(f"\nFailed to update specifications: {e}")
        sys.exit(1)
    finally:
        client.close()
