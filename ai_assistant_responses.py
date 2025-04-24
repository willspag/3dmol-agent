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
Always be helpful, concise, and provide scientific explanations when appropriate."""

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
            "function": {
                "name": "load_pdb",
                "description":
                "Load a protein structure by PDB ID into the 3D viewer.",
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
                    "required": ["pdb_id"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "highlight_hetero",
                "description":
                "Highlight hetero atoms (non-protein components like ligands, water, etc.) in the current structure.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "show_surface",
                "description":
                "Add a surface representation to the current structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selection": {
                            "type": "object",
                            "description":
                            "Optional selection criteria to show surface only for specific parts of the structure.",
                            "properties": {
                                "chain": {
                                    "type":
                                    "string",
                                    "description":
                                    "Chain identifier (e.g., 'A', 'B')."
                                },
                                "resi": {
                                    "type":
                                    "string",
                                    "description":
                                    "Residue number range (e.g., '1-100')."
                                }
                            }
                        }
                    }
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "rotate",
                "description":
                "Rotate the molecule view around specified axes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "number",
                            "description": "Degrees to rotate around X-axis."
                        },
                        "y": {
                            "type": "number",
                            "description": "Degrees to rotate around Y-axis."
                        },
                        "z": {
                            "type": "number",
                            "description": "Degrees to rotate around Z-axis."
                        }
                    }
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "zoom",
                "description": "Zoom the view in or out.",
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
                    "required": ["factor"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "add_box",
                "description":
                "Add a box around a specific region of the structure.",
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
                            "description": "Dimensions of the box."
                        }
                    },
                    "required": ["center", "size"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "set_style",
                "description":
                "Set the visualization style for specific parts of the structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selection": {
                            "type":
                            "object",
                            "properties": {
                                "chain": {
                                    "type":
                                    "string",
                                    "description":
                                    "Chain identifier (e.g., 'A', 'B')."
                                },
                                "resi": {
                                    "type":
                                    "string",
                                    "description":
                                    "Residue number range (e.g., '1-100')."
                                },
                                "elem": {
                                    "type":
                                    "string",
                                    "description":
                                    "Element symbol (e.g., 'C' for carbon, 'N' for nitrogen)."
                                }
                            },
                            "description":
                            "Selection criteria to apply the style to."
                        },
                        "style": {
                            "type": "object",
                            "properties": {
                                "stick": {
                                    "type":
                                    "object",
                                    "description":
                                    "Stick representation parameters."
                                },
                                "cartoon": {
                                    "type":
                                    "object",
                                    "description":
                                    "Cartoon representation parameters."
                                },
                                "sphere": {
                                    "type":
                                    "object",
                                    "description":
                                    "Sphere representation parameters."
                                },
                                "line": {
                                    "type":
                                    "object",
                                    "description":
                                    "Line representation parameters."
                                }
                            },
                            "description": "Style configuration to apply."
                        }
                    },
                    "required": ["selection", "style"]
                }
            }
        }, {
            "type": "function",
            "function": {
                "name": "reset_view",
                "description": "Reset the viewer to the default view.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }]

    async def process_user_message(
            self, user_message) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a user message and yield streaming responses.
        
        This method is a generator that yields:
        - text chunks for normal AI responses
        - function call objects when the AI wants to execute a function
        """
        # Add user message to conversation history
        user_msg: UserMessage = {"role": "user", "content": user_message}
        self.conversation_history.append(user_msg)

        try:
            # Create the API request
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=self.conversation_history,
                tools=self._get_tools_definition(),
                stream=True  # Enable streaming
            )

            # Initialize variables to collect streamed content
            collected_content = ""
            current_tool_calls = {}  # Map tool call IDs to their data

            # Stream the response
            for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle content chunk (regular text response)
                if hasattr(delta, "content") and delta.content is not None:
                    content_chunk = delta.content
                    collected_content += content_chunk

                    # Yield the text chunk
                    yield {"type": "text", "content": content_chunk}

                # Handle tool calls
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        # Get ID of this tool call
                        tool_id = tool_call.index

                        # Initialize tool call data if not existing
                        if tool_id not in current_tool_calls:
                            current_tool_calls[tool_id] = {
                                "id":
                                tool_call.id if hasattr(tool_call, "id") else
                                f"call_{tool_id}",
                                "name":
                                tool_call.function.name if hasattr(
                                    tool_call.function, "name") else "",
                                "arguments":
                                ""
                            }

                        # Update tool call data
                        if hasattr(tool_call.function,
                                   "name") and tool_call.function.name:
                            current_tool_calls[tool_id][
                                "name"] = tool_call.function.name

                        if hasattr(
                                tool_call.function,
                                "arguments") and tool_call.function.arguments:
                            current_tool_calls[tool_id][
                                "arguments"] += tool_call.function.arguments

                        if hasattr(tool_call, "id") and tool_call.id:
                            current_tool_calls[tool_id]["id"] = tool_call.id

                # Check for finish reason
                if chunk.choices[0].finish_reason == "tool_calls":
                    # Process all complete tool calls
                    for tool_id, tool_call in current_tool_calls.items():
                        try:
                            # Skip incomplete tool calls
                            if not tool_call["name"] or not tool_call[
                                    "arguments"]:
                                logger.warning(
                                    f"Incomplete tool call: {tool_call}")
                                continue

                            # Parse the arguments JSON
                            arguments = json.loads(tool_call["arguments"])

                            # Add to conversation history
                            assistant_msg: AssistantMessage = {
                                "role":
                                "assistant",
                                "content":
                                None,
                                "tool_calls": [{
                                    "id": tool_call["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tool_call["name"],
                                        "arguments": tool_call["arguments"]
                                    }
                                }]
                            }
                            self.conversation_history.append(assistant_msg)

                            # Yield the tool call
                            logger.info(
                                f"Function call: {tool_call['name']} with args: {arguments}"
                            )
                            yield {
                                "type": "function_call",
                                "call_id": tool_call["id"],
                                "name": tool_call["name"],
                                "arguments": arguments
                            }
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"Failed to parse tool call arguments: {tool_call['arguments']}, error: {e}"
                            )

            # After all chunks processed, if we've collected text, add it to history
            if collected_content and not current_tool_calls:
                assistant_text_msg: AssistantMessage = {
                    "role": "assistant",
                    "content": collected_content
                }
                self.conversation_history.append(assistant_text_msg)

        except Exception as e:
            logger.error(f"Error in AI processing: {str(e)}")
            error_response = {
                "type": "text",
                "content": f"I encountered an error: {str(e)}"
            }
            yield error_response

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
