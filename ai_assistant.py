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

    def __init__(self, api_key=None, use_web_search_tool = True):
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
        self.use_web_search_tool = use_web_search_tool
        

    def _get_tools_definition(self):
        """Define the tools that the model can use to control the 3D viewer."""
        tools = [{
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

        # Add web search tool if self.use_web_search_tool is set to True
        if self.use_web_search_tool:
            tools.append({
                "type": "web_search_preview",
                "search_context_size": str(os.environ.get("WEB_SEARCH_CONTEXT_SIZE", 'medium')).lower()
                })
        
        return tools

    async def get_model_response(
            self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Query the AI model using OpenAI's responses API
        
        This method is a generator that yields:
        - text chunks for normal AI responses
        - function call objects when the AI wants to execute a function
        """

        try:
            # Create the API request
            if MODEL.lower().startswith('o'):
                response = self.client.responses.create(
                    model=MODEL,
                    input=self.conversation_history,
                    tools=self._get_tools_definition(),
                    reasoning={"effort": "medium", "summary": "auto"}
                )
            else:
                response = self.client.responses.create(
                    model=MODEL,
                    input=self.conversation_history,
                    tools=self._get_tools_definition()
                )

            if response.output:
                print(f"\n\n\nresponse.output exists! len(response.output) - {len(response.output)}\n\n\n")
                
                for response_item in response.output:
                    print(f"\n\nProcessing response_item of type {response_item.type}!\n\n")
                    print(f"response_item: {response_item}\n\n\n")
                    if response_item.type == "reasoning":
                        print(f"\n\n\nresponse_item: {response_item}\n\n\n")
                        
                        # Loop through response_item.summary and yield the text for each one (in case there are mutiple)
                        for reasoning_summary in response_item.summary:
                            
                            yield {
                                'type': 'reasoning',
                                'content': reasoning_summary.text,
                                'raw_response_item': response_item
                            }
                        
                        
                    elif response_item.type == 'function_call':
                        
                        # Yield the tool call
                        yield {
                                "type": "function_call",
                                "call_id": response_item.call_id,
                                "name": response_item.name,
                                "arguments": response_item.arguments,
                                'raw_response_item': response_item
                            }
                        
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
                                if hasattr(response_message_content_object, "annotations") and len(response_message_content_object.annotations) > 0:
                                    # Loop through and add attributes to ensure it's json serializable
                                    annotations = []
                                    for annotation in response_message_content_object.annotations:
                                        annotation_dict = {
                                            "type": annotation.type,
                                            "start_index": annotation.start_index,
                                            "end_index": annotation.end_index,
                                            "url": annotation.url,
                                            "title": annotation.title
                                        }
                                        annotations.append(annotation_dict)
                                else:
                                    annotations = []
                            
                            # Yield the text_content
                            yield {
                                "type": "text",
                                "content": text_content,
                                "annotations": annotations,
                                'raw_response_item': response_item
                            }
                    
                    elif response_item.type == 'web_search_call':
                        
                        yield {
                                'type': 'web_search_call',
                                'status': response_item.status,
                                'raw_response_item': response_item
                            }
                        
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
            # Remove image from result for tool message, if present
            result_no_image = dict(result)
            image_b64 = result_no_image.pop('image', None)
            result_str = json.dumps(result_no_image)

            # Append according to Responses API: function_call_output item (no role)
            self.conversation_history.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": result_str,
            })

            # If there is an image, add it as a developer message (OpenAI input_image format)
            if image_b64:
                developer_image_msg = {
                    "role": "developer",
                    "content": [
                        {"type": "input_text", "text": "Screenshot of the 3D viewer after the last action was executed."},
                        {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"}
                    ]
                }
                self.conversation_history.append(developer_image_msg)

            logger.info(
                f"Added function result for {function_name} to conversation history"
            )
            return True
        except Exception as e:
            logger.error(f"\n\n\nError adding function result: {str(e)}\n\n\n")
            return False
