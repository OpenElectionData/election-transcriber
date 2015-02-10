from transcriber.database import Base, db_session as session
from flask_bcrypt import Bcrypt
from sqlalchemy import Integer, String, Boolean, Column, Table, ForeignKey
from sqlalchemy.orm import synonym, backref, relationship
from flask.ext.security import UserMixin, RoleMixin
from flask.ext.security.utils import md5
from flask.ext.security.datastore import Datastore, UserDatastore
from werkzeug.local import LocalProxy
from flask import current_app

_security = LocalProxy(lambda: current_app.extensions['security'])

bcrypt = Bcrypt()

class SecurityDatastore(Datastore):
    def __init__(self, session):
        self.session = session

    def commit(self):
        self.session.commit()

    def put(self, model):
        self.session.add(model)
        return model
    
    def delete(self, model):
        self.session.delete(model)

class SecurityUserDatastore(SecurityDatastore, UserDatastore):
    def __init__(self, session, user_model, role_model):
        SecurityDatastore.__init__(self, session)
        UserDatastore.__init__(self, user_model, role_model)

    def get_user(self, identifier):
        if self._is_numeric(identifier):
            return self.session.query(self.ser_model).get(identifier)
        for attr in get_identity_attributes():
            query = getattr(self.user_model, attr).ilike(identifier)
            rv = self.session.query(self.user_model).filter(query).first()
            if rv is not None:
                return rv

    def _is_numeric(self, value):
        try:
            int(value)
        except ValueError:
            return False
        return True
    
    def find_user(self, **kwargs):
        return self.session.query(self.user_model).filter_by(**kwargs).first()
    
    def find_role(self, role):
        return self.session.query(self.role_model).filter_by(name=role).first()

class TaskMeta(Base):
    __tablename__ = 'task_meta'
    id = Column(Integer, primary_key=True)

    def __repr__(self):
        return '<TaskMeta %r>' % self.id

roles_users = Table('roles_users', Base.metadata,
        Column('user_id', Integer(), ForeignKey('ndi_user.id')),
        Column('role_id', Integer(), ForeignKey('ndi_role.id')))

class Role(Base, RoleMixin):
    __tablename__ = 'ndi_role'
    id = Column(Integer(), primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)

    def __eq__(self, other):
        return (self.name == other or
                self.name == getattr(other, 'name', None))
    
    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.name)

class User(Base, UserMixin):
    __tablename__ = 'ndi_user'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    _password = Column('password', String, nullable=False)
    roles = relationship('Role', secondary=roles_users, 
                            backref=backref('users', lazy='dynamic')) 
    def __repr__(self): # pragma: no cover
        return '<User %r>' % self.name

    def _get_password(self):
        return self._password
    
    def _set_password(self, value):
        self._password = bcrypt.generate_password_hash(value)

    password = property(_get_password, _set_password)
    password = synonym('_password', descriptor=password)

    def __init__(self, name, email, password):
        self.name = name
        self.password = password
        self.email = email

    @classmethod
    def get_by_username(cls, name):
        return session.query(cls).filter(cls.name == name).first()

    @classmethod
    def check_password(cls, name, value):
        user = cls.get_by_username(name)
        if not user: # pragma: no cover
            return False
        return bcrypt.check_password_hash(user.password, value)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    def get_auth_token(self):
        data = [str(self.id), md5(self.password)]
        return _security.remember_token_serializer.dumps(data)
