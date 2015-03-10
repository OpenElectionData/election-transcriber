from flask import Blueprint, make_response, request, render_template, \
    url_for, send_from_directory, session as flask_session, redirect
import json
import os
from flask_security.decorators import login_required
from flask_security.core import current_user
from transcriber.app_config import UPLOAD_FOLDER
from werkzeug import secure_filename
from transcriber.models import FormMeta, FormSection, FormField, Image
from transcriber.database import engine, db_session
from transcriber.helpers import slugify, add_images
from flask_wtf import Form
from transcriber.dynamic_form import TranscriberIntegerField as IntegerField, \
    TranscriberDateTimeField as DateTimeField, TranscriberDateField as DateField, \
    BlankValidator
from wtforms.fields import BooleanField, StringField
from datetime import datetime
from transcriber.app_config import TIME_ZONE
from sqlalchemy import Table, Column, MetaData, String, Boolean, \
        Integer, DateTime, Date, text, and_, or_
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm import aliased
from uuid import uuid4
from operator import attrgetter, itemgetter
from itertools import groupby

views = Blueprint('views', __name__)

ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg'])

DATA_TYPE = {
    'boolean': Boolean,
    'string': String,
    'integer': Integer,
    'datetime': DateTime,
    'date': Date
}

SQL_DATA_TYPE = {
    'boolean': 'BOOLEAN',
    'string': 'VARCHAR',
    'integer': 'INTEGER',
    'datetime': 'TIMESTAMP WITH TIME ZONE',
    'date': 'DATE'
}

FORM_TYPE = {
    'boolean': BooleanField,
    'string': StringField,
    'integer': IntegerField,
    'datetime': DateTimeField,
    'date': DateField
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@views.route('/')
def index():
    tasks = db_session.query(FormMeta)\
            .filter(or_(FormMeta.status != 'deleted', 
                        FormMeta.status == None)).all()
    return render_template('index.html', tasks=tasks)

@views.route('/about/')
def about():
    return render_template('about.html')

@views.route('/upload/',methods=['GET', 'POST'])
@login_required
def upload():
    image = None
    if request.method == 'POST':
        uploaded = request.files['input_file']
        if uploaded and allowed_file(uploaded.filename):
            image = secure_filename(uploaded.filename)
            uploaded.save(os.path.join(UPLOAD_FOLDER, image))
            image = url_for('views.uploaded_image', filename=image)
            flask_session['image'] = image
            flask_session['image_type'] = image.rsplit('.', 1)[1].lower()
            return redirect(url_for('views.form_creator'))
    return render_template('upload.html', image=image)

@views.route('/delete-part/', methods=['DELETE'])
@login_required
def delete_part():
    part_id = request.form.get('part_id')
    part_type = request.form.get('part_type')
    r = {
        'status': 'ok',
        'message': ''
    }
    status_code = 200
    if not part_id:
        r['status'] = 'error'
        r['message'] = 'Need the ID of the component to remove'
        status_code = 400
    elif not part_type:
        r['status'] = 'error'
        r['message'] = 'Need the type of component to remove'
        status_code = 400
    else:
        thing = None
        if part_type == 'section':
            thing = FormSection
        elif part_type == 'field':
            thing = FormField
        elif part_type == 'form':
            thing = FormMeta
        if thing:
            it = db_session.query(thing).get(part_id)
            if it:
                it.status = 'deleted'
                db_session.add(it)
                db_session.commit()
            else:
                r['status'] = 'error'
                r['message'] = '"{0}" is not a valid component ID'.format(part_id)
                status_code = 400
        else:
            r['status'] = 'error'
            r['message'] = '"{0}" is not a valid component type'.format(part_type)
            status_code = 400
    response = make_response(json.dumps(r), status_code)
    response.headers['Content-Type'] = 'application/json'
    return response

@views.route('/form-creator/', methods=['GET', 'POST'])
@login_required
def form_creator():
    form_meta = FormMeta()
    if request.args.get('form_id'):
        form = db_session.query(FormMeta).get(request.args['form_id'])
        if form:
            form_meta = form
            flask_session['image'] = form.sample_image
            flask_session['image_type'] = form.sample_image.rsplit('.', 1)[1].lower()
    if not flask_session.get('image'):
        return redirect(url_for('views.upload'))
    if request.method == 'POST':
        name = request.form['task_name']
        form_meta.name = name
        form_meta.slug = slugify(name)
        form_meta.last_update = datetime.now().replace(tzinfo=TIME_ZONE)
        form_meta.sample_image = flask_session['image']
        db_session.add(form_meta)
        db_session.commit()
        section_fields = {}
        sections = {}
        field_datatypes = {}
        for k,v in request.form.items():
            parts = k.split('_')
            if 'section' in parts:
                if len(parts) == 2:
                    # You've got yourself a section
                    section_idx = k.split('_')[-1]
                    section = db_session.query(FormSection)\
                            .filter(FormSection.index == section_idx)\
                            .filter(FormSection.form == form_meta)\
                            .first()
                    if not section:
                        section = FormSection(name=v, 
                                              slug=slugify(v),
                                              index=section_idx,
                                              form=form_meta)
                    else:
                        section.name = v
                        section.slug = slugify(v)
                    sections[section_idx] = section
                if len(parts) == 5:
                    # You've got yourself a field data type
                    field_idx = k.split('_')[-1]
                    section_idx = k.split('_')[2]
                    try:
                        field_datatypes[section_idx][field_idx] = v
                    except KeyError:
                        field_datatypes[section_idx] = {field_idx: v}
                if len(parts) == 4:
                    # You've got yourself a field
                    field_idx = k.split('_')[-1]
                    section_idx = k.split('_')[1]
                    field = db_session.query(FormField)\
                            .filter(FormField.index == field_idx)\
                            .filter(FormSection.index == section_idx)\
                            .filter(FormField.form == form_meta)\
                            .first()
                    if not field:
                        section = db_session.query(FormSection)\
                                .filter(FormSection.index == section_idx)\
                                .filter(FormSection.form == form_meta)\
                                .first()
                        field = FormField(name=v,
                                          slug=slugify(v),
                                          index=field_idx,
                                          form=form_meta,
                                          section=section)
                    else:
                        field.name = v
                        field.slug = slugify(v)
                    db_session.add(field)
                    try:
                        section_fields[section_idx].append(field)
                    except KeyError:
                        section_fields[section_idx] = [field]
        for section_id, section in sections.items():
            section.fields = section_fields[section_id]
            for field in section.fields:
                field.data_type = field_datatypes[section_id][unicode(field.index)]
                field.section = section
                db_session.add(field)
            db_session.add(section)
        db_session.commit()
        db_session.refresh(form_meta, ['fields', 'table_name'])
        
        metadata = MetaData()
        if form_meta.table_name:
            table = Table(form_meta.table_name, metadata, 
                          autoload=True, autoload_with=engine)
            new_columns = set([f.slug for f in form_meta.fields])
            existing_columns = set([c.name for c in table.columns])
            add_columns = new_columns - existing_columns
            for column in add_columns:
                field = [f for f in form_meta.fields if f.slug == unicode(column)][0]
                sql_type = SQL_DATA_TYPE[field.data_type]
                alt = 'ALTER TABLE "{0}" ADD COLUMN {1} {2}'\
                        .format(form_meta.table_name, field.slug, sql_type)
                blank = 'ALTER TABLE "{0}" ADD COLUMN {1}_blank boolean'\
                        .format(form_meta.table_name, field.slug)
                not_legible = '''
                    ALTER TABLE "{0}" 
                    ADD COLUMN {1}_not_legible boolean
                    '''.format(form_meta.table_name, field.slug)
                with engine.begin() as conn:
                    conn.execute(alt)
                    conn.execute(blank)
                    conn.execute(not_legible)
        else:
            form_meta.table_name = '{0}_{1}'.format(
                    unicode(uuid4()).rsplit('-', 1)[1], 
                    form_meta.slug)[:60]
            cols = [
                Column('date_added', DateTime(timezone=True), 
                    server_default=text('CURRENT_TIMESTAMP')),
                Column('transcriber', String),
                Column('id', Integer, primary_key=True),
                Column('image_id', Integer)
            ]
            for field in form_meta.fields:
                dt = DATA_TYPE.get(field.data_type, String)
                if field.data_type  == 'datetime':
                    dt = DateTime(timezone=True)
                cols.append(Column(field.slug, dt))
                cols.append(Column('{0}_blank'.format(field.slug), Boolean))
                cols.append(Column('{0}_not_legible'.format(field.slug), Boolean))
            table = Table(form_meta.table_name, metadata, *cols)
            table.create(bind=engine)
            db_session.add(form_meta)
            db_session.commit()
            add_images(form_meta.id)
        return redirect(url_for('views.index'))
    next_section_index = 2
    next_field_indicies = {1: 2}
    if form_meta.id:
        sel = ''' 
            SELECT 
                s.index + 1 as section_index
            FROM form_meta as m
            JOIN form_section as s
                ON m.id = s.form_id
            WHERE m.id = :form_id
            ORDER BY section_index DESC
            LIMIT 1
        '''
        next_section_index = engine.execute(text(sel), 
                                form_id=form_meta.id).first()[0]
        sel = ''' 
            SELECT 
                s.index as section_index,
                MAX(f.index) AS field_index
            FROM form_meta as m
            JOIN form_section as s
                ON m.id = s.form_id
            JOIN form_field as f
                ON s.id = f.section_id
            WHERE m.id = :form_id
            GROUP BY s.id
        '''
        next_field_indicies = {f[0]: f[1] for f in \
                engine.execute(text(sel), form_id=form_meta.id)}
    form_meta = form_meta.as_dict()
    if form_meta['sections']:
        for section in form_meta['sections']:
            section['fields'] = sorted(section['fields'], key=itemgetter('index'))
        form_meta['sections'] = sorted(form_meta['sections'], key=itemgetter('index'))
    return render_template('form-creator.html', 
                           form_meta=form_meta,
                           next_section_index=next_section_index,
                           next_field_index=next_field_indicies)

@views.route('/transcribe/', methods=['GET', 'POST'])
def transcriber():
    if not request.args.get('task_id'):
        return redirect(url_for('views.index'))
    section_sq = db_session.query(FormSection)\
            .filter(or_(FormSection.status != 'deleted', 
                        FormSection.status == None))\
            .order_by(FormSection.index)\
            .subquery()
    field_sq = db_session.query(FormField)\
            .filter(or_(FormField.status != 'deleted', 
                        FormField.status == None))\
            .order_by(FormField.index)\
            .subquery()
    task = db_session.query(FormMeta)\
            .join(section_sq)\
            .join(field_sq)\
            .filter(FormMeta.id == request.args['task_id'])\
            .first()
    form = Form
    task_dict = task.as_dict()
    task_dict['sections'] = []
    bools = []
    for section in sorted(task.sections, key=attrgetter('index')):
        section_dict = {'name': section.name, 'fields': []}
        for field in sorted(section.fields, key=attrgetter('index')):
            message = u'If the "{0}" field is either blank or not legible, \
                    please mark the appropriate checkbox'.format(field.name)
            validators = [BlankValidator(message=message)]
            if field.data_type == 'boolean':
                bools.append(field.slug)
                ft = FORM_TYPE[field.data_type]()
            else:
                if field.data_type == 'string':
                    ft = FORM_TYPE[field.data_type](validators=validators)
                else:
                    ft = FORM_TYPE[field.data_type]()
            setattr(form, field.slug, ft)
            blank = '{0}_blank'.format(field.slug)
            not_legible = '{0}_not_legible'.format(field.slug)
            setattr(form, blank, BooleanField())
            setattr(form, not_legible, BooleanField())
            bools.extend([blank, not_legible])
            section_dict['fields'].append(field)
        task_dict['sections'].append(section_dict)
    if request.method == 'POST':
        form = form(request.form)
        if form.validate():
            ins_args = {
                'transcriber': current_user.name,
                'image_id': flask_session['image_id'],
            }
            for k,v in request.form.items():
                if k != 'csrf_token':
                    ins_args[k] = v
            if not set(bools).intersection(set(ins_args.keys())):
                for f in bools:
                    ins_args[f] = False
            ins = ''' 
                INSERT INTO "{0}" ({1}) VALUES ({2})
            '''.format(task.table_name, 
                       ','.join([f for f in ins_args.keys()]),
                       ','.join([':{0}'.format(f) for f in ins_args.keys()]))
            with engine.begin() as conn:
                conn.execute(text(ins), **ins_args)
            image = db_session.query(Image).get(flask_session['image_id'])
            image.view_count += 1
            db_session.add(image)
            db_session.commit()
    else:
        form = form(meta={})

    # This is where we put in the image. 
    # Right now it's just always loading the example image
    # flask_session['image'] = task.sample_image
    # flask_session['image_type'] = task.sample_image.rsplit('.', 1)[1].lower()
    image = db_session.query(Image)\
            .filter(Image.form_id == task.id)\
            .order_by(Image.view_count)\
            .first()
    flask_session['image'] = image.fetch_url
    flask_session['image_type'] = image.image_type
    flask_session['image_id'] = image.id
    return render_template('transcribe.html', form=form, task=task_dict)

@views.route('/uploads/<filename>')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@views.route('/viewer/')
def viewer():
    return render_template('viewer.html')
