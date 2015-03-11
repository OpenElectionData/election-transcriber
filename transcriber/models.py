from transcriber.database import Base, db_session as session
from flask_bcrypt import Bcrypt
from sqlalchemy import Integer, String, Boolean, Column, Table, ForeignKey, \
    DateTime, text, Text
from sqlalchemy.orm import synonym, backref, relationship
from flask.ext.security import UserMixin, RoleMixin
from flask.ext.security.utils import md5
from flask.ext.security.datastore import Datastore, UserDatastore
from werkzeug.local import LocalProxy
from flask import current_app
from datetime import datetime

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

class Image(Base):
    __tablename__ = 'image'
    id = Column(Integer, primary_key=True)
    view_count = Column(Integer, default=0)
    image_type = Column(String)
    fetch_url = Column(String)
    form_id = Column(Integer, ForeignKey('form_meta.id'))
    form = relationship('FormMeta', 
                backref=backref('images', cascade="all, delete-orphan"))

    def __repr__(self):
        return '<Image %r>' % self.fetch_url

class TaskGroup(Base):
    __tablename__ = 'task_group'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(Text)
    date_added = Column(DateTime(timezone=True), 
            server_default=text('CURRENT_TIMESTAMP'))
    last_update = Column(DateTime(timezone=True), onupdate=datetime.now)
    
    def __repr__(self):
        return '<TaskGroup %r>' % self.id

    def simple_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        d['task_count'] = len(self.tasks)
        return d
    
    def as_dict(self):
        base_d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        base_d['tasks'] = []
        for task in self.tasks:
            base_d['tasks'].append(task.as_dict())
        return base_d

class FormMeta(Base):
    __tablename__ = 'form_meta'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(Text)
    slug = Column(String)
    status = Column(String)
    index = Column(Integer)
    date_added = Column(DateTime(timezone=True), 
            server_default=text('CURRENT_TIMESTAMP'))
    last_update = Column(DateTime(timezone=True), onupdate=datetime.now)
    sample_image = Column(String)
    table_name = Column(String)
    image_view_count = Column(Integer)
    task_group_id = Column(Integer, ForeignKey('task_group.id'))
    task_group = relationship('TaskGroup', backref=backref('tasks', 
                cascade="all, delete-orphan"))

    def __repr__(self):
        return '<FormMeta %r>' % self.id

    def as_dict(self):
        base_d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        base_d['sections'] = []
        for section in self.sections:
            base_d['sections'].append(section.as_dict())
        base_d['task_group'] = None
        if self.task_group:
            base_d['task_group'] = self.task_group.simple_dict()
        return base_d

class FormSection(Base):
    __tablename__ = 'form_section'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    slug = Column(String)
    index = Column(Integer)
    status = Column(String)
    form_id = Column(Integer, ForeignKey('form_meta.id'))
    form = relationship('FormMeta', backref=backref('sections', 
                cascade="all, delete-orphan"))

    def __repr__(self):
        return '<FormSection %r>' % self.name
    
    def as_dict(self):
        base_d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        base_d['fields'] = []
        for field in self.fields:
            base_d['fields'].append(field.as_dict())
        return base_d

class FormField(Base):
    __tablename__ = 'form_field'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    slug = Column(String)
    index = Column(Integer)
    status = Column(String)
    data_type = Column(String)
    section_id = Column(Integer, ForeignKey('form_section.id'))
    section = relationship('FormSection', backref=backref('fields', 
                cascade="all, delete-orphan"))
    form_id = Column(Integer, ForeignKey('form_meta.id'))
    form = relationship('FormMeta', backref=backref('fields', 
                cascade="all, delete-orphan"))

    def __repr__(self):
        return '<FormField %r>' % self.name

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

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
    active = Column(Boolean, default=True)
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
        return self.active

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    def get_auth_token(self):
        data = [str(self.id), md5(self.password)]
        return _security.remember_token_serializer.dumps(data)
