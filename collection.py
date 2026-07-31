import psutil
from datetime import datetime, timezone
import subprocess
import sys
import os
import json
from collections import deque
import pymongo
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ["MONGO_URI"]
HOSTNAME = os.environ["HOSTNAME"]

# Database and collection names
DB_NAME = "Metrics"
COLLECTION_NAME = "hardwareMin"

ID_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs/insert_ids.json")
ID_LOG_MAXLEN = 100

def load_id_log():
    if os.path.exists(ID_LOG_PATH):
        with open(ID_LOG_PATH) as f:
            return deque(json.load(f), maxlen=ID_LOG_MAXLEN)
    return deque(maxlen=ID_LOG_MAXLEN)

def save_id_log(log):
    with open(ID_LOG_PATH, "w") as f:
        json.dump(list(log), f)

def ping_latency(host="8.8.8.8"):
    try:
        # Use 1 ping, wait max 2 seconds, output in ms
        result = subprocess.run([
            "ping", "-c", "1", "-W", "2", host
        ], capture_output=True, text=True)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "time=" in line:
                    # Extract the time=XX ms part
                    try:
                        return float(line.split("time=")[1].split()[0])
                    except Exception:
                        continue
        return None
    except Exception:
        return None

def collect_metrics():
    metrics = {
        "timestamp": datetime.now(timezone.utc),
        "metadata": {
            "hostname": HOSTNAME,
        },
        "fields": {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "ping_ms": ping_latency()
        },
    }
    return metrics

if __name__ == "__main__":
    metrics = collect_metrics()
    try:
        client = pymongo.MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        result = collection.insert_one(metrics)
        print(f"Inserted document with _id: {result.inserted_id} at {metrics['timestamp']}")
        id_log = load_id_log()
        id_log.append(str(result.inserted_id))
        save_id_log(id_log)
    except Exception as e:
        print(f"MongoDB insert failed: {e}")
