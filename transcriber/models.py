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
    image = relationship('DocumentCloudImage', backref='taskassignments')
    form_id = Column(Integer, ForeignKey('form_meta.id'))
    checkout_expire = Column(DateTime(timezone=True))
    view_count = Column(Integer, default=0)
    is_complete = Column(Boolean, default=False)

    def __repr__(self):
        return '<ImageTask %r %r>' % (self.image_id, self.form_id)

    @classmethod
    def count_images(cls, task_id):
        return db.session.query(cls)\
                .filter(cls.form_id == task_id)\
                .count()

    @classmethod
    def get_unseen_images_by_task(cls, task_id):
        return [row.image for row in db.session.query(cls)\
                                    .filter(cls.form_id == task_id)\
                                    .filter(cls.view_count == 0)\
                                    .order_by(cls.id)\
                                    .all()]

    @classmethod
    def get_inprog_images_by_task(cls, task_id):
        reviewer_count = db.session.query(FormMeta).get(task_id).reviewer_count
        return [row.image for row in db.session.query(cls)\
                                    .filter(cls.form_id == task_id)\
                                    .filter(cls.view_count > 0)\
                                    .filter(cls.view_count < reviewer_count)\
                                    .order_by(cls.id)\
                                    .all()]

    @classmethod
    def get_conflict_images_by_task(cls, task_id):
        reviewer_count = db.session.query(FormMeta).get(task_id).reviewer_count
        return [row.image for row in db.session.query(cls)\
                                    .filter(cls.form_id == task_id)\
                                    .filter(cls.view_count >= reviewer_count)\
                                    .filter(cls.is_complete == False)\
                                    .order_by(cls.id)\
                                    .all()]

    @classmethod
    def get_task_progress(cls, task_id):
        progress_dict = {}
        reviewer_count = db.session.query(FormMeta).get(task_id).reviewer_count
        if reviewer_count == None: # clean this up
            reviewer_count = 1

        # doc counts: total = done + inprog + conflict + unseen
        docs_total = db.session.query(cls)\
                .filter(cls.form_id == task_id)\
                .count()
        docs_done = db.session.query(cls)\
                .filter(cls.form_id == task_id)\
                .filter(cls.is_complete == True)\
                .count()
        docs_inprog = len(cls.get_inprog_images_by_task(task_id))
        docs_conflict = len(cls.get_conflict_images_by_task(task_id))
        unseen = len(cls.get_unseen_images_by_task(task_id))

        reviews_complete = 0
        for i in range(1, reviewer_count):
            n = db.session.query(cls)\
                .filter(cls.form_id == task_id)\
                .filter(cls.view_count == i).count()
            reviews_complete+=n*i
        reviews_complete += docs_done*reviewer_count + docs_conflict*(reviewer_count-1)


        progress_dict['docs_total'] = docs_total 
        progress_dict['reviews_total'] = reviewer_count*docs_total

        progress_dict['reviews_done_ct'] = reviews_complete
        progress_dict['reviews_done_perc'] = percentage(reviews_complete, reviewer_count*docs_total)

        progress_dict['docs_done_ct'] = docs_done
        progress_dict['docs_done_perc'] = percentage(docs_done, docs_total)
        progress_dict['docs_inprog_ct'] = docs_inprog
        progress_dict['docs_inprog_perc'] = percentage(docs_inprog, docs_total)
        progress_dict['docs_conflict_ct'] = docs_conflict
        progress_dict['docs_conflict_perc'] = percentage(docs_conflict, docs_total)
        progress_dict['docs_unseen_ct'] = unseen
        progress_dict['docs_unseen_perc'] = percentage(unseen, docs_total)

        return progress_dict


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
    task_group_id = Column(Integer, ForeignKey('task_group.id'))
    task_group = relationship('TaskGroup', backref=backref('tasks', 
                cascade="all, delete-orphan"))
    reviewer_count = Column(Integer)
    deadline = Column(DateTime(timezone=True), onupdate=datetime.now)
    dc_project = Column(String)
    dc_filter = Column(Text)
    split_image = Column(Boolean)

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



def percentage(int1, int2):
    if int2 > 0:
        percentage = int(float(int1)/float(int2)*100)
        if percentage == 0 and int1 > 0:
            percentage = 1

        return percentage
    else:
        return None
