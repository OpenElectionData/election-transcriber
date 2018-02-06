import ast
import json
from operator import itemgetter
from io import StringIO
from datetime import datetime

from flask import Blueprint, make_response, request, render_template, \
    url_for, send_from_directory, session as flask_session, redirect, flash, \
    jsonify
from flask_security.decorators import login_required, roles_required
from flask_security.core import current_user
from flask.ext.principal import Permission, RoleNeed

from sqlalchemy import Table, MetaData, text, or_

from transcriber.app_config import UPLOAD_FOLDER
from transcriber.models import FormMeta, FormSection, FormField, \
    Image, ImageTaskAssignment, TaskGroup
from transcriber.database import db
from transcriber.helpers import pretty_task_transcriptions, \
    get_user_activity, getTranscriptionSelect, getTranscribedImages

from transcriber.transcription_helpers import TranscriptionManager, checkinImages
from transcriber.form_creator_helpers import FormCreatorManager
from transcriber.tasks import ImageUpdater, update_from_s3
from transcriber.auth import csrf

from documentcloud import DocumentCloud

views = Blueprint('views', __name__)

ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg'])


# Create a permission for manager & admin users
manager_permission = Permission(RoleNeed('admin'), RoleNeed('manager'))


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@views.route('/')
def index():
    tasks = db.session.query(FormMeta)\
            .filter(or_(FormMeta.status != 'deleted',
                        FormMeta.status == None))\
            .order_by(FormMeta.task_group_id, FormMeta.index)\
            .all()
            # order by due date here
    t = []
    groups = []
    has_complete_tasks = False
    has_inprog_tasks = False

    for task in tasks:
        # make the progress bar depend on reviews (#docs * #reviewers) instead of documents?
        task_dict = task.as_dict()
        reviewer_count = task_dict['reviewer_count']
        task_id = task_dict['id']

        progress_dict = ImageTaskAssignment.get_task_progress(task_id)

        if task.task_group_id not in groups and progress_dict['docs_done_ct'] < progress_dict['docs_total']:
            is_top_task = True
            groups.append(task.task_group_id)
        else:
            is_top_task = False

        if progress_dict['docs_inprog_ct'] > 0:
            has_inprog_tasks = True
        else:
            has_complete_tasks = True

        t.append([task, progress_dict, is_top_task])

    return render_template('index.html',
                           tasks=t,
                           has_inprog_tasks=has_inprog_tasks,
                           has_complete_tasks=has_complete_tasks)

@views.route('/about/')
def about():
    return render_template('about.html')

@views.route('/create-task/', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def create_task():

    engine = db.session.bind
    result = engine.execute('SELECT DISTINCT election_name FROM image')

    election_list = [thing[0] for thing in result]

    if request.method == 'POST':
        flask_session['election_name'] = request.form['election_name']
        hierarchy_filters = []

        for key, value in request.form.items():
            if key.startswith('hierarchy_'):
                hierarchy_filters.append([h.replace('hierarchy_', '')
                                          for h in key.split(',')])

        flask_session['hierarchy_filters'] = hierarchy_filters

        return redirect(url_for('views.form_creator'))

    return render_template('create-task.html', election_list=election_list)


@views.route('/hierarchy/')
@login_required
@roles_required('admin')
def hierarchy():

    election_name = request.args['election_name']
    hierarchy_elements = request.args.get('hierarchy')
    engine = db.session.bind

    geographies = '''
        SELECT DISTINCT hierarchy[1:1]
        FROM image
        WHERE election_name = :election_name
    '''

    params = {
        'election_name': election_name
    }

    if hierarchy_elements:

        hierarchy_length = '''
            SELECT array_length(hierarchy, 1) AS length
            FROM image
        '''

        next_index = engine.execute(hierarchy_length).first().length
        elements = hierarchy_elements.split(',')

        if next_index > len(elements):
            next_index = len(elements) + 1

            geographies = '''
                SELECT DISTINCT hierarchy[1:{next}]
                FROM image
                WHERE 1=1
            '''.format(next=next_index)

            for index, element in enumerate(elements):
                geographies = '''
                    {geographies}
                    AND hierarchy[{index}] = :element_{index}
                '''.format(geographies=geographies, index=index + 1)

                params['element_{}'.format(index + 1)] = element
        else:
            geographies = []


    if geographies:
        geographies = '{} ORDER BY hierarchy'.format(geographies)
        geographies = [g[0] for g in engine.execute(text(geographies), **params)]

    return jsonify(hierarchy=geographies)


@views.route('/delete-part/', methods=['DELETE'])
@login_required
@roles_required('admin')
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
            it = db.session.query(thing).get(part_id)
            if it:
                it.status = 'deleted'
                db.session.add(it)
                db.session.commit()
            else:
                r['status'] = 'error'
                r['message'] = '"{0}" is not a valid component ID'.format(part_id)
                status_code = 400
        else:
            r['status'] = 'error'
            r['message'] = '"{0}" is not a valid component type'.format(part_type)
            status_code = 400
    if part_type == 'form':

        with db.session.bind.begin() as conn:
            conn.execute(text('''
                DELETE FROM image_task_assignment
                WHERE form_id = :form_id
            '''), form_id=part_id)

        flash("Task deleted")
    response = make_response(json.dumps(r), status_code)
    response.headers['Content-Type'] = 'application/json'
    return response


@views.route('/delete-transcription/', methods=['GET','POST'])
@login_required
@roles_required('admin')
def delete_transcription():
    transcription_id = request.args.get('transcription_id')
    task_id = request.args.get('task_id')
    username = request.args.get('user')
    next = request.args.get('next')

    transcription_task = TranscriptionManager(task_id,
                                              username=username,
                                              transcription_id=transcription_id)

    transcription_task.getFormMeta()
    image_id = transcription_task.deleteOldTranscription()

    if request.args.get('message') == 'edited':
        flash("Transcription edited: image <strong>%s</strong> by user <strong>%s</strong>" % (image_id, user))
    else:
        flash("Transcription deleted: image <strong>%s</strong> by user <strong>%s</strong>" % (image_id, user))

    if next == 'task':
        return redirect(url_for('views.transcriptions', task_id=task_id))

    return redirect(url_for('views.user', user=user))


@views.route('/form-creator/', methods=['GET', 'POST'])
@login_required
@roles_required('admin')
def form_creator():

    election_name = flask_session.get('election_name')
    hierarchy_filter = flask_session.get('hierarchy_filters')

    if request.args.get('form_id'):
        creator_manager = FormCreatorManager(form_id=request.args.get('form_id'))
    else:
        creator_manager = FormCreatorManager(election_name=election_name,
                                             hierarchy_filter=hierarchy_filter)

    image_url = creator_manager.form_meta.sample_image

    engine = db.session.bind

    if request.method == 'POST':

        creator_manager.updateFormMeta(request.form,
                                       sample_image=image_url)

        creator_manager.saveFormParts()

        updater = ImageUpdater()
        updater.updateImages()

        return redirect(url_for('views.index'))

    if creator_manager.existing_form:
        creator_manager.getNextIndices()

    form_meta = creator_manager.form_meta.as_dict()

    if form_meta['sections']:
        for section in form_meta['sections']:
            section['fields'] = sorted(section['fields'], key=itemgetter('index'))
        form_meta['sections'] = sorted(form_meta['sections'], key=itemgetter('index'))

    return render_template('form-creator.html',
                           form_meta=form_meta,
                           next_section_index=creator_manager.next_section_index,
                           next_field_index=creator_manager.next_field_indices,
                           image_url=image_url,
                           election_name=election_name,
                           hierarchy_filter=hierarchy_filter)


@views.route('/get-task-group/')
@login_required
@roles_required('admin')
def get_task_group():
    term = request.args.get('term')
    where = TaskGroup.name.ilike('%%%s%%' % term)
    base_query = db.session.query(TaskGroup).filter(where)
    names = [{'name': t.name, 'id': str(t.id), 'description': t.description} \
            for t in base_query.all()]
    resp = make_response(json.dumps(names))
    resp.headers['Content-Type'] = 'application/json'
    return resp

@views.route('/edit-task-group/', methods=['GET', 'POST'])
@login_required
@manager_permission.require()
def edit_task_group():
    if not request.args.get('group_id'):
        flash('Group ID is required')
        return redirect(url_for('views.index'))
    if request.method == 'POST':
        form = request.form
        if form['task_array']:
            priorities = ast.literal_eval(form['task_array'])

            save_ok = True
            for i, task_id in enumerate(priorities):
                task = db.session.query(FormMeta).get(int(task_id))
                if task:
                    task.index = i
                    db.session.add(task)
                    db.session.commit()
                else:
                    flash("Error saving priorities")
                    save_ok = False
                    break

            if save_ok:
                flash("Priorities saved")

        else:
            flash("Error saving priorities")

    task_group = db.session.query(TaskGroup).get(request.args['group_id'])
    return render_template('edit-task-group.html',task_group=task_group)

@views.route('/transcribe-intro/<task_id>', methods=['GET', 'POST'])
@login_required
def transcribe_intro(task_id):

    task_id = int(task_id)
    if not task_id:
        return redirect(url_for('views.index'))

    task = db.session.query(FormMeta).get(task_id)
    task_dict = task.as_dict()
    return render_template('transcribe-intro.html', task=task_dict)

@views.route('/transcribe/<task_id>', methods=['GET', 'POST'])
@login_required
def transcribe(task_id):

    task_id = int(task_id)
    if not task_id:
        return redirect(url_for('views.index'))

    engine = db.session.bind

    if current_user.is_anonymous():
        username = request.remote_addr
    else:
        username = current_user.name

    supercede = request.args.get('supercede')
    image_id = request.args.get('image_id')
    edit_mode = False

    if not image_id:
        image_id = request.form.get('image_id')

    transcription_task = TranscriptionManager(task_id,
                                              username=username,
                                              transcription_id=supercede,
                                              image_id=image_id)

    transcription_task.getFormMeta()
    transcription_task.setupDynamicForm()

    if image_id and supercede:
        transcription_task.prepopulateFields()
        edit_mode = True

    checkinImages()

    if request.method == 'POST':

        if transcription_task.validateTranscription(request.form):

            if transcription_task.transcription_id:
                transcription_task.deleteOldTranscription()

            transcription_task.saveTranscription()

            transcription_task.checkComplete()

            if not edit_mode:
                flash("Saved! Let's do another!", "saved")
                return redirect(url_for('views.transcribe', task_id=task_id))
            else:
                flash('New transcription saved!', 'saved')
                return redirect(url_for('views.transcriptions', task_id=task_id))

    transcription_task.getImageTaskAssignment()

    if transcription_task.image_task_assignment == None:

        if transcription_task.isTaskIncomplete(): # if task is done
            flash("Thanks for helping to transcribe '%s'! Want to help out with another?" % transcription_task.task.name)
            return redirect(url_for('views.index'))
        else: # if task is not done
            flash("All images associated with '%s' have been checked out" % transcription_task.task.name)
            return redirect(url_for('views.index'))

    return render_template('transcribe.html',
                           task=transcription_task)

@views.route('/download-transcriptions/', methods=['GET', 'POST'])
@login_required
@manager_permission.require()
def download_transcriptions():
    if not request.args.get('task_id'):
        return redirect(url_for('views.index'))

    task = db.session.query(FormMeta).get(request.args['task_id'])

    engine = db.session.bind

    table = Table(task.table_name,
                  MetaData(),
                  autoload=True,
                  autoload_with=engine)

    common_fields = [
        'date_added',
        'transcriber',
        'id',
        'image_id',
        'transcription_status',
        'flag_irrelevant'
    ]

    dynamic_fields = ['{}'.format(c.name) for c in table.columns \
                          if c.name not in common_fields]

    dynamic_fields_select = getTranscriptionSelect(dynamic_fields)

    copy = '''
        COPY (
            SELECT
              {common},
              i.hierarchy as image_hierarchy,
              i.fetch_url as image_url,
              {dynamic}
            from "{table_name}" as t
            join image as i
            on t.image_id = i.id
            order by t.image_id, transcription_status
        ) TO STDOUT WITH CSV HEADER DELIMITER ','
    '''.format(common=', '.join(['t.{}'.format(f) for f in common_fields]),
               dynamic=dynamic_fields_select,
               table_name=task.table_name)

    engine = db.session.bind

    conn = engine.raw_connection()
    curs = conn.cursor()

    outp = StringIO()
    curs.copy_expert(copy, outp)
    conn.close()

    outp.seek(0)

    resp = make_response(outp.getvalue())
    resp.headers['Content-Type'] = 'text/csv'
    filedate = datetime.now().strftime('%Y-%m-%d')
    resp.headers['Content-Disposition'] = 'attachment; filename=transcriptions_{0}_{1}.csv'.format(task.slug, filedate)
    return resp

@views.route('/transcriptions/', methods=['GET', 'POST'])
@login_required
@manager_permission.require()
def transcriptions():
    if not request.args.get('task_id'):
        return redirect(url_for('views.index'))

    transcriptions_final = None
    header = None
    task_id = request.args.get('task_id')

    task = db.session.query(FormMeta).get(task_id)
    task_dict = task.as_dict()

    task_dict['progress'] = ImageTaskAssignment.get_task_progress(task_id)
    task_dict['image_count'] = ImageTaskAssignment.count_images(task_id)

    table_name = task_dict['table_name']

    t_header, rows_all = getTranscribedImages(table_name)

    images_completed = ImageTaskAssignment.get_completed_images_by_task(task_id)
    images_unseen = ImageTaskAssignment.get_unseen_images_by_task(task_id)
    images_inprog = ImageTaskAssignment.get_inprog_images_by_task(task_id)
    images_conflict = ImageTaskAssignment.get_conflict_images_by_task(task_id)

    rows_all_len = len(rows_all)

    img_statuses = {
        'done': images_completed,
        'inprog': images_inprog,
        'unseen': images_unseen,
        'conflict': images_conflict
    }

    row_filter = request.args.get('filter')

    if len(rows_all) > 0:
        transcription_tbl_header, transcriptions_tbl_rows = \
                pretty_task_transcriptions(t_header,
                                           rows_all[:26],
                                           task_id,
                                           img_statuses,
                                           row_filter)
    else:
        transcription_tbl_header = []
        transcriptions_tbl_rows = []

    return render_template('transcriptions.html',
                            task=task_dict,
                            rows_all_len=rows_all_len,
                            transcription_tbl_header=transcription_tbl_header,
                            transcriptions_tbl_rows=transcriptions_tbl_rows,
                            row_filter=row_filter)


@views.route('/transcription-data/<task_id>/', methods=['POST'])
@csrf.exempt
def transcription_data(task_id):

    limit = request.form['length']
    offset = request.form['start']
    total = request.args['total']

    task = db.session.query(FormMeta).get(task_id)

    t_header, transcribed_images = getTranscribedImages(task.table_name,
                                                        limit=limit,
                                                        offset=offset)

    images_completed = ImageTaskAssignment.get_completed_images_by_task(task_id)
    images_unseen = ImageTaskAssignment.get_unseen_images_by_task(task_id)
    images_inprog = ImageTaskAssignment.get_inprog_images_by_task(task_id)
    images_conflict = ImageTaskAssignment.get_conflict_images_by_task(task_id)

    img_statuses = {
        'done': images_completed,
        'inprog': images_inprog,
        'unseen': images_unseen,
        'conflict': images_conflict
    }

    row_filter = request.args.get('filter')

    if len(transcribed_images) > 0:
        _, transcriptions_tbl_rows = pretty_task_transcriptions(t_header,
                                                                transcribed_images,
                                                                task_id,
                                                                img_statuses,
                                                                row_filter)
    else:
        transcriptions_tbl_rows = []

    rows = []

    for _, row_data in transcriptions_tbl_rows:
        rows.append(row_data)

    resp = {
        'draw': int(request.form['draw']),
        'recordsTotal': total,
        'recordsFiltered': total,
        'data': rows,
    }

    response = make_response(json.dumps(resp))
    response.headers['Content-Type'] = 'application/json'
    return response


@views.route('/all-users/', methods=['GET', 'POST'])
@login_required
@manager_permission.require()
def all_users():

    table_names = FormMeta.grab_active_table_names()

    if table_names:
        # get anonymous transcribers as well as registered users
        sels = ['SELECT transcriber, date_added FROM "{0}" WHERE (transcription_status = \'raw\')'.format(table_name)
                for table_name in table_names]
        sel_all = ' UNION ALL '.join(sels)
        users_t = 'SELECT t.transcriber from ({0}) as t'.format(sel_all)
        users_u = 'SELECT name as transcriber FROM ndi_user'
        all_usernames = users_t+' UNION '+users_u
        all_users = 'SELECT n.transcriber, u.id as user_id, u.email from ({0}) as n LEFT JOIN ndi_user as u on n.transcriber = u.name'.format(all_usernames)
        user_q = 'SELECT u.transcriber, u.user_id, u.email, max(t.date_added) as last_seen, count(t.*) as total_transcriptions from ({0}) as u LEFT JOIN ({1}) as t on u.transcriber = t.transcriber GROUP BY u.transcriber, u.user_id, u.email'.format(all_users, sel_all)
        role_q = 'SELECT ru.user_id, array_agg(r.name) as roles FROM roles_users as ru JOIN ndi_role as r ON ru.role_id = r.id GROUP BY ru.user_id'
        q = 'SELECT u.transcriber, u.email, r.roles, u.total_transcriptions, u.last_seen FROM ({0}) as u LEFT JOIN ({1}) as r ON u.user_id = r.user_id'.format(user_q, role_q)

        engine = db.session.bind
        with engine.begin() as conn:
            user_info = conn.execute(text(q)).fetchall()
    else:
        # get registered users
        user_q = 'SELECT name as transcriber, id as user_id, email, NULL as last_seen, 0 as total_transcriptions FROM ndi_user'
        role_q = 'SELECT ru.user_id, array_agg(r.name) as roles FROM roles_users as ru JOIN ndi_role as r ON ru.role_id = r.id GROUP BY ru.user_id'
        q = 'SELECT u.transcriber, u.email, r.roles, u.total_transcriptions, u.last_seen FROM ({0}) as u LEFT JOIN ({1}) as r ON u.user_id = r.user_id'.format(user_q, role_q)

        engine = db.session.bind
        with engine.begin() as conn:
            user_info = conn.execute(text(q)).fetchall()


    return render_template('all-users.html', user_info=user_info)


@views.route('/user/', methods=['GET', 'POST'])
@login_required
@manager_permission.require()
def user():
    if not request.args.get('user'):
        return redirect(url_for('views.index'))

    user, user_transcriptions = get_user_activity(request.args.get('user'))

    return render_template('user.html', user=user, user_transcriptions = user_transcriptions)


@views.route('/view-activity/', methods=['GET', 'POST'])
@login_required
def view_activity():
    if current_user.is_anonymous():
        username = request.remote_addr
    else:
        username = current_user.name

    user, user_transcriptions = get_user_activity(username)

    return render_template('view-activity.html', user=user, user_transcriptions = user_transcriptions)

@views.route('/uploads/<filename>')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@views.route('/viewer/')
@login_required
def viewer():
    return render_template('viewer.html')

@views.route('/refresh-project/')
@login_required
@manager_permission.require()
def refresh_project():
    project_title = request.args.get('project_title')

    key = update_from_s3.delay(project_title=project_title)

    flask_session['refresh_key'] = key

    response = make_response(json.dumps({'status': 'ok'}))
    response.headers['Content-Type'] = 'application/json'

    return response

@views.route('/check-work/')
@login_required
@manager_permission.require()
def check_work():
    key = flask_session['refresh_key']

    engine = db.session.bind
    complete = engine.execute(text('select completed from work_table where key = :key'), key=key).first()

    result = {'completed': complete.completed}

    if complete.completed == True:
        del flask_session['refresh_key']

    response = make_response(json.dumps(result))
    response.headers['Content-Type'] = 'application/json'
    return response

