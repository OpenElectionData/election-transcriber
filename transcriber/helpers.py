from transcriber.app_config import AWS_KEY, AWS_SECRET
from boto.s3.connection import S3Connection
import re
from unicodedata import normalize
from wtforms.form import Form
from wtforms.fields import StringField
from wtforms.validators import DataRequired
from transcriber.models import Image, FormMeta, FormField
from transcriber.database import db
from flask import url_for


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
    for h in t_header[4::cpf]:
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
        row_pretty[1] = "<a href='"+url_for('views.user', user=transcriber)+"'>"+transcriber+"</a>"

        # assumes image_id is the 4th metadata col
        image_id = row[5]
        image_url = row[1]
        image_link = "<a href='"+image_url+"' target='blank'>"+str(image_id)+"</a>"
        row_pretty = [image_link]+row_pretty

        row_transcribed = [row[i:i + cpf] for i in range(6, num_cols, cpf)] # transcribed fields
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
