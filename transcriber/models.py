from flask_bcrypt import Bcrypt
from sqlalchemy import Integer, String, Boolean, Column, Table, ForeignKey, \
    DateTime, text, Text
from sqlalchemy.orm import synonym, backref, relationship
from flask.ext.security import UserMixin, RoleMixin
from flask.ext.security.utils import md5
from werkzeug.local import LocalProxy
from flask import current_app
from datetime import datetime
from transcriber.database import db

_security = LocalProxy(lambda: current_app.extensions['security'])

flask_bcrypt = Bcrypt()


class DocumentCloudImage(db.Model):
    __tablename__ = 'document_cloud_image'
    id = Column(Integer, primary_key=True)
    image_type = Column(String)
    fetch_url = Column(String)

    def __repr__(self):
        return '<DocumentCloudImage %r>' % self.fetch_url

    @classmethod
    def get_id_by_url(cls, url):
        return db.session.query(cls).filter(cls.fetch_url == url).first().id

class ImageTaskAssignment(db.Model):
    __tablename__ = 'image_task_assignment'
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey('document_cloud_image.id'))
    form_id = Column(Integer, ForeignKey('form_meta.id'))
    checkout_expire = Column(DateTime(timezone=True))
    view_count = Column(Integer, default=0)

    def __repr__(self):
        return '<ImageTask %r %r>' % (self.image_id, self.form_id)

class TaskGroup(db.Model):
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

class FormMeta(db.Model):
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
    reviewer_count = Column(Integer)
    deadline = Column(DateTime(timezone=True), onupdate=datetime.now)
    image_location = Column(String)

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

class FormSection(db.Model):
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

class FormField(db.Model):
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

roles_users = Table('roles_users', db.Model.metadata,
        Column('user_id', Integer(), ForeignKey('ndi_user.id')),
        Column('role_id', Integer(), ForeignKey('ndi_role.id')))

class Role(db.Model, RoleMixin):
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

class User(db.Model, UserMixin):
    __tablename__ = 'ndi_user'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=False, unique=True)
    confirmed_at = Column(DateTime)
    password = Column('password', String, nullable=False)
    active = Column(Boolean, default=False)
    roles = relationship('Role', secondary=roles_users, 
                            backref=backref('users', lazy='dynamic')) 
    def __repr__(self): # pragma: no cover
        return '<User %r>' % self.name

    @classmethod
    def get_by_username(cls, name):
        return session.query(cls).filter(cls.name == name).first()

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
