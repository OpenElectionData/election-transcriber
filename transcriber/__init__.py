from flask import Flask
from transcriber.views import views
from transcriber.models import bcrypt, User, Role, SecurityUserDatastore
from transcriber.auth import auth, csrf
from transcriber.database import db_session
from flask_mail import Mail
from flask.ext.security import Security

mail = Mail()
security = Security()

def create_app():
    app = Flask(__name__)
    app.config.from_object('transcriber.app_config')
    app.register_blueprint(views)
    app.register_blueprint(auth)
    
    datastore = SecurityUserDatastore(db_session, User, Role)
    security.init_app(app, datastore)

    mail.init_app(app)
    csrf.init_app(app)
    # login_manager.init_app(app)
    # bcrypt.init_app(app)
    
    return app
