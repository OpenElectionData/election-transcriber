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

views = Blueprint('views', __name__)

ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg'])

DATA_TYPE = {
    'boolean': Boolean,
    'string': String,
    'integer': Integer,
    'datetime': DateTime,
    'date': Date
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@views.route('/')
def index():
    return render_template('index.html')

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
            return redirect(url_for('views.task_creator'))
    return render_template('upload.html', image=image)

@views.route('/task-creator/', methods=['GET', 'POST'])
@login_required
def task_creator():
    if not flask_session.get('image'):
        return redirect(url_for('views.upload'))
    form_meta = None
    if request.method == 'POST':
        name = request.form['task_name']
        form_meta = FormMeta(name=name, slug=slugify(name),
            last_update=datetime.now().replace(tzinfo=TIME_ZONE))
        db_session.add(form_meta)
        db_session.commit()
        section_fields = {}
        sections = {}
        field_datatypes = {}
        for k,v in request.form.items():
            parts = k.split('_')
            if 'section' in parts:
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
                    field = FormField(name=v,
                                      slug=slugify(v),
                                      index=field_idx,
                                      form=form_meta)
                    db_session.add(field)
                    try:
                        section_fields[section_idx].append(field)
                    except KeyError:
                        section_fields[section_idx] = [field]
                if len(parts) == 2:
                    # You've got yourself a section
                    section_idx = k.split('_')[-1]
                    section = FormSection(name=v, 
                                          slug=slugify(v),
                                          index=section_idx,
                                          form=form_meta)
                    sections[section_idx] = section
        for section_id, section in sections.items():
            section.fields = section_fields[section_id]
            for field in section.fields:
                field.data_type = field_datatypes[section_id][field.index]
            db_session.add(section)
        db_session.commit()
        db_session.refresh(form_meta)
        metadata = MetaData()
        cols = [
            Column('date_added', DateTime(timezone=True), 
                server_default=text('CURRENT_TIMESTAMP')),
            Column('user', String),
            Column('id', Integer, primary_key=True)
        ]
        for field in form_meta.fields:
            dt = DATA_TYPE[field.data_type]
            if dt == 'datetime':
                dt = DateTime(timezone=True)
            cols.append(Column(field.slug, dt))
        table = Table(form_meta.slug, metadata, *cols)
        table.create(bind=engine)
    return render_template('task-creator.html', form_meta=form_meta)

@views.route('/uploads/<filename>')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@views.route('/viewer/')
def viewer():
    return render_template('viewer.html')
