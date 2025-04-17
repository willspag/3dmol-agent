"""
pytest – functional tests for every exposed viewer method.

Prereqs:
    chromedriver + Google Chrome (or change Remote webdriver options)
"""
import os, time, base64, io, pathlib, threading
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service      # NEW
from webdriver_manager.chrome import ChromeDriverManager    # NEW

import app   # the Flask module above

TEST_DIR = pathlib.Path(__file__).parent
IMG_DIR   = TEST_DIR / "test_images"
IMG_DIR.mkdir(exist_ok=True)

# ────────────────────────────────  Start server once  ───────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _server():
    th = threading.Thread(
        target=app.socketio.run,
        kwargs=dict(app=app.app,
                    host="127.0.0.1",
                    port=5000,
                    allow_unsafe_werkzeug=True),   # dev server is fine for tests
        daemon=True)
    th.start()
    time.sleep(3)  # Increased wait time
    yield
    # nothing to teardown – daemon thread exits with pytest


# ────────────────────────────────  Selenium  ────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _driver():
    opts = Options()
    # opts.add_argument("--headless=new") # Removed headless option
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    
    driver.implicitly_wait(10)
    driver.get("http://127.0.0.1:5000")
    
    print("\nPage errors:", driver.get_log('browser'))
    
    import time as _t
    sid = None
    print("Attempting to get Socket.IO SID from browser...")
    for i in range(100): # Increased attempts
        sid = driver.execute_script("""
            console.log('Socket status:', window.socket);
            return window.socket ? window.socket.id : null
        """)
        if sid:
            print(f"Got SID from browser: {sid}")
            app._connected_sid = sid
            break
        _t.sleep(0.3) # Increased sleep
    else:
        print("Failed to get SID from browser.")
        pytest.fail("Browser created no Socket.IO client")
    
    yield driver
    driver.quit()


# ────────────────────────────────  helpers  ─────────────────────────────────────
def save(name: str, png: bytes):
    (IMG_DIR / f"{name}.png").write_bytes(png)


# ────────────────────────────────  tests  ───────────────────────────────────────
def test_load_pdb():
    png = app.load_pdb("1CRN")
    save("01_load_pdb", png)
    assert len(png) > 1000

def test_highlight_hetero():
    app.load_pdb("1HSG")
    png = app.highlight_hetero()
    save("02_highlight_hetero", png)
    assert len(png) > 1000

def test_show_surface():
    app.load_pdb("4FNT")
    png = app.show_surface()
    save("03_surface", png)
    assert len(png) > 1000

@pytest.mark.parametrize("axis,val", [("x",90), ("y",45), ("z",30)])
def test_rotate(axis, val):
    kw = {"x":val,"y":0,"z":0} if axis=="x" else \
         {"x":0,"y":val,"z":0} if axis=="y" else \
         {"x":0,"y":0,"z":val}
    png = app.rotate(**kw)
    save(f"04_rotate_{axis}", png)
    assert len(png) > 1000

def test_zoom():
    png = app.zoom(1.4)
    save("05_zoom", png)
    assert len(png) > 1000

def test_add_box():
    png = app.add_box(center={"x":0,"y":0,"z":0},
                      size={"x":10,"y":10,"z":10})
    save("06_box", png)
    assert len(png) > 1000

def test_set_style():
    png = app.set_style(selection={"chain":"A"},
                        style={"stick":{}, "cartoon":{}})
    save("07_custom_style", png)
    assert len(png) > 1000

def test_reset():
    png = app.reset_view()
    save("08_reset", png)
    assert len(png) > 1000
