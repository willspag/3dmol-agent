from app import app, socketio

# Load environment variables
from dotenv import load_dotenv

load_dotenv(override=True)


# Configuration for Gunicorn workers
# This is used when the app runs in production with Gunicorn
class GunicornConfig:
    bind = "0.0.0.0:5000"
    workers = 1  # Use a single worker to avoid multiple Socket.IO servers
    worker_class = "sync"  # Default worker class
    timeout = 60  # Increased timeout to avoid worker timeouts (default is 30)
    keepalive = 5
    threads = 3
    preload_app = True  # Preload the app to avoid multiple Socket.IO servers
    reload = True  # Auto-reload on code changes
    loglevel = "info"


if __name__ == "__main__":
    socketio.run(app,
                 host="0.0.0.0",
                 port=5000,
                 debug=True,
                 allow_unsafe_werkzeug=True,
                 use_reloader=True,
                 log_output=True)
