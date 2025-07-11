from .app import app

def run():
    app.run(port=5001, debug=False, use_reloader=False)