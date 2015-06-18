from transcriber import create_app
import os
from transcriber.models import User, Role
from flask.ext.security.utils import encrypt_password
from flask.ext.security import SQLAlchemyUserDatastore
from sqlalchemy.exc import IntegrityError
from transcriber.database import db

def init_db():

    fake_app = create_app()

    with fake_app.test_request_context():

        datastore = SQLAlchemyUserDatastore(db, User, Role)


        print "\n** ADDING ROLES **"
        for role in ['admin', 'manager']:
            try:
                print "adding role '%s'" %role
                datastore.create_role(name=role, description=role)
                datastore.commit()
                print "   ...OK"
            except IntegrityError, r:
                print "   '%s' role already exists" % role
                db.session.rollback()

        print "\n** ADDING USERS **"
        users = [fake_app.config['ADMIN_USER'], fake_app.config['MANAGER_USER'], fake_app.config['CLERK_USER']]
        for user in users:
            if user:
                name = user['name']
                email = user['email']
                role = user['role']
                password = user['password']
                try:
                    print "adding user '%s'" % name
                    password = encrypt_password(password)
                    datastore.create_user(email=email, 
                                          password=password, 
                                          name=name, 
                                          active=True)
                    datastore.commit()
                    print "   ...OK"
                except IntegrityError, e:
                    print "   user '%s' already exists" % name
                    db.session.rollback()

                if role:
                    try:
                        print "adding '%s' role to user '%s'" %(role, name)
                        this_user = db.session.query(User)\
                            .filter(User.name == name).first()
                        this_role = db.session.query(Role).filter(Role.name == role).first()
                        datastore.add_role_to_user(this_user, this_role)
                        datastore.commit()
                        print "   ...OK"
                    except IntegrityError, e:
                        print "   unable to add role '%s' to user '%s'" %(role, name)


    from alembic.config import Config
    from alembic import command
    path = os.path.join(os.path.dirname(__file__), 'alembic.ini')
    alembic_cfg = Config(path)
    command.stamp(alembic_cfg, 'head')

if __name__ == "__main__":
    init_db()
    print "Done!"
