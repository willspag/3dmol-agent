import json
import os
import logging
import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator, Union, TypedDict, Literal

# Load environment variables
from dotenv import load_dotenv

load_dotenv(override=True)

# Ensure OpenAI package is installed
try:
    from openai import OpenAI
except ImportError:
    raise ImportError(
        "OpenAI package is required. Please install it with 'pip install openai'."
    )


# Define TypedDict classes for message structure
class SystemMessage(TypedDict):
    role: Literal['system']
    content: str


class UserMessage(TypedDict):
    role: Literal['user']
    content: str


class FunctionCall(TypedDict):
    id: str
    type: Literal['function']
    function: Dict[str, Any]


class AssistantMessage(TypedDict, total=False):
    role: Literal['assistant']
    content: Optional[str]
    tool_calls: Optional[List[FunctionCall]]


class ToolResultMessage(TypedDict):
    role: Literal['tool']
    tool_call_id: str
    content: str


# Union type for all message types
Message = Union[SystemMessage, UserMessage, AssistantMessage,
                ToolResultMessage]


MODEL = os.environ.get("OPENAI_MODEL", "o4-mini")

logger = logging.getLogger(__name__)


class MolecularAIAssistant:
    def __init__(self, emit_response_func, api_key=None):
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        self.system_message = """You are a helpful molecular biology assistant specializing in protein structure visualization.
You have access to a 3D molecular viewer and can help users visualize and manipulate protein structures.
You can load PDB files, highlight specific parts of molecules, show surfaces, rotate the view, zoom, and more.
Always be helpful, concise, and provide scientific explanations when appropriate.

IMPORTANT: When you call a function (tool) to interact with the 3D viewer:
1. You will first receive a `function_call_output` item indicating whether the action succeeded or failed (e.g., `{"status": "success"}` or `{"status": "error", "message": "Details..."}`).
2. Immediately following the `function_call_output` item, a `developer` message containing a base64-encoded image (screenshot) of the 3D viewer's current state will be automatically added to the conversation.
3. The image message is tagged with the *developer* role and represents feedback from the tool. You may analyze it and, if needed, call another tool before composing your textual response for the user."""
        
        
        # Initialize with system message
        system_msg: SystemMessage = {
            "role": "system",
            "content": self.system_message
        }
        self.conversation_history: List[Message] = [system_msg]
        
        # Pass the _emit_response function to the init function so it connects properly to the socketio shit
        self._emit_response = emit_response_func

    def _get_tools_definition(self):
        """Define the tools that the model can use to control the 3D viewer."""
        return [{
            "type": "function",
            "name": "load_pdb",
            "description": "Load a protein structure by PDB ID into the 3D viewer. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "pdb_id": {
                        "type":
                        "string",
                        "description":
                        "The 4-character PDB ID of the structure to load (e.g., '1HSG', '4FNT')."
                    }
                },
                "required": ["pdb_id"],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "highlight_hetero",
            "description": "Highlight hetero atoms (non-protein components like ligands, water, etc.) in the current structure. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "show_surface",
            "description":
            "Add a surface representation to the current structure.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "selection": {
                        "type": ["object", "null"],
                        "description":
                        "Optional selection criteria to show surface only for specific parts of the structure. If null, applies to the whole structure. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
                        "properties": {
                            "chain": {
                                "type": ["string", "null"],
                                "description": "Chain identifier (e.g., 'A', 'B')."
                            },
                            "resi": {
                                "type": ["string", "null"],
                                "description":
                                "Residue number or range (e.g., '101', '1-100')."
                            }
                        },
                        "required": ["chain", "resi"],
                        "additionalProperties": False
                    }
                },
                "required": ["selection"],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "rotate",
            "description": "Rotate the molecule view around specified axes. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": ["number", "null"],
                        "description":
                        "Degrees to rotate around X-axis. Null if no rotation on this axis."
                    },
                    "y": {
                        "type": ["number", "null"],
                        "description":
                        "Degrees to rotate around Y-axis. Null if no rotation on this axis."
                    },
                    "z": {
                        "type": ["number", "null"],
                        "description":
                        "Degrees to rotate around Z-axis. Null if no rotation on this axis."
                    }
                },
                "required": ["x", "y", "z"],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "zoom",
            "description": "Zoom the view in or out. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "factor": {
                        "type":
                        "number",
                        "description":
                        "Zoom factor. Values > 1 zoom in, values < 1 zoom out (e.g., 1.2 to zoom in 20%, 0.8 to zoom out 20%)."
                    }
                },
                "required": ["factor"],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "add_box",
            "description": "Add a box around a specific region of the structure. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "center": {
                        "type": "object",
                        "properties": {
                            "x": {
                                "type": "number"
                            },
                            "y": {
                                "type": "number"
                            },
                            "z": {
                                "type": "number"
                            }
                        },
                        "required": ["x", "y", "z"],
                        "additionalProperties": False,
                        "description": "Center coordinates of the box."
                    },
                    "size": {
                        "type": "object",
                        "properties": {
                            "x": {
                                "type": "number"
                            },
                            "y": {
                                "type": "number"
                            },
                            "z": {
                                "type": "number"
                            }
                        },
                        "required": ["x", "y", "z"],
                        "additionalProperties": False,
                        "description": "Dimensions of the box (width, height, depth)."
                    }
                },
                "required": ["center", "size"],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "set_style",
            "description":
            "Set the visualization style for specific parts of the structure. All parameters must follow 3Dmol.js syntax. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "selection": {
                        "type": "object",
                        "properties": {
                            "chain": {
                                "type": ["string", "null"],
                                "description": "Chain identifier (e.g., 'A', 'B')."
                            },
                            "resi": {
                                "type": ["string", "null"],
                                "description":
                                "Residue number or range (e.g., '101', '1-100')."
                            },
                            "elem": {
                                "type": ["string", "null"],
                                "description":
                                "Element symbol (e.g., 'C' for carbon, 'N' for nitrogen)."
                            }
                        },
                        "required": ["chain", "resi", "elem"],
                        "additionalProperties": False,
                        "description":
                        "Selection criteria to apply the style to. Use null for fields not needed for selection (e.g., select whole chain 'A': {'chain': 'A', 'resi': null, 'elem': null})."
                    },
                    "style_type": {
                        "type": "string",
                        "enum": ["stick", "cartoon", "sphere", "line"],
                        "description":
                        "The type of visualization style to apply."
                    },
                    "style_params": {
                        "type": ["object", "null"],
                        "description":
                        "Optional parameters for the chosen style (e.g., color, radius). Pass null if no specific parameters are needed.",
                        "properties": {}, # Define specific params here if needed later
                        "required": [],
                        "additionalProperties": False
                    }
                },
                "required": ["selection", "style_type", "style_params"],
                "additionalProperties": False
            }
        }, {
            "type": "function",
            "name": "reset_view",
            "description": "Reset the viewer to the default view. Returns status message and triggers an automatic developer-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        }]

    def process_user_message(self, user_message) -> None:
        """
        Process a user message by adding it to conversation history and initiating 
        model response processing.

        This function does not return anything. It:
        1. Adds the user message to the conversation history
        2. Calls _generate_response() to begin processing the model's response
        3. Lets _generate_response() and handle_response_object() manage the 
           incremental processing of model outputs

        The actual responses from the model are handled through emitted events
        that the caller listens for, rather than return values.

        Args:
            user_message: The message text from the user to process
        """
        # Add user message to conversation history
        user_msg: UserMessage = {"role": "user", "content": user_message}
        self.conversation_history.append(user_msg)
        
        # Run model generation loop
        self._generate_response()

    def _generate_response(self) -> Dict[str, Any]:
        """Internal helper that queries OpenAI with the **current** conversation history
        (without mutating it) and returns a parsed dict in the same format as
        :py:meth:`process_user_message` but **without** adding any new user
        message.  This is used to continue the conversation after the caller has
        appended tool results via :py:meth:`add_function_result`."""
        
        # We only need to keep querying the model if it requested a new tool
        # call in the previous response. The `handle_response_object` method
        # returns the *outer* response_item.type ("function_call", "message",
        # etc.). If the last item the model sent was a "function_call", we
        # should execute it and then ask the model how to proceed. As soon as
        # the last item is a regular assistant "message", we are done and can
        # return control back to the caller.

        last_response_item_type: Optional[str] = "function_call"  # force at least one request

        while last_response_item_type == "function_call":
            try:
                response = self.client.responses.create(
                    model=MODEL,
                    input=self.conversation_history,
                    tools=self._get_tools_definition(),
                    reasoning={"effort": "medium", "summary": "auto"}
                )

                last_response_item_type = self.handle_response_object(response)

            except Exception as e:
                logger.error(f"Error generating follow-up response: {e}")
                # Stop the loop on any error to avoid hanging the HTTP request
                break

    # New _parse_response_object function to more closely follow openai's example implementations
    def handle_response_object(self, response) -> str:
        
        #print(f"\n\n\njson.dumps(response,indent=4): {json.dumps(response,indent=4)}\n\n\n")
        
        # Keep track of what the last response_item type was to return (if not a message, the model should be queries again)
        last_response_item_type = None
        # Determine if a tool call is needed and process accordingly.
        if response.output:
            print(f"\n\n\nresponse.output exists! len(response.output) - {len(response.output)}\n\n\n")
            
            for response_item in response.output:
                print(f"\n\nProcessing response_item of type {response_item.type}!\n\n")
                if response_item.type == "reasoning":
                    reasoning_summary = response_item.summary
                    print(f"\n\n\nresponse_item: {response_item}\n\n\n")
                    reasoning_summary_dict = {
                        'type': 'reasoning',
                        'summary': reasoning_summary
                    }
                    self._emit_response(reasoning_summary_dict)
                    # Add reasoning response_item to conversation history
                    self.conversation_history.append(response_item)
                    
                elif response_item.type == 'function_call':
                    function_call_args = response_item.arguments
                    function_call_id = response_item.call_id
                    function_name = response_item.name
                    
                    # Append the tool call object to the conversation history
                    self.conversation_history.append(response_item)
                    
                    # Go ahead and emit the tool_start object
                    self._emit_response({
                        'type':'tool_start',
                        'name': function_name,
                        'arguments': function_call_args
                    })
                    
                    # Run the actual viewer/tool and get result
                    result_dict, image_base64 = execute_function_call(function_name, function_call_args)

                    # Emit a tool_result back to the front-end so that the UI
                    # can update status and display the optional screenshot.
                    self._emit_response({
                        "type": "tool_result",
                        "name": function_name,
                        "result": result_dict,
                    })

                    # Also append a function_call_output item to the
                    # conversation history so that the assistant has access
                    # to the outcome on subsequent turns.
                    tool_response_dict = {
                        "type": "function_call_output",
                        "call_id": function_call_id,
                        "output": json.dumps(result_dict),
                    }
                    self.conversation_history.append(tool_response_dict)
                    logger.info(
                        f"Added function_call_output for {function_name} to conversation history"
                    )

                elif response_item.type == 'message':
                    for response_message_content_object in response_item.content:
                        text_content = None
                        # If it's a refusal, content type, log that it happened.
                        # Either way, send the message content and append response_item to conversation history
                        if response_message_content_object.type == "refusal":
                            logging.warning(f"Model refusal received: {json.dumps(response_message_content_object)}")
                            text_content = response_message_content_object.refusal
                            annotations = None
                        elif response_message_content_object.type == "output_text":
                            text_content = response_message_content_object.text
                            if hasattr(response_message_content_object, "annotations"):
                                annotations = response_message_content_object.annotations
                            else:
                                annotations = None
                        
                        
                        # Add message to conversation history
                        self.conversation_history.append(response_item)
                        logger.info(f"Added message response_item with text_content '{text_content}' to conversation history")
                    
                        # Display Response
                        self._emit_response({
                            "type": "text",
                            "content": text_content,
                            "annotations": annotations,
                        })
                
                
                # Keep track of last_response_item_type
                last_response_item_type = response_item.type
                
            return last_response_item_type
                        
                    

    
    # Public helper to continue after tool results
    def continue_assistant(self) -> Dict[str, Any]:
        """Generate the assistant's next turn without adding a new user message."""
        return self._generate_response()




import base64
import io
import os
import logging
import threading
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import partial
import pickle
from flask import Flask, render_template, request, jsonify, Response, session
from flask_socketio import SocketIO, emit

#from ai_assistant_responses import MolecularAIAssistant

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

# Keep track of connections
_connected_sids = []
_primary_sid: Optional[str] = None

# Store test results for retrieval
test_results: List[Dict[str, Any]] = []

# Helper functions for multi-user session persistence

def get_ai_assistant(emit_response_func):
    
    
    
    assistant = MolecularAIAssistant(emit_response_func=emit_response_func)
    if 'conversation_history' in session:
        try:
            assistant.conversation_history = pickle.loads(session['conversation_history'])
        except Exception:
            assistant.conversation_history = assistant.conversation_history[:1]  # just system message
    return assistant

def save_ai_assistant(assistant):
    session['conversation_history'] = pickle.dumps(assistant.conversation_history)

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
    request_id = data.get('request_id')
    if request_id in viewer_command_responses:
        viewer_command_responses[request_id]['result'] = data
        viewer_command_responses[request_id]['event'].set()

# Modified implementation of Socket.IO RPC call with REST API fallback
def _call_viewer(command: str, **kwargs) -> bytes:
    """Internal helper that asks the viewer to run a command and returns a PNG."""
    if _primary_sid is None:
        logger.error("_call_viewer invoked but _primary_sid is None – no viewer connected")
        return b""

    logger.info(f"Calling command '{command}' for primary SID: {_primary_sid}")
    payload: Dict[str, Any] = {"name": command, **kwargs}

    # Create a unique request ID for this command
    request_id = f"cmd_{time.time_ns()}"

    # Setup the response data
    viewer_command_responses[request_id] = {
        'result': None,
        'event': threading.Event()
    }

    # Emit command to viewer – use explicit room to ensure delivery even from background threads
    logger.debug(f"Emitting 'command' to viewer with request_id {request_id} and payload {payload}")
    socketio.emit("command", {
        "payload": payload,
        "request_id": request_id
    },
    room=_primary_sid,
    namespace="/")

    # Wait for response with timeout
    try:
        timeout = int(os.environ.get("VIEWER_COMMAND_TIMEOUT", "30"))  # seconds
    except ValueError:
        timeout = 30  # Default to 20 seconds if conversion fails
    response_event = viewer_command_responses[request_id]['event']
    if not response_event.wait(timeout=timeout):
        logger.error(f"Timeout waiting for response to {command}")
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
    """Handle user chat messages and return AI responses (non-streaming)."""
    message_text = request.json.get('message', '')
    logger.info(f"Received chat message via API: {message_text}")
    
    # Define the _emit_response before passing it to get_ai_assistant()
    def _emit_response(payload):
        socketio.emit('ai_response', payload)
        
    try:
        ai_assistant = get_ai_assistant(emit_response_func = _emit_response) # Get assistant early
        ai_assistant.process_user_message(user_message=message_text)
        response = jsonify({
                "status": "success"
            }), 200

    except Exception as e:
        logger.exception(f"Error processing chat message: {e}")
        response = jsonify({
            "status": "error",
            "error": str(e),
            "responses": [{"type": "error", "content": f"Error: {str(e)}"}],
        }), 500
        
    
    return response


# Keep legacy Socket.IO handler for compatibility
@socketio.on('chat_message')
def handle_chat_message(message_text):
    """Handle user chat messages via Socket.IO (non-streaming)."""
    logger.info(f"Received chat message via Socket.IO: {message_text}")

    def _process():
        try:
            ai_assistant = get_ai_assistant(emit_response_func = _emit_response) # Get assistant early
            ai_assistant.process_user_message(user_message=message_text)

        except Exception as e:
            logger.exception(f"Error processing chat message: {e}")

    def _emit_response(payload):
        socketio.emit('ai_response', payload)

    threading.Thread(target=_process).start()
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

    # Prepare success messages early so both caller and background thread share it
    success_messages = {
        'load_pdb': f"Loaded PDB: {arguments.get('pdb_id', 'unknown')}",
        'highlight_hetero': "Highlighted hetero atoms",
        'show_surface': "Showed surface representation",
        'rotate':
        f"Rotated view: x={arguments.get('x', 0)}, y={arguments.get('y', 0)}, z={arguments.get('z', 0)}",
        'zoom': f"Zoomed view by factor: {arguments.get('factor', 1.2)}",
        'add_box': f"Added box with parameters: {arguments}",
        'set_style': f"Set style with parameters: {arguments}",
        'reset_view': "Reset view to default"
    }

    def _background_viewer_call(fn_name, fn_args):
        """Run the blocking _call_viewer helper in a background thread and emit the
        tool_result once finished so the front-end can update."""
        try:
            img_data = _call_viewer(fn_name, **fn_args)
            img_b64 = base64.b64encode(img_data).decode('utf-8') if img_data else None
            result_payload = {
                'success': img_b64 is not None,
                'message': success_messages[fn_name] if img_b64 else "Operation completed but no image was returned",
                'image': img_b64,
            }

            # Forward to the connected clients (chat UI) as a tool_result
            socketio.emit('ai_response', {
                'type': 'tool_result',
                'name': fn_name,
                'result': result_payload,
            })

        except Exception as exc:
            logger.exception(f"Background viewer call for {fn_name} failed: {exc}")
            socketio.emit('ai_response', {
                'type': 'tool_error',
                'name': fn_name,
                'error': str(exc),
            })

    # Start the blocking viewer call in a new background task so we don't hang
    socketio.start_background_task(_background_viewer_call, function_name, arguments)

    # Return an immediate placeholder result (no image) so the assistant can
    # continue reasoning. The front-end will later receive the tool_result that
    # contains the real outcome produced by the background task.
    placeholder = {
        'success': True,
        'message': 'Command dispatched',
        'image': None,
    }

    return placeholder, None


# ────────────────────────────────  Dev server  ──────────────────────────────────
if __name__ == "__main__":
    print("Open http://0.0.0.0:5000 in a browser")
    socketio.run(app,
                 host="0.0.0.0",
                 port=5000,
                 debug=True,
                 allow_unsafe_werkzeug=True,
                 use_reloader=True,
                 log_output=True)
