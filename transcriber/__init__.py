from flask import Flask
from transcriber.views import views
from transcriber.models import bcrypt
from transcriber.auth import auth, login_manager

def create_app():
    app = Flask(__name__)
    app.config.from_object('transcriber.app_config')
    app.register_blueprint(views)
    app.register_blueprint(auth)

    login_manager.init_app(app)
    bcrypt.init_app(app)
    
    return app
