import psutil
from datetime import datetime, timezone
import subprocess
import sys
import os
import json
import logging
import time
from collections import deque
import pymongo
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Database and collection names
DB_NAME = "Metrics"
COLLECTION_NAME = "hardwareMin"

COLLECTION_INTERVAL_SECONDS = 60

ID_LOG_PATH = os.path.join(os.path.dirname(__file__), "logs/insert_ids.json")
ID_LOG_MAXLEN = 100

SPOOL_PATH = os.path.join(os.path.dirname(__file__), "logs/spool.json")
SPOOL_MAXLEN = 100

def load_id_log():
    if os.path.exists(ID_LOG_PATH):
        with open(ID_LOG_PATH) as f:
            return deque(json.load(f), maxlen=ID_LOG_MAXLEN)
    return deque(maxlen=ID_LOG_MAXLEN)

def save_id_log(log):
    with open(ID_LOG_PATH, "w") as f:
        json.dump(list(log), f)

def metrics_to_json(metrics):
    doc = dict(metrics)
    doc["timestamp"] = doc["timestamp"].isoformat()
    return doc

def metrics_from_json(doc):
    metrics = dict(doc)
    metrics["timestamp"] = datetime.fromisoformat(metrics["timestamp"])
    return metrics

def load_spool():
    if os.path.exists(SPOOL_PATH):
        with open(SPOOL_PATH) as f:
            return deque((metrics_from_json(doc) for doc in json.load(f)), maxlen=SPOOL_MAXLEN)
    return deque(maxlen=SPOOL_MAXLEN)

def save_spool(samples):
    if samples:
        with open(SPOOL_PATH, "w") as f:
            json.dump([metrics_to_json(m) for m in samples], f)
    elif os.path.exists(SPOOL_PATH):
        os.remove(SPOOL_PATH)

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

def collect_metrics(hostname):
    metrics = {
        "timestamp": datetime.now(timezone.utc),
        "metadata": {
            "hostname": hostname,
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
    MONGO_URI = os.environ["MONGO_URI"]
    HOSTNAME = os.environ["HOSTNAME"]

    client = pymongo.MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]

    while True:
        cycle_start = time.monotonic()

        spooled = load_spool()
        if spooled:
            try:
                result = collection.insert_many(spooled)
                logger.info("Flushed %d spooled sample(s) from %s", len(result.inserted_ids), SPOOL_PATH)
                save_spool([])
            except Exception as e:
                logger.warning("Spool flush failed, will retry next cycle: %s", e)

        metrics = collect_metrics(HOSTNAME)
        try:
            result = collection.insert_one(metrics)
            logger.info("Inserted document with _id: %s at %s", result.inserted_id, metrics['timestamp'])
            id_log = load_id_log()
            id_log.append(str(result.inserted_id))
            save_id_log(id_log)
        except Exception as e:
            logger.error("MongoDB insert failed, spooling for retry: %s", e)
            spooled = load_spool()
            spooled.append(metrics)
            save_spool(spooled)

        elapsed = time.monotonic() - cycle_start
        time.sleep(max(0, COLLECTION_INTERVAL_SECONDS - elapsed))
