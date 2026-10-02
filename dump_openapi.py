import json
from web.app import app

with open("openapi.json", "w") as f:
    json.dump(app.openapi(), f, indent=2)
