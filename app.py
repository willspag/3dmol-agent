"""
Minimal Flask + 3Dmol.js micro-service
Author: ChatGPT
"""
import base64
import io
import os
from pathlib import Path
from typing import Dict, Any

from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, call, ConnectionRefusedError

# ────────────────────────────────  Flask + Socket.IO  ───────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# keep track of the **first** connected viewer (good enough for single-user demo)
_connected_sid: str | None = None

# ────────────────────────────────  HTML template  ───────────────────────────────
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf‑8"/>
<title>3Dmol.js Flask Demo</title>
<!-- socket.io v3 ↔ python-socketio 5.x -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/3.1.3/socket.io.min.js"></script>
<!-- stable 3Dmol from jsDelivr (much more reliable in CI) -->
<script src="https://cdn.jsdelivr.net/npm/3dmol@2.0.3/build/3Dmol-min.js"></script>
<style>
 html,body{margin:0;height:100%;overflow:hidden}
 #viewer{width:100%;height:100%}
 #boxinfo{position:absolute;top:10px;left:10px;
          background:rgba(255,255,255,.85);padding:6px 8px;
          font:12px monospace;border-radius:4px;display:none}
</style>
</head>
<body>
<div id="viewer"></div>
<div id="boxinfo" id="boxinfo"></div>

<script>
 // ────────────────────────  Socket.IO  ───────────────────────────
 const socket = io("http://127.0.0.1:5000", {
     transports: ["polling"],
     upgrade: false,
     reconnection: false        // ← keep the same SID for the whole test run
 });
 window.socket = socket;  // Make explicitly available to window
 socket.on("connect", ()=>console.log("socket connected"));
 socket.on("command", async (payload, cb)=>{
     await exec(payload);                      // run the command
     const png = viewer.pngURI();              // take screenshot
     cb({img: png});                           // return to Python
 });

 // ────────────────────────  create viewer  ────────────────────────
 const viewer = $3Dmol.createViewer("viewer",{backgroundColor:"white"});
 viewer.setViewStyle({style:"outline"});
 viewer.render();

 /* ----------------- helper that maps commands → 3Dmol ---------------- */
 async function exec(p){
     switch(p.name){
        case "load_pdb":
            const url = `https://files.rcsb.org/download/${p.pdb_id}.pdb`;
            const txt = await fetch(url).then(r=>r.text());
            viewer.clear();
            viewer.addModel(txt,"pdb");
            viewer.setStyle({cartoon:{color:"spectrum"}});
            viewer.zoomTo(); break;

        case "highlight_hetero":
            viewer.setStyle({hetflag:true},
                            {stick:{colorscheme:"orangeCarbon"}});
            break;

        case "show_surface":
            viewer.addSurface($3Dmol.SurfaceType.VDW,
                              {opacity:0.8,color:"white"},
                              p.selection||{}); break;

        case "rotate":   viewer.rotate(p.x||0,p.y||0,p.z||0); break;
        case "zoom":     viewer.zoom(p.factor||1.2,1000);     break;

        case "add_box":
            const shap = viewer.addBox({center:p.center,
                                        dimensions:p.size,
                                        wireframe:true,
                                        color:"magenta"});
            const el = document.getElementById("boxinfo");
            el.style.display="block";
            el.textContent = `box center (${p.center.x.toFixed(1)}, `
                            +`${p.center.y.toFixed(1)}, ${p.center.z.toFixed(1)}) `
                            +`size (${p.size.x},${p.size.y},${p.size.z})`;
            break;

        case "set_style":
            viewer.setStyle(p.selection||{}, p.style||{}); break;

        case "reset":    viewer.zoomTo(); break;
     }
     viewer.render();
 }
</script>
</body>
</html>
"""

# ────────────────────────────────  Routes  ──────────────────────────────────────
@app.route("/")
def index():
    """Serve the single-page viewer."""
    return render_template_string(INDEX_HTML)


# ────────────────────────────────  Socket events  ───────────────────────────────
@socketio.on("connect")
def _on_connect(auth):
    global _connected_sid
    if _connected_sid is None:
        _connected_sid = request.sid
        emit("status", {"msg": "registered"})
    else:
        raise ConnectionRefusedError("Only one active viewer allowed.")


@socketio.on("disconnect")
def _on_disconnect(reason):
    global _connected_sid
    if request.sid == _connected_sid:
        _connected_sid = None


# ────────────────────────────────  Python API  ──────────────────────────────────
def _call_viewer(command: str, **kwargs) -> bytes:
    """Internal helper that asks the viewer to run *command* and returns a PNG."""
    if _connected_sid is None:
        raise RuntimeError("No browser viewer connected yet – open / in a tab.")
    print(f"Calling command '{command}' for SID: {_connected_sid}")
    payload: Dict[str, Any] = {"name": command, **kwargs}
    # send RPC and wait (max 15 s)
    res: Dict[str, str] = socketio.call("command", payload,
                                        to=_connected_sid, timeout=15)  # 15 s
    img64: str = res["img"].split(",", 1)[1]      # drop data:image/png;base64,
    return base64.b64decode(img64)


# public helper functions – the ones you'll import & test
def load_pdb(pdb_id: str) -> bytes:              # e.g. "1crn"
    return _call_viewer("load_pdb", pdb_id=pdb_id)

def highlight_hetero() -> bytes:
    return _call_viewer("highlight_hetero")

def show_surface(selection: dict | None = None) -> bytes:
    return _call_viewer("show_surface", selection=selection or {})

def rotate(x=0, y=0, z=0) -> bytes:
    return _call_viewer("rotate", x=x, y=y, z=z)

def zoom(factor: float = 1.2) -> bytes:
    return _call_viewer("zoom", factor=factor)

def add_box(center: dict, size: dict) -> bytes:
    """
    center/size → {'x':…, 'y':…, 'z':…}
    size        → {'x':dx,'y':dy,'z':dz}
    """
    return _call_viewer("add_box", center=center, size=size)

def set_style(selection: dict, style: dict) -> bytes:
    return _call_viewer("set_style", selection=selection, style=style)

def reset_view() -> bytes:
    return _call_viewer("reset")


# ────────────────────────────────  Dev server  ──────────────────────────────────
if __name__ == "__main__":
    print("Open http://127.0.0.1:5000 in a browser, then run tests in another shell")
    socketio.run(app, host="0.0.0.0", port=5000)
