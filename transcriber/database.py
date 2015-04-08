import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError

from transcriber.app_config import DEFAULT_USER, CLERK_USER, DB_CONN


engine = create_engine(DB_CONN, 
                       convert_unicode=True, 
                       server_side_cursors=True)

db_session = scoped_session(sessionmaker(bind=engine,
                                         autocommit=False,
                                         autoflush=False))

Base = declarative_base()

def init_db(sess=None, eng=None):
    from transcriber.models import User, Role, SecurityUserDatastore

    Base.metadata.create_all(bind=engine)

    datastore = SecurityUserDatastore(db_session, User, Role)

    try:
        print "adding roles"
        for role in ['admin']:
            datastore.create_role(name=role, description=role)
        datastore.commit()
    except IntegrityError, e:
        print "Admin role already exists"
        db_session.rollback()

    print "adding users"
    for user in [DEFAULT_USER, CLERK_USER]:
        try:
            if user:
                print "adding ", user['name']
                name = user['name']
                email = user['email']
                password = user['password']
                datastore.create_user(email=email, password=password, name=name)
                datastore.commit()
        except IntegrityError, e:
            print "user already exists"
            db_session.rollback()

    try:
        print "adding roles to users"
        default_user = db_session.query(User).filter(User.name == DEFAULT_USER['name']).first()
        admin_role = db_session.query(Role).filter(Role.name == 'admin').first()
        datastore.add_role_to_user(default_user, admin_role)
        datastore.commit()
    except IntegrityError, e:
        print "Failed to add roles to users"


    from alembic.config import Config
    from alembic import command
    path = os.path.join(os.path.dirname(__file__), '..', 'alembic.ini')
    alembic_cfg = Config(path)
    command.stamp(alembic_cfg, 'head')
