import re
from unicodedata import normalize
from collections import OrderedDict
import itertools

from wtforms.form import Form
from wtforms.fields import StringField
from wtforms.validators import DataRequired
from transcriber.models import FormMeta, FormField, User
from transcriber.database import db
from flask import url_for
from sqlalchemy import Table, MetaData, text, or_


def slugify(text, delim=u'_', truncate=False):
    if text:
        text = str(text)
        punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.:;]+')
        result = []
        for word in punct_re.split(text.lower()):
            word = normalize('NFKD', word).encode('ascii', 'ignore')
            if word:
                result.append(word)
        slug = str(delim.join([r.decode('utf-8') for r in result]))

        if truncate:
            return slug[:40]

        return slug

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

    slug_map = {f.slug: f.name for f in FormField.query.filter(FormField.form_id == task_id)}

    for f_slug in t_header[t_col_start::cpf]:
        field_h.append(slug_map[f_slug])
    # meta fields + transcription fields + space for delete button

    header = meta_h + field_h

    slug_header = {}

    for slug, name in slug_map.items():
        slug_header[name] = slug

    transcriptions = []

    skip_cols = [
        'date_added',
        'image_id',
        'transcriber',
        'id',
        'fetch_url',
        'hierarchy',
        'transcription_status',
        'flag_irrelevant'
    ]

    for row in rows_all:
        transcription_date = row['date_added'].strftime("%Y-%m-%d %H:%M:%S")

        user_link = url_for('views.user', user=row['transcriber'])

        delete_url = url_for('views.delete_transcription',
                             user=row['transcriber'],
                             transcription_id=row['id'],
                             task_id=task_id,
                             next='task')

        edit_url = url_for('views.transcribe',
                           task_id=task_id,
                           image_id=row['image_id'],
                           supercede=row['id'])

        row_pretty = {
            'image_id': row['image_id'],
            'date_added': transcription_date,
            'source': row['fetch_url'],
            'transcription_id': row['id'],
            'user_link': user_link,
            'user_name': row['transcriber'],
            'delete_url': delete_url,
            'edit_url': edit_url,
            'status': img_statuses.get(row['image_id'], 'unseen'),
            'flag_irrelevant': row['flag_irrelevant'],
        }

        def grouper(x):
            return x[0].replace('_blank', '')\
                       .replace('_not_legible', '')\
                       .replace('_altered', '')

        if not row_filter:
            include_row = True
        else:
            include_row = False

        for field_name, field_group in itertools.groupby(row.items(), key=grouper):

            if field_name in skip_cols:
                continue

            field_group = OrderedDict(field_group)


            value = field_group[field_name]
            blank = field_group[field_name + '_blank']
            not_legible = field_group[field_name + '_not_legible']
            altered = field_group[field_name + '_altered']

            if blank:
                if row_filter == 'blank':
                    include_row = True
                value = 'Blank <i class="fa fa-times fa-fw"></i>'

            elif not_legible:
                if row_filter == 'illegible':
                    include_row = True
                value = 'Not Legible <i class="fa fa-question fa-fw"></i>'

            elif altered:
                if row_filter == 'altered':
                    include_row = True
                value = 'Altered <i class="fa fa-exclamation-triangle fa-fw"></i>'

            row_pretty[field_name] = value

        if row_filter == 'conflict' and row_pretty['status'] == 'conflict':
            include_row = True

        if row['flag_irrelevant']:
            include_row = True
            value = 'Irrelevant <i class="fa fa-ban"></i>'

        if include_row:
            transcriptions.append(row_pretty)

    return (header, slug_header, transcriptions)


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
                SELECT * FROM image AS i
                JOIN "{0}" AS t
                  ON i.id = t.image_id
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

def getTranscribedImages(table_name, limit=None, offset=None):

    engine = db.session.bind

    table = Table(table_name,
                  MetaData(),
                  autoload=True,
                  autoload_with=engine)

    t_header = [c.name for c in table.columns if c.name != 'image_id']
    columns = ', '.join(['t."{}"'.format(c) for c in t_header])

    q = '''
        SELECT
          i.id AS image_id,
          i.fetch_url,
          i.hierarchy,
          {columns}
        FROM image AS i
        JOIN "{table_name}" AS t
          ON i.id = t.image_id
        WHERE t.transcription_status = 'raw'
        ORDER BY i.id, t.id
    '''.format(columns=columns,
               table_name=table_name,
               limit=limit,
               offset=offset)

    if limit or offset:
        q = '{q} LIMIT {limit} OFFSET {offset}'.format(q=q,
                                                       limit=limit,
                                                       offset=offset)

    with engine.begin() as conn:
        rows_all = [OrderedDict(r) for r in conn.execute(text(q))]

    return t_header, rows_all
