import os
import asyncio
from datetime import datetime, timedelta
from pymongo import MongoClient
from tools.email_sender import send_match_reminder


async def reminder_worker():
    print("  [worker] starting reminder worker loop")
    iteration = 0
    while True:
        iteration += 1
        try:
            uri = os.getenv("MONGODB_URI", "").strip()
            if not uri:
                print(f"  [worker] iter {iteration}: no MONGODB_URI")
                await asyncio.sleep(60)
                continue

            client = MongoClient(uri)
            db = client["wc2026"]
            now = datetime.utcnow()

            pending = list(db["reminders"].find({
                "sent": False,
                "email": {"$exists": True, "$ne": None}
            }))
            print(f"  [worker] iter {iteration}: now={now.isoformat()}, found {len(pending)} pending reminders")

            for reminder in pending:
                try:
                    match_date_str = reminder.get("match_date", "")
                    if not match_date_str:
                        continue

                    try:
                        match_dt = datetime.fromisoformat(match_date_str.replace("Z", "+00:00").replace("+00:00", ""))
                    except ValueError as ve:
                        print(f"  [worker] could not parse date '{match_date_str}': {ve}")
                        continue

                    minutes_before = reminder.get("minutes_before", 60)
                    notify_at = match_dt - timedelta(minutes=minutes_before)
                    print(f"  [worker] reminder for {reminder['team']}: notify_at={notify_at.isoformat()}, now={now.isoformat()}")

                    if notify_at <= now <= notify_at + timedelta(minutes=2):
                        print(f"  [worker] FIRING email for {reminder['team']}")
                        result = send_match_reminder(
                            to_email=reminder["email"],
                            team=reminder["team"],
                            match_date=match_date_str,
                            minutes_before=minutes_before
                        )
                        if result.get("sent"):
                            db["reminders"].update_one(
                                {"_id": reminder["_id"]},
                                {"$set": {"sent": True, "sent_at": datetime.utcnow().isoformat()}}
                            )
                            print(f"  [worker] email sent and marked for {reminder['team']}")
                        else:
                            print(f"  [worker] email failed: {result.get('error')}")
                except Exception as e:
                    print(f"  [worker] reminder processing error: {e}")

            client.close()
        except Exception as e:
            print(f"  [worker] outer error: {e}")

        await asyncio.sleep(30)