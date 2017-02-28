from flask_bcrypt import Bcrypt
from sqlalchemy import Integer, String, Boolean, Column, Table, ForeignKey, \
    DateTime, text, Text, or_, LargeBinary, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import synonym, backref, relationship
from flask.ext.security import UserMixin, RoleMixin
from flask.ext.security.utils import md5
from werkzeug.local import LocalProxy
from flask import current_app
from datetime import datetime
from transcriber.database import db
import json
import ast

_security = LocalProxy(lambda: current_app.extensions['security'])

flask_bcrypt = Bcrypt()

class WorkTable(db.Model):
    __tablename__ = 'work_table'
    key = Column(String, primary_key=True)
    return_value = Column(JSONB)
    work_value = Column(LargeBinary)
    traceback = Column(Text)
    task_name = Column(String(255))
    updated = Column(DateTime(timezone=True))
    claimed = Column(Boolean, server_default=text('FALSE'))
    cleared = Column(Boolean, server_default=text('TRUE'))
    completed = Column(Boolean, server_default=text('FALSE'))

    def __repr__(self):
        return '<WorkTable {0}>'.format(str(self.key))

class DocumentCloudImage(db.Model):
    __tablename__ = 'document_cloud_image'
    id = Column(Integer, primary_key=True)
    image_type = Column(String)
    fetch_url = Column(String)
    dc_project = Column(String)
    dc_id = Column(String, unique=True)
    hierarchy = Column(String)
    is_page_url = Column(Boolean)
    is_current = Column(Boolean)

    def __repr__(self):
        return '<DocumentCloudImage %r>' % self.fetch_url

    @classmethod
    def get_id_by_url(cls, url):
        return db.session.query(cls).filter(cls.fetch_url == url).first().id

    @classmethod
    def grab_relevant_images(cls, project_name, hierarchy_filter=None):
        # this only grabs image urls without page numbers

        if hierarchy_filter:
            hierarchy_filter = ast.literal_eval(json.loads(hierarchy_filter))

        doc_list = [row for row in db.session.query(cls)\
                        .filter(cls.dc_project == project_name)\
                        .filter(cls.is_page_url == False)
                        .all()]
        if hierarchy_filter:
            doc_list = [row for row in doc_list if string_start_match(row.hierarchy, hierarchy_filter)]
        return doc_list

    @classmethod
    def grab_relevant_image_pages(cls, project_name, hierarchy_filter):
        # this only grabs image urls with page numbers

        hierarchy_filter = ast.literal_eval(json.loads(hierarchy_filter)) \
                               if hierarchy_filter else None

        doc_list = [row for row in db.session.query(cls)\
                        .filter(cls.dc_project == project_name)\
                        .filter(cls.is_page_url == True)
                        .all()]
        if hierarchy_filter:
            doc_list = [row for row in doc_list \
                            if string_start_match(row.hierarchy, hierarchy_filter)]

        return doc_list

def string_start_match(full_string, match_strings):
    for match_string in match_strings:
        if match_string in full_string:
            return True
    return False

class ImageTaskAssignment(db.Model):
    __tablename__ = 'image_task_assignment'
    id = Column(Integer, primary_key=True)
    image_id = Column(String, ForeignKey('document_cloud_image.dc_id'))
    image = relationship('DocumentCloudImage', backref='taskassignments')
    form_id = Column(Integer, ForeignKey('form_meta.id'))
    checkout_expire = Column(DateTime(timezone=True))
    view_count = Column(Integer, server_default=text('0'))
    is_complete = Column(Boolean, default=False)

    def __repr__(self):
        return '<ImageTask %r %r>' % (self.image_id, self.form_id)

    @classmethod
    def count_images(cls, task_id):
        return db.session.query(cls)\
                .filter(cls.form_id == task_id)\
                .count()


    @classmethod
    def is_task_complete(cls, task_id):

        not_complete = db.session.query(cls)\
                .filter(cls.form_id == task_id)\
                .filter(cls.is_complete == False)\
                .first()
        if not_complete:
            return False
        else:
            return True

    @classmethod
    def get_completed_images_by_task(cls, task_id):
        return [row.image for row in db.session.query(cls)\
                                    .filter(cls.form_id == task_id)\
                                    .filter(cls.is_complete == True)\
                                    .order_by(cls.id)\
                                    .all()]

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
    def conflict_query(cls, task_id):

        table_name = db.session.bind.execute(text('''
            SELECT table_name FROM form_meta
            WHERE id = :form_id
        '''), form_id=task_id).first().table_name

        data_table = Table(table_name,
                           MetaData(),
                           autoload=True,
                           autoload_with=db.session.bind)

        skip_cols = [
            'date_added',
            'transcriber',
            'id',
            'image_id',
            'transription_status'
        ]

        select_cols = [c.name for c in data_table.columns
                       if c.name not in skip_cols]

        having = ' OR '.join(['array_length(array_agg(DISTINCT "{}"), 1) > 1'.format(c)
                              for c in select_cols])

        return '''
              SELECT image_id FROM "{data_table}"
              WHERE transcription_status NOT LIKE '%_deleted'
              GROUP BY image_id
              HAVING ({having})
        '''.format(data_table=table_name, having=having)


    @classmethod
    def get_conflict_images_by_task(cls, task_id):
        conflict = '''
            SELECT dc.*
            FROM document_cloud_image AS dc
            JOIN (
                {conflict_query}
            ) AS conflict
              ON dc.dc_id = conflict.image_id
            JOIN image_task_assignment AS ita
              ON dc.dc_id = ita.image_id
            WHERE ita.form_id = :form_id
        '''.format(conflict_query=cls.conflict_query(task_id))

        return [i for i in db.session.bind.execute(text(conflict), 
                                                   form_id=task_id)]

    @classmethod
    def get_task_progress(cls, task_id):
        progress_dict = {}
        reviewer_count = db.session.query(FormMeta).get(task_id).reviewer_count
        if reviewer_count == None: # clean this up
            reviewer_count = 1

        engine = db.session.bind

        doc_counts = '''
            SELECT
              COUNT(*) AS count,
              is_complete
            FROM image_task_assignment
            WHERE form_id = :task_id
            GROUP BY is_complete
        '''

        doc_counts = list(engine.execute(text(doc_counts),
                                         task_id=task_id))

        docs_total = 0
        docs_done = 0

        for row in doc_counts:

            docs_total += row.count

            if row.is_complete:
                docs_done += row.count

        in_prog = '''
            SELECT COUNT(*) AS count
            FROM image_task_assignment
            WHERE form_id = :task_id
              AND view_count > 0
              AND view_count < :reviewer_count
        '''

        conflict = '''
            SELECT COUNT(*) AS count
            FROM (
              {conflict_query}
            ) As conflict
        '''.format(conflict_query=cls.conflict_query(task_id))

        unseen = '''
            SELECT COUNT(*) AS count
            FROM image_task_assignment
            WHERE form_id = :task_id
              AND view_count = 0
        '''

        q_args = {
            'task_id': task_id,
            'reviewer_count': reviewer_count
        }

        docs_inprog = engine.execute(text(in_prog), **q_args).first().count
        docs_conflict = engine.execute(text(conflict), **q_args).first().count
        docs_unseen = engine.execute(text(unseen), **q_args).first().count
        
        # Total number of reviews that will need to happen
        reviews_total = (docs_total * reviewer_count)

        # Total number of reviews that have happened
        reviews_complete = (reviews_total - docs_inprog)

        progress_dict['docs_total'] = docs_total
        progress_dict['reviews_total'] = reviews_total

        progress_dict['reviews_done_ct'] = reviews_complete
        progress_dict['reviews_done_perc'] = percentage(reviews_complete, reviews_total)

        progress_dict['docs_done_ct'] = docs_done
        progress_dict['docs_done_perc'] = percentage(docs_done, docs_total)
        progress_dict['docs_inprog_ct'] = docs_inprog
        progress_dict['docs_inprog_perc'] = percentage(docs_inprog, docs_total)
        progress_dict['docs_conflict_ct'] = docs_conflict
        progress_dict['docs_conflict_perc'] = percentage(docs_conflict, docs_total)
        progress_dict['docs_unseen_ct'] = docs_unseen
        progress_dict['docs_unseen_perc'] = percentage(docs_unseen, docs_total)

        # hacky fix for progress bar chart rounding down percentages
        remainder = 100 - progress_dict['docs_done_perc'] - progress_dict['docs_inprog_perc'] - progress_dict['docs_conflict_perc'] - progress_dict['docs_unseen_perc']
        if remainder > 0:
            if progress_dict['docs_done_perc'] >= progress_dict['docs_inprog_perc'] and progress_dict['docs_done_perc'] > 0:
                progress_dict['docs_done_perc'] += remainder
            elif progress_dict['docs_inprog_perc'] > 0:
                progress_dict['docs_inprog_perc'] += remainder

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

    @classmethod
    def grab_active_table_names(cls):
        return [row.table_name for row in db.session.query(cls)\
                        .filter(or_(FormMeta.status != 'deleted', FormMeta.status == None))\
                        .all()]

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
    if int1 == 0:
        return 0
    if int2 > 0:
        percentage = int(float(int1)/float(int2)*100)
        if percentage == 0 and int1 > 0:
            percentage = 1

        return percentage
    else:
        return None
