from datetime import datetime
import json
import os
import csv

import sqlalchemy as sa

import boto3

from transcriber.app_config import DB_CONN, S3_BUCKET
from transcriber.models import FormMeta, Image, ImageTaskAssignment
from transcriber.queue import queuefunc

engine = sa.create_engine(DB_CONN)

@queuefunc
def update_from_s3(election_name=None, overwrite=False):
    updater = ImageUpdater(overwrite=overwrite)

    if election_name:
        updater.updateElection(election_name)
    else:
        updater.updateAllElections()

    print('complete!')


class ImageUpdater(object):
    def __init__(self, overwrite=False):

        self.this_folder = os.path.abspath(os.path.dirname(__file__))

        self.download_folder = os.path.join(self.this_folder, 'downloads')

        if not os.path.exists(self.download_folder):
            os.mkdir(self.download_folder)

        aws_key, aws_secret_key = self.awsCredentials()

        self.client = boto3.client('s3',
                                   aws_access_key_id=aws_key,
                                   aws_secret_access_key=aws_secret_key)

        self.bucket = S3_BUCKET

        self.download_folder = os.path.join(self.this_folder, 'downloads')
        self.overwrite = overwrite
        self.inserts = []

    def awsCredentials(self):
        creds_path = os.path.join(self.this_folder, '..', 'credentials.csv')

        if not os.path.exists(creds_path):
            raise Exception('Please decrypt s3credentials.csv.gpg into the root folder of the project')

        with open(creds_path) as f:
            reader = csv.reader(f)

            next(reader)

            _, _, aws_key, aws_secret_key, _ = next(reader)

        return aws_key, aws_secret_key

    @property
    def image_upsert(self):

        return '''
            INSERT INTO image (
              id,
              image_type,
              fetch_url,
              election_name,
              hierarchy,
              is_page_url,
              is_current
            ) VALUES (
              :id,
              :image_type,
              :fetch_url,
              :election_name,
              :hierarchy,
              :is_page_url,
              :is_current
            )
            ON CONFLICT (id) DO UPDATE SET
              image_type = :image_type,
              fetch_url = :fetch_url,
              election_name = :election_name,
              hierarchy = :hierarchy,
              is_page_url = :is_page_url,
              is_current = :is_current

        '''

    def updateImages(self):

        forms = '''
            SELECT
              election_name,
              id AS form_id
            FROM form_meta
        '''

        for form in engine.execute(forms):

            insert = '''
                INSERT INTO image_task_assignment (
                  image_id,
                  form_id,
                  is_complete
                )
                SELECT
                  image.id AS image_id,
                  :form_id AS form_id,
                  FALSE AS is_complete
                FROM image
                LEFT JOIN image_task_assignment AS ita
                  ON image.id = ita.image_id
                WHERE image.election_name = :election_name
                ON CONFLICT ON CONSTRAINT image_to_form
                DO NOTHING
            '''

            with engine.begin() as conn:
                conn.execute(sa.text(insert),
                             form_id=form.form_id,
                             election_name=form.election_name)

    def fetchOrWrite(self, key):
        image_name = key.split('/', 1)[-1]

        image_name_json = '{}.json'.format(image_name.rsplit('.', 1)[0])

        json_path = os.path.join(self.download_folder, image_name_json)

        if os.path.exists(json_path):
            return json.load(open(json_path))

        image = self.client.head_object(Bucket=self.bucket, Key=key)

        with open(json_path, 'w') as f:
            f.write(json.dumps(image['Metadata']))

        return image['Metadata']

    def updateAllElections(self):

        elections = set()

        params = {
            'Bucket': self.bucket,
        }

        all_keys = self.client.list_objects_v2(Bucket=self.bucket)

        while True:
            for key in all_keys['Contents']:
                elections.add(key['Key'].split('/', 1)[0])

            if all_keys['IsTruncated']:
                params['ContinuationToken'] = all_keys['NextContinuationToken']
            else:
                break

            all_keys = self.client.list_objects_v2(**params)

        for election in elections:
            self.updateElection(election)

    def updateElection(self, election_name):

        print('getting images for election {}'.format(election_name))

        self.inserts = []

        params = {
            'Bucket': self.bucket,
            'Prefix': election_name,
        }

        images = self.client.list_objects_v2(**params)

        updated = 0

        while True:

            for key['Key'] in images['Contents']:

                if key['Size'] > 0:

                    image = self.fetchOrWrite(key['Key'])

                    self.addToDCInserts(election_name, key['Key'], image)

                    updated += 1

                    if updated % 100 is 0:
                        print('fetched {}'.format(updated))

            if images['IsTruncated']:
                params['ContinuationToken'] = images['NextContinuationToken']
            else:
                break

            images = self.client.list_objects_v2(**params)

        if self.inserts:
            with engine.begin() as conn:
                conn.execute(sa.text(self.image_upsert), *self.inserts)

    def addToDCInserts(self,
                       election_name,
                       image_key,
                       image_metadata):

        fetch_url_fmt = 'https://s3.amazonaws.com/{bucket}/{key}'

        fetch_url = fetch_url_fmt.format(bucket=self.bucket,
                                         key=image_key)

        hierarchy = None

        if image_metadata.get('hierarchy'):
            hierarchy = json.loads(image_metadata['hierarchy'])

        values = dict(image_type='pdf',
                      fetch_url=fetch_url,
                      election_name=election_name,
                      id=image_metadata['image_id'],
                      hierarchy=hierarchy,
                      is_page_url=False,
                      is_current=True)

        self.inserts.append(values)
