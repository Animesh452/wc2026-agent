from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db = client["wc2026"]
db["users"].insert_one({"test": "connected"})
print("MongoDB working:", db["users"].find_one({"test": "connected"}))
db["users"].delete_many({"test": "connected"})