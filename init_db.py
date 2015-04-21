from transcriber.app_config import DB_CONN
from transcriber import create_app

def init_db(sess=None, eng=None):
    import os
    from transcriber.models import User, Role
    from transcriber import db
    from flask.ext.security.utils import encrypt_password
    from flask.ext.security import SQLAlchemyUserDatastore
    from sqlalchemy.exc import IntegrityError

    fake_app = create_app()
    
    with fake_app.app_context():

        db.create_all()

        datastore = SQLAlchemyUserDatastore(db, User, Role)

        try:
            print "adding roles"
            for role in ['admin']:
                datastore.create_role(name=role, description=role)
            datastore.commit()
        except IntegrityError, e:
            print "Admin role already exists"
            db.session.rollback()

        print "adding users"
        users = [fake_app.config['DEFAULT_USER'], fake_app.config['CLERK_USER']]
        for user in users:
            try:
                if user:
                    print "adding ", user['name']
                    name = user['name']
                    email = user['email']
                    password = encrypt_password(user['password'])
                    datastore.create_user(email=email, 
                                          password=password, 
                                          name=name, 
                                          active=True)
                    datastore.commit()
            except IntegrityError, e:
                print "user already exists"
                db.session.rollback()

        try:
            print "adding roles to users"
            default_user = db.session.query(User)\
                .filter(User.name == fake_app.config['DEFAULT_USER']['name']).first()
            admin_role = db.session.query(Role).filter(Role.name == 'admin').first()
            datastore.add_role_to_user(default_user, admin_role)
            datastore.commit()
        except IntegrityError, e:
            print "Failed to add roles to users"


    from alembic.config import Config
    from alembic import command
    path = os.path.join(os.path.dirname(__file__), 'alembic.ini')
    alembic_cfg = Config(path)
    command.stamp(alembic_cfg, 'head')

if __name__ == "__main__":
    init_db()
    print "Done!"
