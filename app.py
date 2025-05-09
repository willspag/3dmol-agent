import base64
import io
import os
import json
import logging
import threading
import time
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import partial

import pickle
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit

from ai_assistant import MolecularAIAssistant

# Load environment variables
from dotenv import load_dotenv

load_dotenv(override=True)

# Configure logging for easier debugging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask and Socket.IO
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-key")
# Go back to a simpler Socket.IO configuration that was working before
# Use polling only with reasonable timeouts
socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    async_mode="threading",
                    ping_timeout=60,
                    ping_interval=25,
                    transports=['polling'],
                    logger=False)

# Store assistants in memory with UUID keys
assistants_store = {}

# Define functions that modify the viewer state and expect an image back
VIEWER_MODIFYING_FUNCTIONS = {
    'load_pdb', 'highlight_hetero', 'show_surface', 'rotate', 'zoom',
    'add_box', 'set_style', 'reset_view'
}

# Timeout for waiting for the developer image
IMAGE_WAIT_TIMEOUT_SECONDS = int(os.environ.get("IMAGE_WAIT_TIMEOUT_SECONDS", "15"))

# Get AI Assistant using UUID from flask session
def get_ai_assistant():
    
    use_web_search = os.environ.get('USE_WEB_SEARCH_TOOL', 'TRUE').upper() == 'TRUE'
    
    # Check if we have a session UUID
    assistant_uuid = session.get('assistant_uuid')
    
    # If we have a UUID and it exists in our store, use that assistant
    if assistant_uuid and assistant_uuid in assistants_store:
        return assistants_store[assistant_uuid]
    
    # Otherwise create a new assistant
    assistant = MolecularAIAssistant(use_web_search_tool=use_web_search)
    
    # Generate a new UUID for this assistant and store it
    assistant_uuid = str(uuid.uuid4())
    session['assistant_uuid'] = assistant_uuid
    assistants_store[assistant_uuid] = assistant
    
    return assistant

# Save AI Assistant to the assistant store
def save_ai_assistant(assistant):
    assistant_uuid = session.get('assistant_uuid')
    if assistant_uuid:
        assistants_store[assistant_uuid] = assistant

# Clear AI Assistant conversation history
def clear_conversation_history():
    """Clear the conversation history and create a new assistant."""
    assistant_uuid = session.get('assistant_uuid')
    
    # Remove the old assistant from the store if it exists
    if assistant_uuid and assistant_uuid in assistants_store:
        del assistants_store[assistant_uuid]
    
    # Generate a new UUID for a fresh assistant
    new_uuid = str(uuid.uuid4())
    session['assistant_uuid'] = new_uuid
    
    # Create a new assistant and store it
    use_web_search = os.environ.get('USE_WEB_SEARCH_TOOL', 'TRUE').upper() == 'TRUE'
    assistants_store[new_uuid] = MolecularAIAssistant(use_web_search_tool=use_web_search)
    
    logger.info(f"Cleared conversation history and created new assistant with UUID: {new_uuid}")

# Keep track of connections
_connected_sids = []
_primary_sid: Optional[str] = None

# Store test results for retrieval
test_results: List[Dict[str, Any]] = []


# ────────────────────────────────  Routes  ──────────────────────────────────────
@app.route("/")
def index():
    """Serve the main page with 3D molecular viewer and test runner."""
    
    # Clear chat history from session
    clear_conversation_history()
    
    return render_template("index.html")


@app.route("/api/clear_chat_history", methods=["POST"])
def api_clear_chat_history():
    """Clear the AI assistant's conversation history."""
    try:
        clear_conversation_history()
        return jsonify({"status": "success", "message": "Chat history cleared."})
    except Exception as e:
        logger.error(f"Error clearing chat history: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


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
    global _connected_sids, _primary_sid
    current_sid = request.sid

    # Add to connected SIDs list
    if current_sid not in _connected_sids:
        _connected_sids.append(current_sid)

    # Set first connection as primary if none exists
    if _primary_sid is None:
        _primary_sid = current_sid
        logger.info(f"Primary client connected with SID: {_primary_sid}")
        emit("status", {"msg": "registered"})
    else:
        logger.info(f"Secondary client connected with SID: {current_sid}")
        # Allow secondary connections for the chat interface
        emit("status", {"msg": "viewer_only"})


@socketio.on("disconnect")
def _on_disconnect():
    global _connected_sids, _primary_sid
    current_sid = request.sid

    # Remove from connected SIDs
    if current_sid in _connected_sids:
        _connected_sids.remove(current_sid)

    # If primary disconnected, assign a new primary if possible
    if current_sid == _primary_sid:
        logger.info(f"Primary client disconnected: {_primary_sid}")
        _primary_sid = None
        if _connected_sids:
            _primary_sid = _connected_sids[0]
            logger.info(f"New primary client assigned: {_primary_sid}")
            socketio.emit("status", {"msg": "registered"}, to=_primary_sid)
    else:
        logger.info(f"Secondary client disconnected: {current_sid}")


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
# There are now two ways to call the viewer:
# 1. Via Socket.IO (the original method) - used for tests and live demos
# 2. Via REST API (new method) - more reliable for chat function calls

# Global queue to store viewer command responses
viewer_command_responses = {}


# REST API endpoint for viewer commands
@app.route('/api/viewer_command', methods=['POST'])
def handle_viewer_command_api():
    """Handle viewer commands and return the result as a REST API response."""
    if not request.is_json:
        return jsonify({"error": "Expected JSON data"}), 400

    data = request.json
    command_name = data.get('command')
    if not command_name:
        return jsonify({"error": "Missing command parameter"}), 400

    # Extract arguments
    kwargs = {k: v for k, v in data.items() if k != 'command'}

    # Handle specific commands with REST API
    logger.info(
        f"API call for viewer command: {command_name} with args: {kwargs}")

    # Submit the command to the viewer and get the result
    image_data = _call_viewer(command_name, **kwargs)

    # Convert binary image to base64 for the response
    image_base64 = base64.b64encode(image_data).decode(
        'utf-8') if image_data else None

    return jsonify({
        "success": image_base64 is not None,
        "image": image_base64
    })


# Socket.IO event handlers for viewer commands (for compatibility with test runner)
@socketio.on('viewer_command_response')
def handle_viewer_command_response(data):
    """Handle the response from a viewer command request."""
    logger.info(f"Received viewer_command_response for request_id: {data.get('request_id')}")

    request_id = data.get('request_id')
    if request_id and request_id in viewer_command_responses:
        logger.info(f"Found matching request_id: {request_id}. Setting event.")
        viewer_command_responses[request_id]['result'] = data
        viewer_command_responses[request_id]['event'].set()
    elif request_id:
        logger.warning(f"Received response for unknown/expired request_id: {request_id}")
    else:
        logger.warning(f"Received viewer_command_response with missing request_id: {data}")


# Modified implementation of Socket.IO RPC call with REST API fallback
def _call_viewer(command: str, **kwargs) -> bytes:
    
    print(f"\n\n\nCalling viewer with command {command} and args {json.dumps(kwargs)}\n\n\n")
    """Internal helper that asks the viewer to run a command and returns a PNG."""
    if _primary_sid is None:
        raise RuntimeError(
            "No primary viewer connected yet – open the app in a tab.")

    logger.info(f"Calling command '{command}' for primary SID: {_primary_sid}")
    payload: Dict[str, Any] = {"name": command, **kwargs}

    # Create a unique request ID for this command
    request_id = f"cmd_{time.time_ns()}"

    # Setup the response data
    viewer_command_responses[request_id] = {
        'result': None,
        'event': threading.Event()
    }

    # Send the command to the primary client
    socketio.emit("command", {
        "payload": payload,
        "request_id": request_id
    },
                  to=_primary_sid)

    # Wait for response with timeout
    try:
        timeout = int(os.environ.get("VIEWER_COMMAND_TIMEOUT", "30"))  # seconds
    except ValueError:
        timeout = 30  # Default to 30 seconds if conversion fails

    logger.info(f"Waiting for response_event for request_id: {request_id} with timeout: {timeout} seconds")
    response_event = viewer_command_responses[request_id]['event']
    if not response_event.wait(timeout=timeout):
        logger.error(f"Timeout waiting for response to {command} (request_id: {request_id})")
        del viewer_command_responses[request_id]
        return b""

    # Process the response
    try:
        result = viewer_command_responses[request_id]['result']
        # Clean up the response data
        del viewer_command_responses[request_id]

        if isinstance(result, dict) and "img" in result:
            img64: str = result["img"].split(
                ",", 1)[1]  # Drop data:image/png;base64,
            return base64.b64decode(img64)
        else:
            logger.error(f"No image in response: {result}")
            return b""
    except Exception as e:
        logger.error(f"Error processing response: {e}")
        if request_id in viewer_command_responses:
            del viewer_command_responses[request_id]
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
            logger.error(
                f"Missing coordinate '{key}' in parameters: center={center}, size={size}"
            )
            raise ValueError(
                f"Both center and size must contain '{key}' coordinates")

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


# ────────────────────────────────  AI Assistant  ──────────────────────────────────
# RESTful API for handling chat messages (more reliable than socketio with Gunicorn)
@app.route('/api/chat', methods=['POST'])
def handle_chat_message_api():
    """Handle user chat messages and return AI responses."""
    message_text = request.json.get('message', '')
    logger.info(f"Received chat message via API: {message_text}")
    
    
    ai_assistant = get_ai_assistant()
    
    # Add user message to conversation history
    user_msg = {"role": "user", "content": [{"type": 'input_text',"text": message_text}]}
    ai_assistant.conversation_history.append(user_msg)
    

    # We'll use a synchronous approach for simplicity to avoid the Socket.IO issues
    try:
        # Create a new event loop for the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Collect all the responses
        chat_payload = []

        # Process the message with the AI assistant
        async def collect_ai_responses():
            
            last_message_type = 'user_message'
            while last_message_type != 'text':
                
                # Removed the sleep here as event-based waiting is more robust
                # if not last_message_type == 'user_message': ... time.sleep(...)

                async for response_item in ai_assistant.get_model_response():
                    last_message_type = response_item['type']
                    function_modified_viewer = False # Flag to track if we need to wait

                    if response_item['type'] == 'text':
                        # Add text chunk to response
                        chat_payload.append({
                            'type': 'text',
                            'content': response_item['content'],
                            'annotations': response_item['annotations']
                            
                        })
                        
                        
                    elif response_item['type'] == 'reasoning':
                        # Add reasoning summary to response
                        chat_payload.append({
                            'type': 'reasoning',
                            'content': response_item['content']
                        })
                        
                    
                    
                    elif response_item['type'] == 'web_search_call':
                        
                        chat_payload.append({
                            'type': 'web_search_call',
                            'status': response_item['status']
                        })
                        

                    elif response_item['type'] == 'function_call':
                        # Add function call notification to response
                        chat_payload.append({
                            'type': 'tool_start',
                            'name': response_item['name'],
                            'arguments': response_item['arguments']
                        })

                        
                        # Execute the function
                        try:
                            result = execute_function_call(
                                response_item['name'],
                                response_item['arguments'])

                            # Add function result to conversation
                            ai_assistant.add_function_result(
                                response_item['call_id'], response_item['name'],
                                result
                            )

                            # Add function result to response
                            chat_payload.append({
                                'type': 'tool_result',
                                'name': response_item['name'],
                                'result': result
                            })

                            # Check if this function modifies the viewer and requires waiting
                            if response_item['name'] in VIEWER_MODIFYING_FUNCTIONS and result.get('success'):
                                function_modified_viewer = True

                        except Exception as e:
                            logger.error(
                                f"Error executing function {response_item['name']}: {str(e)}"
                            )
                            chat_payload.append({
                                'type': 'tool_error',
                                'name': response_item['name'],
                                'error': str(e),
                                "raw_response_item": response_item['raw_response_item']
                            })

                    # Wait for the image if a viewer-modifying function was called successfully
                    if function_modified_viewer:
                        logger.info(f"Function '{response_item['name']}' executed. Waiting for developer image event...")
                        # Ensure the event is clear before waiting
                        ai_assistant.image_received_event.clear()
                        # Wait for the event to be set by handle_developer_image
                        event_received = ai_assistant.image_received_event.wait(timeout=IMAGE_WAIT_TIMEOUT_SECONDS)
                        if event_received:
                            logger.info("Developer image event received.")
                        else:
                            logger.warning(f"Timeout waiting for developer image after '{response_item['name']}'. Proceeding without image.")
                        # No need to clear again, wait does not consume the set state, but clearing before wait is good practice

        # Run the async function and wait for it to complete
        loop.run_until_complete(collect_ai_responses())
        loop.close()

        # Save the updated AI Assistant
        save_ai_assistant(ai_assistant)
    
        # Return the full response as JSON
        return jsonify({'responses': chat_payload})

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        return jsonify({
            'error':
            str(e),
            'responses': [{
                'type': 'error',
                'content': f"Error: {str(e)}"
            }]
        }), 500


# Keep legacy Socket.IO handler for compatibility
@socketio.on('chat_message')
def handle_chat_message(message_text):
    """Handle user chat messages via Socket.IO and process AI responses."""
    logger.info(f"Received chat message via Socket.IO: {message_text}")
    
    ai_assistant = get_ai_assistant()
    
    # Add user message to conversation history
    user_msg = {"role": "user", "content": [{"type": 'input_text',"text": message_text}]}
    ai_assistant.conversation_history.append(user_msg)

    # Create a thread to process the message to avoid blocking
    def process_message_thread():
        # Create an event loop for the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        

        try:
            # Process the message with the AI assistant
            async def process_chunks():
                
                last_message_type = 'user_message'
                while last_message_type != 'text':
                    # Removed sleep here as well

                    async for response_item in ai_assistant.get_model_response():
                        logger.debug(f"SocketIO: Processing response_item.type: {response_item.get('type')}") # Use .get for safety
                        last_message_type = response_item['type']
                        function_modified_viewer = False # Flag to track if we need to wait

                        if response_item['type'] == 'text':
                            # Send text response_item to the client
                            socketio.emit('ai_response', {
                                'type': 'text',
                                'content': response_item['content'],
                                'annotations': response_item['annotations']
                                
                            })
                            
                        
                        elif response_item['type'] == 'reasoning':
                            # Send reasoning response_item to the client
                            socketio.emit('ai_response', {
                                'type': 'reasoning',
                                'content': response_item['content']
                            })
                        

                        elif response_item['type'] == 'web_search_call':
                             socketio.emit('ai_response', {
                                'type': 'web_search_call',
                                'status': response_item['status']
                            })

                        elif response_item['type'] == 'function_call':
                            # Send function call notification to the client
                            socketio.emit(
                                'ai_response', {
                                    'type': 'tool_start',
                                    'name': response_item['name'],
                                    'arguments': response_item['arguments']
                                })

                            # Execute the function
                            try:
                                result = execute_function_call(
                                    response_item['name'],
                                    response_item['arguments'])

                                # Add function result to conversation
                                ai_assistant.add_function_result(
                                    response_item['call_id'],
                                    response_item['name'], result)

                                # Send function result to the client
                                socketio.emit(
                                    'ai_response', {
                                        'type': 'tool_result',
                                        'name': response_item['name'],
                                        'result': result
                                    })

                                # Check if this function modifies the viewer and requires waiting
                                if response_item['name'] in VIEWER_MODIFYING_FUNCTIONS and result.get('success'):
                                    function_modified_viewer = True

                            except Exception as e:
                                logger.error(
                                    f"Error executing function {response_item['name']}: {str(e)}"
                                )
                                socketio.emit(
                                    'ai_response', {
                                        'type': 'tool_error',
                                        'name': response_item['name'],
                                        'error': str(e)
                                    })

                        # Wait for the image if a viewer-modifying function was called successfully
                        # This blocking wait is acceptable here because this entire function runs in a separate thread.
                        if function_modified_viewer:
                            logger.info(f"SocketIO: Function '{response_item['name']}' executed. Waiting for developer image event...")
                            # Ensure the event is clear before waiting
                            ai_assistant.image_received_event.clear()
                            # Wait for the event to be set by handle_developer_image
                            event_received = ai_assistant.image_received_event.wait(timeout=IMAGE_WAIT_TIMEOUT_SECONDS)
                            if event_received:
                                logger.info("SocketIO: Developer image event received.")
                            else:
                                logger.warning(f"SocketIO: Timeout waiting for developer image after '{response_item['name']}'. Proceeding without image.")
                            # No need to clear again

            # Run the async function that processes chunks
            loop.run_until_complete(process_chunks())

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            socketio.emit('ai_response', {
                'type': 'error',
                'content': f"Error: {str(e)}"
            })

        finally:
            loop.close()
            
            # Save the updated AI Assistant
            save_ai_assistant(ai_assistant)

    
    # Start the thread
    threading.Thread(target=process_message_thread).start()
    return {'status': 'processing'}


def execute_function_call(function_name, arguments):
    """Execute a function call from the AI and return the result."""
    logger.info(
        f"Executing function: {function_name} with arguments: {arguments}")


    # Convert arguments to dict if it's a JSON string
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse arguments JSON string: {e}")
            raise ValueError(f"Invalid JSON arguments: {arguments}")
        
    # Map of valid function names
    valid_functions = {
        'load_pdb', 'highlight_hetero', 'show_surface', 'rotate', 'zoom',
        'add_box', 'set_style', 'reset_view'
    }

    if function_name not in valid_functions:
        raise ValueError(f"Unknown function: {function_name}")

    try:
        # Prepare appropriate response messages based on function
        success_messages = {
            'load_pdb': f"Loaded PDB: {arguments.get('pdb_id', 'unknown')}",
            'highlight_hetero': "Highlighted hetero atoms",
            'show_surface': "Showed surface representation",
            'rotate':
            f"Rotated view: x={arguments.get('x', 0)}, y={arguments.get('y', 0)}, z={arguments.get('z', 0)}",
            'zoom': f"Zoomed view by factor: {arguments.get('factor', 1.2)}",
            'add_box': f"Added box with specified parameters",
            'set_style': "Set style for selected atoms",
            'reset_view': "Reset view to default"
        }

        # For this implementation, we'll execute the commands directly rather than via Socket.IO
        # Prepare the API call parameters based on the function
        #call_params = {'command': function_name}
        #call_params.update(arguments)

        # Directly execute the viewer command
        image_data = _call_viewer(function_name, **arguments)
        image_base64 = base64.b64encode(image_data).decode(
            'utf-8') if image_data else None
        success_messagee = success_messages[function_name] + "\n\nNotice: Due to asynchronous function execution, there may be a delay in the automated 'user' message providing the screenshot of the updated 3dmol.js viewer."
        # Return the result
        return {
            'success': True,#image_base64 is not None,
            'message': success_messagee,
            'image': image_base64
        }

    except Exception as e:
        logger.error(f"Error executing function {function_name}: {str(e)}")
        return {'success': False, 'message': f"Error: {str(e)}"}


# ────────────────────────────────  Dev server  ──────────────────────────────────
@app.route('/api/developer_image', methods=['POST'])
def handle_developer_image():
    """Handle developer image messages from the frontend and signal the waiting chat thread."""
    if not request.is_json:
        return jsonify({"error": "Expected JSON data"}), 400

    data = request.json
    image_b64 = data.get('image_b64')
    tool_name = data.get('tool_name') # Keep tool_name for logging/context

    if not image_b64 or not tool_name:
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        # Get the current AI assistant
        ai_assistant = get_ai_assistant()

        logging.info(f"Received developer image for tool '{tool_name}'. Adding to history.")
        developer_image_msg = {
            "role": "user", # Use 'user' role as per revised prompt strategy
            "content": [
                {"type": 'input_text', "text": f"Here's a screenshot of the 3Dmol.js viewer after executing the {tool_name} command:"},
                {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"}
            ]
        }

        # Add the developer message to conversation history
        ai_assistant.conversation_history.append(developer_image_msg)

        # Save the updated AI Assistant state
        save_ai_assistant(ai_assistant)

        # Signal the waiting chat thread that the image has been received and processed
        logger.info(f"Setting image_received_event for assistant {session.get('assistant_uuid')}")
        ai_assistant.image_received_event.set()

        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"Error handling developer image: {str(e)}", exc_info=True)
        # Attempt to signal anyway, but log the error clearly
        try:
            ai_assistant = get_ai_assistant()
            if ai_assistant:
                logger.warning("Signaling image event despite error during processing.")
                ai_assistant.image_received_event.set()
        except Exception as signal_err:
             logger.error(f"Failed to signal image event after error: {signal_err}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    print("Open http://0.0.0.0:5000 in a browser")
    socketio.run(app,
                 host="0.0.0.0",
                 port=5000,
                 debug=True,
                 allow_unsafe_werkzeug=True,
                 use_reloader=True,
                 log_output=True)
