from transcriber.app_config import AWS_KEY, AWS_SECRET
from boto.s3.connection import S3Connection
import re
from unicodedata import normalize
from wtforms.form import Form
from wtforms.fields import StringField
from wtforms.validators import DataRequired
from transcriber.models import FormMeta, FormField, User
from transcriber.database import db
from flask import url_for
from sqlalchemy import text, or_


def slugify(text, delim=u'_'):
    if text:
        text = str(text)
        punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.:;]+')
        result = []
        for word in punct_re.split(text.lower()):
            word = normalize('NFKD', word).encode('ascii', 'ignore')
            if word:
                result.append(word)
        return str(delim.join([r.decode('utf-8') for r in result]))
    else: # pragma: no cover
        return text

# given several transcriptions, returns a final representation (or none if it can't be reconciled)

# given all rows, produce pretty rows to display in html table
# this is used to display transcriptions on the user transcriptions page (user view)
# includes a delete link to delete a transcription
def pretty_user_transcriptions(t_header, rows_all, task_id, user_name):
    num_cols = len(rows_all[0])

    # 4 cols per field: fieldname/fieldname_blank/fieldname_not_legible/fieldname_altered
    cpf = 4
    # transcription field start index (first 5 fields are meta info abt transcription)
    t_col_start = 6

    meta_h = ['image id', 'date added', 'id']
    field_h = []
    for h in t_header[t_col_start::cpf]:
        f_slug = h[0]
        field = FormField.query.filter(FormField.form_id == task_id).filter(FormField.slug == f_slug).first().as_dict()
        field_h.append(field["name"])
    # meta fields + transcription fields + space for delete button
    header = meta_h+field_h+[""]

    transcriptions = [header]
    for row in rows_all:
        row = list(row)

        image_id = row[5]
        image_url = row[1]
        image_link = "<a href='"+image_url+"' target='blank'>"+str(image_id)+"</a>"

        transcription_id = row[4]
        row_pretty = [image_link, row[2], transcription_id]

        row_transcribed = [row[i:i + cpf] for i in range(t_col_start+2, num_cols, cpf)] # transcribed fields
        for field in row_transcribed:
            field_pretty = str(field[0])
            if field[1]:
                field_pretty = field_pretty+'<i class="fa fa-times"></i>'
            if field[2]:
                field_pretty = field_pretty+'<i class="fa fa-question"></i>'
            if field[3]:
                field_pretty = field_pretty+'<i class="fa fa-exclamation-triangle"></i>'
            row_pretty.append(field_pretty)
        # adding a link to delete
        delete_html = '<a href="/delete-transcription/?user='+user_name+'&transcription_id='+str(transcription_id)+'&task_id='+str(task_id)+'"><i class="fa fa-trash-o"></i></a>'
        row_pretty.append(delete_html)
        transcriptions.append(row_pretty)

    return transcriptions


# given all rows, produce pretty rows to display in html table
# this is used to display transcriptions on the 'review' transcriptions' page
# colors rows based on transcription status & includes a delete link to delete a transcription
def pretty_task_transcriptions(t_header, rows_all, task_id, img_statuses, row_filter):
    num_cols = len(rows_all[0])

    # 4 cols per field: fieldname/fieldname_blank/fieldname_not_legible/fieldname_altered
    cpf = 4
    # transcription field start index (first 5 fields are meta info abt transcription)
    t_col_start = 5

    meta_h = ['image id', 'date added', 'source','id', 'transcriber', ''] # include source hierarchy?
    field_h = []

    for f_slug in t_header[t_col_start::cpf]:
        field = FormField.query.filter(FormField.form_id == task_id).filter(FormField.slug == f_slug).first().as_dict()
        field_h.append(field["name"])
    # meta fields + transcription fields + space for delete button
    
    header = meta_h + field_h

    transcriptions = []
    for row in rows_all:
        row = list(row)

        image_id = row[0]
        image_url = row[1]
        image_link = "<a href='{0}' target='_blank'>{1}</a>".format(image_url, image_id)

        transcription_date = row[3].strftime("%Y-%m-%d %H:%M:%S")
        dt_formatted = "<span class='text-xs'>{}</span>".format(transcription_date)
        src_formatted = "<span class='text-xs'>{}</span>".format(row[2])

        transcription_id = row[5]
        user_name = row[4]
        user_link = '<a href="/user/?user={0}" target="_blank">{0}</a>'.format(user_name)
        row_pretty = [image_link, dt_formatted, src_formatted, transcription_id, user_link]

        # adding a link to delete, link to transcribe
        delete_url = url_for('views.delete_transcription', 
                             user=user_name, 
                             transcription_id=transcription_id, 
                             task_id=task_id, 
                             next='task')

        delete_template = '<a title="Delete transcription {t_id}" href="{d_url}"><i class="fa fa-trash-o fa-fw"></i></a>'
        delete_html = delete_template.format(t_id=transcription_id, d_url=delete_url)

        edit_url = url_for('views.transcribe', 
                           task_id=task_id, 
                           image_id=image_id, 
                           supercede=transcription_id)
        
        edit_template = '<a title="Edit transcription {t_id}" href="{e_url}"><i class="fa fa-pencil fa-fw"></i></a>'
        transcribe_html = edit_template.format(t_id=transcription_id, e_url=edit_url)

        row_pretty.append(delete_html+transcribe_html)


        row_transcribed = [row[i:i + cpf] for i in range(t_col_start+3, num_cols, cpf)] # transcribed fields
        
        if not row_filter:
            include_row = True
        else:
            include_row = False

        for field_group in row_transcribed:
            value, blank, not_legible, altered = field_group

            if blank:
                if row_filter == 'blank':
                    include_row = True
                value = 'Blank <i class="fa fa-times fa-fw"></i>'

            if not_legible:
                if row_filter == 'illegible':
                    include_row = True
                value = 'Not Legible <i class="fa fa-question fa-fw"></i>'
            
            if altered:
                if row_filter == 'altered':
                    include_row = True
                value = 'Altered <i class="fa fa-exclamation-triangle fa-fw"></i>'
            
            row_pretty.append(value)

        # TODO: a less hacky & more elegant way to get image task assignment status
        cls = ''
        for s in img_statuses:
            if image_id in [i.id for i in img_statuses[s]]:
                cls = s

        if row_filter=='conflict' and cls=='conflict':
            include_row = True
        if row_filter=='irrelevant' and row[8]:
            include_row = True

        if include_row:
            transcriptions.append((cls, row_pretty))

    return (header, transcriptions)


# given a username, returns user info & user activity
def get_user_activity(user_name):

    user_transcriptions = []
    user_row = db.session.query(User)\
                .filter(User.name == user_name)\
                .first()
    
    if user_row:
        user = {
        'id': user_row.id,
        'name': user_row.name,
        'detail': user_row.email
        }
    else:
        user = {
        'id': None,
        'name': user_name,
        'detail': "Anonymous Transcriber"
        }

    all_tasks = db.session.query(FormMeta)\
            .filter(or_(FormMeta.status != 'deleted', 
                        FormMeta.status == None)).all()

    engine = db.session.bind

    for task in all_tasks:
        task_info = task.as_dict()
        table_name = task_info['table_name']

        q = ''' 
                SELECT * from (SELECT id, fetch_url from document_cloud_image) i
                JOIN "{0}" t 
                ON (i.id = t.image_id)
                WHERE transcriber = '{1}' and transcription_status = 'raw'
            '''.format(table_name, user['name'])
        h = ''' 
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{0}'
        '''.format(table_name)

        with engine.begin() as conn:
            t_header = conn.execute(text(h)).fetchall()
            rows_all = conn.execute(text(q)).fetchall()

        if len(rows_all) > 0:
            transcriptions = pretty_user_transcriptions(t_header, rows_all, task_info["id"], user['name'])
            user_transcriptions.append((task_info, transcriptions))

    return (user, user_transcriptions)

def getTranscriptionSelect(transcribed_fields):
    switches = []
    
    value_states = [
        ('Blank', 'blank',), 
        ('Illegible', 'not_legible',), 
        ('Altered', 'altered',),
    ]
    
    cases = []
    for field in transcribed_fields:
        
        ending = field.rsplit('_', 1)[1]
        
        if ending in ['blank', 'legible', 'altered']:
            continue

        switches = []
        
        for value, state in value_states:
            switch = """
                WHEN "{field}_{state}" = TRUE 
                THEN '{value}'
            """.format(field=field, 
                       state=state, 
                       value=value)

            switches.append(switch)

        case = '''
            CASE 
              {0} 
            ELSE "{1}"::VARCHAR
            END AS "{1}"
        '''.format(' '.join(switches), field)
        
        cases.append(case)
    
    return ', '.join(cases)
