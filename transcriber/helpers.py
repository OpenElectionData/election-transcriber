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
        text = unicode(text)
        punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.:;]+')
        result = []
        for word in punct_re.split(text.lower()):
            word = normalize('NFKD', word).encode('ascii', 'ignore')
            if word:
                result.append(word)
        return unicode(delim.join(result))
    else: # pragma: no cover
        return text

# given several transcriptions, returns a final representation (or none if it can't be reconciled)
def reconcile_rows(col_names, table_name, image_id, min_agree):
    engine = db.session.bind

    final_transcription = {}
    for col_name in col_names:
        q = '''
            SELECT "{0}", COUNT(*) as c FROM "{1}" WHERE image_id = {2} GROUP BY "{0}" ORDER BY c DESC
            '''.format( col_name,
                        table_name,
                        image_id
                        )
        with engine.begin() as conn:
            top_result = conn.execute(text(q)).first()
            if int(top_result[1]) >= min_agree:
                final_transcription[col_name] = top_result[0]
            else:
                return None
            
    return final_transcription

# given all rows, produce pretty rows to display in html table
def pretty_transcriptions(t_header, rows_all, task_id):
    num_cols = len(rows_all[0])

    # this code assumes that first 2 cols are info from joined image table,
    # next 4 cols are meta info abt transcription
    # & remaining cols are for fields

    # 4 cols per field: fieldname/fieldname_blank/fieldname_not_legible/fieldname_altered
    cpf = 4

    meta_h = []
    field_h = []
    for h in t_header[:4]:
        meta_f = h[0]
        meta_f = re.sub(r'_', ' ', meta_f) # un-slugify
        meta_h.append(meta_f)
    for h in t_header[5::cpf]:
        f_slug = h[0]
        field = FormField.query.filter(FormField.form_id == task_id).filter(FormField.slug == f_slug).first().as_dict()
        field_h.append(field["name"])
    # move image_id to first col
    meta_h.insert(0, meta_h.pop())
    header = meta_h+field_h

    transcriptions = [header]
    for row in rows_all:
        row = list(row)
        row_pretty = row[2:5] # transcription metadata
        # link for transcriber
        transcriber = row_pretty[1]
        if transcriber:
            row_pretty[1] = "<a href='"+url_for('views.user', user=transcriber)+"'>"+transcriber+"</a>"
        else:
            row_pretty[1] = ""
        # assumes image_id is the 4th metadata col
        image_id = row[5]
        image_url = row[1]
        image_link = "<a href='"+image_url+"' target='blank'>"+str(image_id)+"</a>"
        row_pretty = [image_link]+row_pretty

        row_transcribed = [row[i:i + cpf] for i in range(7, num_cols, cpf)] # transcribed fields
        for field in row_transcribed:
            field_pretty = str(field[0])
            if field[1]:
                field_pretty = field_pretty+'<i class="fa fa-times"></i>'
            if field[2]:
                field_pretty = field_pretty+'<i class="fa fa-question"></i>'
            if field[3]:
                field_pretty = field_pretty+'<i class="fa fa-exclamation-triangle"></i>'
            row_pretty.append(field_pretty)
        transcriptions.append(row_pretty)

    return transcriptions

def pretty_final_transcriptions(t_header, rows_all, task_id):
    num_cols = len(rows_all[0])

    # this code assumes that first 2 cols are info from joined image table,
    # next 4 cols are meta info abt transcription
    # & remaining cols are for fields

    # 4 cols per field: fieldname/fieldname_blank/fieldname_not_legible/fieldname_altered
    cpf = 4
    # transcription field start index (first 5 fields are meta info abt transcription)
    t_col_start = 5

    meta_h = ['image id', 'date added', 'id']
    field_h = []
    for h in t_header[t_col_start::cpf]:
        f_slug = h[0]
        field = FormField.query.filter(FormField.form_id == task_id).filter(FormField.slug == f_slug).first().as_dict()
        field_h.append(field["name"])
    header = meta_h+field_h

    transcriptions = [header]
    for row in rows_all:
        row = list(row)

        image_id = row[5]
        image_url = row[1]
        image_link = "<a href='"+image_url+"' target='blank'>"+str(image_id)+"</a>"
                
        row_pretty = [image_link, row[2], row[4]]

        row_transcribed = [row[i:i + cpf] for i in range(7, num_cols, cpf)] # transcribed fields
        for field in row_transcribed:
            field_pretty = str(field[0])
            if field[1]:
                field_pretty = field_pretty+'<i class="fa fa-times"></i>'
            if field[2]:
                field_pretty = field_pretty+'<i class="fa fa-question"></i>'
            if field[3]:
                field_pretty = field_pretty+'<i class="fa fa-exclamation-triangle"></i>'
            row_pretty.append(field_pretty)
        transcriptions.append(row_pretty)

    return transcriptions

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
                WHERE transcriber = '{1}'
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
            transcriptions = pretty_transcriptions(t_header, rows_all, task_info["id"])
            user_transcriptions.append((task_info, transcriptions))

    return (user, user_transcriptions)
