"""Check the private worker RPC and image availability, without executing a plugin."""
import json
from developer_worker.client import call

if __name__ == "__main__":
    print(json.dumps(call("GET", "/health")))
