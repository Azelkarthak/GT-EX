from .app import app

def run():
    app.run(port=5002, debug=False, use_reloader=False)
