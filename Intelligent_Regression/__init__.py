from .app import app

def run():
    app.run(port=5000, debug=False, use_reloader=False)
