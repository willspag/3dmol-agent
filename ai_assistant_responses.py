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

    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        self.system_message = """You are a helpful molecular biology assistant specializing in protein structure visualization.
You have access to a 3D molecular viewer and can help users visualize and manipulate protein structures.
You can load PDB files, highlight specific parts of molecules, show surfaces, rotate the view, zoom, and more.
Always be helpful, concise, and provide scientific explanations when appropriate.

IMPORTANT: When you call a function (tool) to interact with the 3D viewer:
1. You will first receive a `tool` message indicating whether the action succeeded or failed (e.g., `{"status": "success"}` or `{"status": "error", "message": "Details..."}`).
2. Immediately following the `tool` message, a `user` message containing a base64 encoded image (screenshot) of the 3D viewer's current state will be automatically added to the conversation.
3. This image message is part of the tool's feedback, NOT a new message from the actual user. You are not obligated to respond directly to this image immediately. You may choose to analyze the image and call another tool if further manipulation is needed before generating a textual response for the user."""

        # Initialize with system message
        system_msg: SystemMessage = {
            "role": "system",
            "content": self.system_message
        }
        self.conversation_history: List[Message] = [system_msg]

    def _get_tools_definition(self):
        """Define the tools that the model can use to control the 3D viewer."""
        return [{
            "type": "function",
            "name": "load_pdb",
            "description": "Load a protein structure by PDB ID into the 3D viewer. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
            "description": "Highlight hetero atoms (non-protein components like ligands, water, etc.) in the current structure. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
                        "Optional selection criteria to show surface only for specific parts of the structure. If null, applies to the whole structure. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
            "description": "Rotate the molecule view around specified axes. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
            "description": "Zoom the view in or out. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
            "description": "Add a box around a specific region of the structure. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
            "Set the visualization style for specific parts of the structure. All parameters must follow 3Dmol.js syntax. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
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
            "description": "Reset the viewer to the default view. Returns status message and triggers an automatic user-message containing a screenshot image of the updated 3dmol.js viewer after the function is applied.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False
            }
        }]

    def process_user_message(self, user_message) -> Dict[str, Any]:
        """
        Process a user message and return the complete AI response using the responses API.
        
        This method returns a dictionary containing either:
        - The AI's textual response: {'type': 'text', 'content': '...'}
        - A list of function calls: {'type': 'function_calls', 'calls': [{'call_id': '...', 'name': '...', 'arguments': {...}}]}
        - An error message: {'type': 'error', 'content': '...'}
        """
        # Add user message to conversation history
        user_msg: UserMessage = {"role": "user", "content": user_message}
        self.conversation_history.append(user_msg)

        try:
            # Create the API request using responses.create (non-streaming)
            response = self.client.responses.create(
                model=MODEL,
                input=self.conversation_history, # Use 'input' for responses API
                tools=self._get_tools_definition(),
                # No stream=True here
                # No tool_choice needed explicitly for non-streaming 'auto' behavior with responses API
            )

            # The response object contains 'output' (list) and 'output_text' (string)

            # Check if the output contains function calls
            # responses.create returns a list in 'output' for function calls
            # and potentially text in 'output_text'
            
            function_calls_requested = []
            if response.output and isinstance(response.output, list):
                 for item in response.output:
                     # According to docs, function calls have type 'function_call'
                     if isinstance(item, dict) and item.get("type") == "function_call":
                         function_calls_requested.append(item)
                     # Handle other potential item types if necessary

            if function_calls_requested:
                parsed_tool_calls = []
                
                # Construct the assistant message for history based on the raw API response
                # It might contain multiple function calls
                assistant_msg_tool_calls = []
                for fc in function_calls_requested:
                     # Ensure fc has the expected structure before accessing attributes
                     if "id" in fc and "name" in fc and "arguments" in fc:
                        assistant_msg_tool_calls.append({
                            "id": fc["id"],
                            "type": "function",
                            "function": {
                                "name": fc["name"],
                                "arguments": fc["arguments"] # Keep arguments as string here for history
                            }
                        })
                     else:
                          logger.warning(f"Skipping malformed function call item in response: {fc}")

                if not assistant_msg_tool_calls:
                     logger.error("Detected function calls but failed to structure them for history.")
                     # Fallback or raise error? Returning text for now.
                     return {"type": "text", "content": "I attempted an action but encountered an internal structuring issue."}


                # Add assistant message with tool calls to history
                assistant_msg: AssistantMessage = {
                    "role": "assistant",
                    "content": None, # Typically no content when tool calls are made
                    "tool_calls": assistant_msg_tool_calls
                }
                self.conversation_history.append(assistant_msg)


                # Prepare the response object with parsed arguments for the caller
                for tool_call_data in function_calls_requested:
                    try:
                         # Ensure expected keys exist
                         if "name" in tool_call_data and "arguments" in tool_call_data and "call_id" in tool_call_data:
                            arguments = json.loads(tool_call_data["arguments"])
                            logger.info(
                                f"Function call requested: {tool_call_data['name']} with args: {arguments}"
                            )
                            parsed_tool_calls.append({
                                "call_id": tool_call_data["call_id"], # Use call_id from the response item
                                "name": tool_call_data["name"],
                                "arguments": arguments
                            })
                         else:
                              logger.warning(f"Skipping parsing malformed function call item: {tool_call_data}")

                    except json.JSONDecodeError as e:
                        logger.error(
                            f"Failed to parse tool call arguments: {tool_call_data.get('arguments', 'N/A')}, error: {e}"
                        )
                         # Optionally decide how to handle parse errors

                if parsed_tool_calls:
                    return {"type": "function_calls", "calls": parsed_tool_calls}
                else:
                     logger.warning("Function calls detected in API response but failed to parse arguments for any.")
                     # Add a simple text response to history if needed
                     assistant_text_fallback: AssistantMessage = {"role":"assistant", "content": "I tried to perform an action but encountered an issue."}
                     self.conversation_history.append(assistant_text_fallback)
                     return {"type": "text", "content": "I tried to perform an action but encountered an issue processing the details."}


            # Handle regular text response (present in output_text)
            elif response.output_text:
                assistant_text_msg: AssistantMessage = {
                    "role": "assistant",
                    "content": response.output_text
                }
                self.conversation_history.append(assistant_text_msg)
                return {"type": "text", "content": response.output_text}
            
            # Handle cases where there's neither text nor valid function calls
            else:
                 logger.warning("Received an empty or unexpected response structure from the AI.")
                 # Add an empty assistant message to history to mark the turn
                 assistant_empty_msg: AssistantMessage = { "role": "assistant", "content": None }
                 self.conversation_history.append(assistant_empty_msg)
                 return {"type": "text", "content": ""} # Return empty text


        except Exception as e:
            logger.error(f"Error in AI processing: {str(e)}")
            # Return a single error dictionary
            return {
                "type": "error", 
                "content": f"I encountered an error: {str(e)}"
            }

    def add_function_result(self, call_id, function_name, result):
        """Add a function call result to the conversation history."""
        try:
            # Format function result for the conversation history
            result_str = json.dumps(result)

            # Use the updated OpenAI API format for tool responses
            tool_result_msg: ToolResultMessage = {
                "role": "tool",
                "tool_call_id": call_id,
                "content": result_str
            }
            self.conversation_history.append(tool_result_msg)

            logger.info(
                f"Added function result for {function_name} to conversation history"
            )
            return True
        except Exception as e:
            logger.error(f"Error adding function result: {str(e)}")
            return False
