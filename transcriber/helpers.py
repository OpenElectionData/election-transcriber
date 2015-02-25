from transcriber.app_config import AWS_KEY, AWS_SECRET
from boto.s3.connection import S3Connection
import re
from unicodedata import normalize
from wtforms.form import Form
from wtforms.fields import StringField
from wtforms.validators import DataRequired
from transcriber.models import Image, FormMeta
from transcriber.database import db_session

# Temporary function to populate incoming tasks with some canned images.
def add_images(form_id):
    conn = S3Connection(AWS_KEY, AWS_SECRET)
    bucket = conn.get_bucket('election-images')
    base = 'http://election-images.s3.amazonaws.com'
    for thing in bucket.list():
        fetch_url = '{0}/{1}'.format(base, thing.name)
        image = Image(fetch_url=fetch_url, 
                      image_type='pdf', 
                      form_id=form_id)
        db_session.add(image)
    db_session.commit()

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
