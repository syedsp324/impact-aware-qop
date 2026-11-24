"""python -m app  → starts the web app on http://localhost:8000"""
import sys, webbrowser, threading
import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    threading.Timer(2.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    uvicorn.run("app.server:app", host="127.0.0.1", port=port)
