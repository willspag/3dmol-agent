Please deeply research the DSX protein (specifically PDB ID 7A9G) as a therapeutic target for tuberculosis, and determine the best active site to target for small molecule drug discovery. Conduct extremely thorough research of scientific literature of the best potential active sites to target and the PDB 7A9G crystallography file. Provide numerous sources throughout your findings.

Your job is to create a thorough report on this target and the specific PDB ID 7A9G in order to provide detailed information to another AI model who will be controlling a 3Dmol.js viewer as a protein visualization display of the PDB ID 7A9G protein in order to visually analyze the protein and draw a search box on the protein (to be used as search space arguments provided to autodock vina for high throughput molecular docking) corresponding to the recommendations you provide. Therefore, ensure that your instructions are extremely clear such that the model is able to position the box around your exact recommended active site by only having access to your report, basic custom tools to manipulate the 3dmol.js viewer, and screenshot images of the 3Dmol.js viewer after each each tool call.

To be clear, the model is not able to run 3dmol.js code directly, it only has access to a set of custom tools which it can use, so you must keep these tool limitations in mind when providing your instructions such that the ai will be able to follow your instructions and design your exact recommended search box through access to only your report, these tools, and screenshot images of the updated viewer after each tool call. For reference, below are the tool definitions for all of the model's available tools:

```
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
```
