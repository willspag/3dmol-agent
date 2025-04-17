# 1) create and activate an isolated Conda env
conda create -n 3dmol‑flask python=3.11 -y
conda activate 3dmol‑flask

# 2) grab the minimal deps
#    (they’re not all on conda‑forge, so we still use pip here)
pip install flask flask-socketio eventlet selenium pytest

# optional: pin them for reproducibility
pip freeze > requirements.txt

# 3) run the server
python app.py                 # open http://127.0.0.1:5000 in a browser

# 4) in a second terminal (same env) run the tests
pytest -q