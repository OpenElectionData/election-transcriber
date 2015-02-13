from flask import Blueprint, make_response, request, render_template, \
    url_for, send_from_directory, session as flask_session, redirect
import json
import os
from flask_security.decorators import login_required
from flask_security.core import current_user
from transcriber.app_config import UPLOAD_FOLDER
from werkzeug import secure_filename
from transcriber.models import TaskMeta, FormSection, FormField
from transcriber.database import engine
from transcriber.helpers import slugify
from flask_wtf import Form
from wtforms import TextField
from wtforms.validators import DataRequired

views = Blueprint('views', __name__)

ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg'])

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
    if request.method == 'POST':
        name = request.form['task_name']
        t = TaskMeta(name=name)
        sections = []
        fields = []
        for k,v in request.form.items():
            parts = set(k.split('_'))
            if set(['section', 'field']).issubset(parts):
                # You've got yourself a field
                fields.append(FormField(name=v, index=k.split('_')[-1]))
            elif set(['section']).issubset(parts):
                # You've got yourself a section
                sections.append(FormSection(name=v, index=k.split('_')[-1]))
        print fields
        print sections
    return render_template('task-creator.html')

@views.route('/uploads/<filename>')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@views.route('/viewer/')
def viewer():
    return render_template('viewer.html')
