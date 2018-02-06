from flask import Flask
from transcriber.views import views
from transcriber.models import User, Role, flask_bcrypt
from transcriber.database import db
from transcriber.auth import auth, csrf, LoginForm, RegisterForm
from flask_mail import Mail
from flask.ext.security import Security, SQLAlchemyUserDatastore
from flask.ext.sqlalchemy import SQLAlchemy

mail = Mail()
security = Security()

sentry = None
try:
  from raven.contrib.flask import Sentry
  from transcriber.app_config import SENTRY_DSN
  if SENTRY_DSN:
    sentry = Sentry(dsn=SENTRY_DSN)
except ImportError:
  pass
except KeyError:
  pass

def create_app():
    app = Flask(__name__)
    app.config.from_object('transcriber.app_config')
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['DB_CONN']

    app.register_blueprint(views)
    app.register_blueprint(auth)

    db.init_app(app)

    datastore = SQLAlchemyUserDatastore(db, User, Role)
    security.init_app(app,
                      datastore,
                      login_form=LoginForm,
                      confirm_register_form=RegisterForm)

    mail.init_app(app)
    csrf.init_app(app)
    flask_bcrypt.init_app(app)


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

    app.config['sentry'] = None

    if sentry:
        sentry.init_app(app)
        app.config['sentry'] = sentry

    app.jinja_env.filters['zip'] = zip

    return app
