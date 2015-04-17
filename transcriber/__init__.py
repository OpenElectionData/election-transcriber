from flask import Flask
from transcriber.views import views
from transcriber.models import User, Role, SecurityUserDatastore, bcrypt
from transcriber.auth import auth, csrf, LoginForm, RegisterForm
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
    security.init_app(app, 
                      datastore, 
                      login_form=LoginForm, 
                      confirm_register_form=RegisterForm)

    mail.init_app(app)
    csrf.init_app(app)
    # login_manager.init_app(app)
    bcrypt.init_app(app)

    @app.template_filter('format_number')
    def format_number(s): # pragma: no cover
        if s:
            return '{:,}'.format(s)
        return s

    @app.template_filter('format_date')
    def format_date(s, fmt='%H:%M%p %b %d, %Y'): # pragma: no cover
        if s:
            return s.strftime(fmt)
        else:
            return '0'
    
    @app.template_filter('format_date_sort')
    def format_date_sort(s, fmt='%Y%m%d%H%M'): # pragma: no cover
        if s:
            return s.strftime(fmt)
        else:
            return '0'
    
    return app
