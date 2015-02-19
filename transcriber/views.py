from flask import Blueprint, make_response, request, render_template, \
    url_for, send_from_directory, session as flask_session, redirect
import json
import os
from flask_security.decorators import login_required
from flask_security.core import current_user
from transcriber.app_config import UPLOAD_FOLDER
from werkzeug import secure_filename
from transcriber.models import FormMeta, FormSection, FormField
from transcriber.database import engine, db_session
from transcriber.helpers import slugify
from flask_wtf import Form
from wtforms import TextField
from wtforms.validators import DataRequired
from datetime import datetime
from transcriber.app_config import TIME_ZONE
from sqlalchemy import Table, Column, MetaData, String, Boolean, \
        Integer, DateTime, Date, text
from uuid import uuid4

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

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@views.route('/')
def index():
    tasks = db_session.query(FormMeta).all()
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
            existing_columns = set([c.name for c in table.columns \
                    if c.name not in ['id', 'user', 'date_added']])
            add_columns = new_columns - existing_columns
            for column in add_columns:
                field = [f for f in form_meta.fields if f.slug == unicode(column)][0]
                sql_type = SQL_DATA_TYPE[field.data_type]
                alt = 'ALTER TABLE "{0}" ADD COLUMN {1} {2}'\
                        .format(form_meta.table_name, field.slug, sql_type)
                with engine.begin() as conn:
                    conn.execute(alt)
           
            # Commenting this for now since switching data types is tricky

            #for column in existing_columns:
            #    field = [f for f in form_meta.fields if f.slug == unicode(column)][0]
            #    col = getattr(table.c, column)
            #    dt = DATA_TYPE[field.data_type]
            #    if col.type != dt:
            #        sql_type = SQL_DATA_TYPE[field.data_type]
            #        alt = 'ALTER TABLE "{0}" ALTER COLUMN {1} TYPE {2}'\
            #                .format(form_meta.table_name, field.slug, sql_type)
            #        conn = engine.connect()
            #        trans = conn.begin()
            #        try:
            #            conn.execute(alt)
            #            conn.commit()
            #        except Exception:
            #            trans.rollback()
            #            uu = unicode(uuid4()).rsplit('-', 1)[1]
            #            column_name = '{0}_{1}'.format(field.slug, uu)
            #            alt = 'ALTER TABLE "{0}" ADD COLUMN "{1}" {2}'\
            #                    .format(form_meta.table_name, column_name, sql_type)
            #            conn.execute(alt)
            #            field.slug = column_name
            #            db_session.add(field)
        else:
            form_meta.table_name = '{0}_{1}'.format(
                    unicode(uuid4()).rsplit('-', 1)[1], 
                    form_meta.slug)[:60]
            cols = [
                Column('date_added', DateTime(timezone=True), 
                    server_default=text('CURRENT_TIMESTAMP')),
                Column('user', String),
                Column('id', Integer, primary_key=True)
            ]
            for field in form_meta.fields:
                dt = DATA_TYPE.get(field.data_type, String)
                if field.data_type  == 'datetime':
                    dt = DateTime(timezone=True)
                cols.append(Column(field.slug, dt))
            table = Table(form_meta.table_name, metadata, *cols)
            table.create(bind=engine)
            db_session.add(form_meta)
            db_session.commit()
    next_section_index = 2
    next_field_indexes = {1: 2}
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
        next_field_indexes = {f[0]: f[1] for f in \
                engine.execute(text(sel), form_id=form_meta.id)}
    return render_template('form-creator.html', 
                           form_meta=form_meta,
                           next_section_index=next_section_index,
                           next_field_index=next_field_indexes)

@views.route('/get-next-section/<int:form_id>/')
def get_next_section(form_id):
    sel = ''' 
        SELECT 
            s.index as section_index
        FROM form_meta as m
        JOIN form_section as s
            ON m.id = s.form_id
        WHERE m.id = :form_id
        ORDER BY section_index DESC
        LIMIT 1
    '''
    section_index = engine.execute(text(sel), form_id=form_id).first()
    r = {'section_index': section_index.section_index + 1}
    resp = make_response(json.dumps(r))
    resp.headers['Content-Type'] = 'application/json'
    return resp

@views.route('/get-next-field/<int:form_id>/<int:section_index>/')
def get_next_field(form_id, section_index):
    sel = '''
        SELECT 
            f.index 
        FROM form_meta AS m 
        JOIN form_section AS s 
            ON m.id = s.form_id 
        JOIN form_field AS f 
            ON s.id = f.section_id 
        WHERE m.id = :form_id 
            AND s.index = :section_index
        ORDER BY f.index DESC
        LIMIT 1
    '''
    field_index = engine.execute(text(sel), 
                                 form_id=form_id, 
                                 section_index=section_index).first()
    r = {'field_index': field_index.index + 1}
    resp = make_response(json.dumps(r))
    resp.headers['Content-Type'] = 'application/json'
    return resp
    

@views.route('/uploads/<filename>')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@views.route('/viewer/')
def viewer():
    return render_template('viewer.html')
