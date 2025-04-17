import base64
import io
import os
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Configure logging for easier debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask and Socket.IO
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-key")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Keep track of connected viewer
_connected_sid: Optional[str] = None

# Store test results for retrieval
test_results: List[Dict[str, Any]] = []

# ────────────────────────────────  Routes  ──────────────────────────────────────
@app.route("/")
def index():
    """Serve the main page with 3D molecular viewer and test runner."""
    return render_template("index.html")

@app.route("/api/clear_test_results", methods=["POST"])
def clear_test_results():
    """Clear the test results."""
    global test_results
    test_results = []
    return jsonify({"status": "success"})

@app.route("/api/get_test_results")
def get_test_results():
    """Return the test results."""
    return jsonify(test_results)

# ────────────────────────────────  Socket events  ───────────────────────────────
@socketio.on("connect")
def _on_connect():
    global _connected_sid
    if _connected_sid is None:
        _connected_sid = request.sid
        logger.info(f"Client connected with SID: {_connected_sid}")
        emit("status", {"msg": "registered"})
    else:
        logger.warning(f"Connection refused: SID {request.sid}, already have {_connected_sid}")
        # Instead of refusing connection, we'll allow it but keep the first one as primary
        emit("status", {"msg": "viewer_only"})

@socketio.on("disconnect")
def _on_disconnect():
    global _connected_sid
    if request.sid == _connected_sid:
        logger.info(f"Primary client disconnected: {_connected_sid}")
        _connected_sid = None
    else:
        logger.info(f"Secondary client disconnected: {request.sid}")

# Command execution and test running
@socketio.on("command")
def handle_command(payload):
    """Execute a command in the 3D viewer and return the result."""
    logger.debug(f"Received command: {payload}")
    command_name = payload.get("name", "")
    
    # Record test result if this is a test
    if payload.get("is_test", False):
        record_test_result(command_name, payload)
    
    # For non-test commands, just return success
    return {"status": "success"}

@socketio.on("run_tests")
def run_tests():
    """Run the test suite and report results."""
    global test_results
    test_results = []
    
    # Tell the client to start running tests
    emit("start_tests")
    return {"status": "started"}

# ────────────────────────────────  Test helpers  ──────────────────────────────────
def record_test_result(test_name: str, data: Dict[str, Any]):
    """Add a test result to the results list."""
    result = {
        "name": test_name,
        "success": data.get("success", True),
        "image": data.get("image", ""),
        "details": data.get("details", ""),
        "timestamp": data.get("timestamp", "")
    }
    test_results.append(result)
    # Emit an event to notify about new test result
    socketio.emit("test_result", result)

# ────────────────────────────────  Python API  ──────────────────────────────────
# Custom implementation of a Socket.IO RPC call with response
def _call_viewer(command: str, **kwargs) -> bytes:
    """Internal helper that asks the viewer to run a command and returns a PNG."""
    if _connected_sid is None:
        raise RuntimeError("No browser viewer connected yet – open the app in a tab.")
    
    logger.info(f"Calling command '{command}' for SID: {_connected_sid}")
    payload: Dict[str, Any] = {"name": command, **kwargs}
    
    # Create an event to wait for the response
    response_event = threading.Event()
    response_data = {"result": None, "error": None}
    
    # Define a callback to handle the response
    def _on_response(data):
        response_data["result"] = data
        response_event.set()
    
    # Use a unique event ID for this request
    event_id = f"viewer_command_{time.time()}_{command}"
    
    # Register a one-time event handler for the response
    @socketio.on(event_id)
    def _handle_response(data):
        _on_response(data)
        return True  # Acknowledge receipt
    
    # Send the command to the client with the response event ID
    socketio.emit("command", {"payload": payload, "response_event": event_id}, to=_connected_sid)
    
    # Wait for response with timeout
    timeout = 15  # seconds
    if not response_event.wait(timeout=timeout):
        logger.error(f"Timeout waiting for response to {command}")
        return b""
    
    # Process the response
    try:
        result = response_data["result"]
        if isinstance(result, dict) and "img" in result:
            img64: str = result["img"].split(",", 1)[1]  # Drop data:image/png;base64,
            return base64.b64decode(img64)
        else:
            logger.error(f"No image in response: {result}")
            return b""
    except Exception as e:
        logger.error(f"Error processing response: {e}")
        return b""

# Public helper functions that match the example API
def load_pdb(pdb_id: str) -> bytes:
    """Load a PDB file by ID and return the resulting image."""
    return _call_viewer("load_pdb", pdb_id=pdb_id)

def highlight_hetero() -> bytes:
    """Highlight hetero atoms in the molecule and return the resulting image."""
    return _call_viewer("highlight_hetero")

def show_surface(selection: Optional[Dict[str, Any]] = None) -> bytes:
    """Add a surface representation and return the resulting image."""
    return _call_viewer("show_surface", selection=selection or {})

def rotate(x=0, y=0, z=0) -> bytes:
    """Rotate the view by the given angles and return the resulting image."""
    return _call_viewer("rotate", x=x, y=y, z=z)

def zoom(factor: float = 1.2) -> bytes:
    """Zoom the view by the given factor and return the resulting image."""
    return _call_viewer("zoom", factor=factor)

def add_box(center: Dict[str, float], size: Dict[str, float]) -> bytes:
    """Add a box around the specified region and return the resulting image."""
    # Make sure we have proper dictionaries with numeric values
    if not isinstance(center, dict) or not isinstance(size, dict):
        logger.error(f"Invalid parameters: center={center}, size={size}")
        raise ValueError("Both center and size must be dictionaries")
    
    # Ensure all required keys are present
    for key in ['x', 'y', 'z']:
        if key not in center or key not in size:
            logger.error(f"Missing coordinate '{key}' in parameters: center={center}, size={size}")
            raise ValueError(f"Both center and size must contain '{key}' coordinates")
    
    # Log the parameters for debugging
    logger.info(f"Adding box with center={center}, size={size}")
    
    # Call the viewer with validated parameters
    return _call_viewer("add_box", center=center, size=size)

def set_style(selection: Dict[str, Any], style: Dict[str, Any]) -> bytes:
    """Set the style for the selected atoms and return the resulting image."""
    return _call_viewer("set_style", selection=selection, style=style)

def reset_view() -> bytes:
    """Reset the view to the default and return the resulting image."""
    return _call_viewer("reset")

# ────────────────────────────────  Dev server  ──────────────────────────────────
if __name__ == "__main__":
    print("Open http://0.0.0.0:5000 in a browser")
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, 
                 allow_unsafe_werkzeug=True, use_reloader=True, log_output=True)
