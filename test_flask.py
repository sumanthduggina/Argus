# test_flask.py
from flask import Flask
import time

app = Flask(__name__)

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(port=5001, debug=False)