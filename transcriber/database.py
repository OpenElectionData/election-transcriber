import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError

from transcriber.app_config import DEFAULT_USER, DB_CONN

engine = create_engine(DB_CONN, 
                       convert_unicode=True, 
                       server_side_cursors=True)

db_session = scoped_session(sessionmaker(bind=engine,
                                         autocommit=False,
                                         autoflush=False))

Base = declarative_base()

def init_db(sess=None, eng=None):
    import transcriber.models
    Base.metadata.create_all(bind=engine)

    if DEFAULT_USER:
        datastore = transcriber.models.SecurityUserDatastore(db_session, 
                                                             transcriber.models.User,
                                                             transcriber.models.Role)
        name = DEFAULT_USER['name']
        email = DEFAULT_USER['email']
        password = DEFAULT_USER['password']
        datastore.create_user(email=email, password=password, name=name)
        datastore.commit()
