from transcriber import create_app

app = create_app()

if __name__ == "__main__":
    import sys
    try:
        port = int(sys.argv[1])
    except (IndexError, ValueError):
        port = 5000

    app.config['DEBUG_TB_ENABLED'] = True

    from flask_debugtoolbar import DebugToolbarExtension
    toolbar = DebugToolbarExtension(app)

    app.run(debug=True, port=port)
