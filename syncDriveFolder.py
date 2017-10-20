import os
from io import BytesIO
import json
import csv
from uuid import uuid4

import httplib2

from oauth2client.service_account import ServiceAccountCredentials
from apiclient.discovery import build
from apiclient.http import MediaIoBaseDownload
from apiclient.errors import HttpError

import boto3

import img2pdf

from transcriber.app_config import S3_BUCKET
from transcriber.helpers import slugify

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class SyncGoogle(object):
    def __init__(self, election_name=None):
        self.this_dir = os.path.dirname(__file__)
        secrets_path = os.path.join(self.this_dir, 'credentials.json')

        credentials = ServiceAccountCredentials.from_json_keyfile_name(secrets_path,
                                                                       SCOPES)
        http = credentials.authorize(httplib2.Http())

        self.service = build('drive', 'v3', http=http)

        result = self.service.files().list(q='sharedWithMe=true').execute()

        self.folder_ids = [f['id'] for f in result['files']
                           if f['mimeType'] == 'application/vnd.google-apps.folder']

        self.bucket = S3_BUCKET
        self.election_name = election_name
        self.election_slug = slugify(election_name)

        aws_key, aws_secret_key = self.awsCredentials()

        self.s3_client = boto3.client('s3',
                                      aws_access_key_id=aws_key,
                                      aws_secret_access_key=aws_secret_key)

        self.synced_images = self.getSyncedImages()

    def awsCredentials(self):
        creds_path = os.path.join(self.this_dir, 'credentials.csv')

        if not os.path.exists(creds_path):
            raise Exception('Please decrypt s3credentials.csv.gpg into the root folder of the project')

        with open(creds_path) as f:
            reader = csv.reader(f)

            next(reader)

            _, _, aws_key, aws_secret_key, _ = next(reader)

        return aws_key, aws_secret_key


    def getSyncedImages(self):

        synced_path = os.path.join(self.this_dir, 'synced_images.json')

        if not os.path.exists(synced_path):
            with open(synced_path, 'w') as f:
                json.dump([], f)

        with open(synced_path) as f:
            return json.load(f)

    def addSyncedImage(self, title):

        self.synced_images.append(title)

        with open(os.path.join(self.this_dir, 'synced_images.json'), 'w') as f:
            json.dump(self.synced_images, f)

    def iterFiles(self):

        file_count = 0

        for folder_id in self.folder_ids:

            page_token = None

            params = {
                'q': "'{}' in parents".format(folder_id),
                'orderBy': 'name',
            }

            while True:

                if page_token:
                    params['pageToken'] = page_token

                folder_files = self.service.files().list(**params).execute()

                page_token = folder_files.get('nextPageToken')

                for folder_file in folder_files['files']:

                    title = folder_file['name']
                    file_id = folder_file['id']

                    if title not in self.synced_images:

                        contents = self.service.files().get_media(fileId=file_id)

                        with open(os.path.join(self.this_dir, title), 'wb') as fd:
                            media = MediaIoBaseDownload(fd, contents)
                            done = False

                            while done is False:

                                try:
                                    status, done = media.next_chunk()
                                except HttpError:
                                    print('Could not get file {}'.format(file_id))
                                    break
                        if done:

                            yield title
                            self.addSyncedImage(title)

                    file_count += 1

                if file_count % 100 == 0:
                    print('got {} files'.format(file_count))

                if not page_token:
                    break

        print('got {} files in total'.format(file_count))

    def sync(self):

        for title in self.iterFiles():

            with open(os.path.join(self.this_dir, title), 'rb') as fd:

                hierarchy = self.constructHierarchy(title)
                metadata = {
                    'hierarchy': json.dumps(hierarchy),
                    'election_name': self.election_name,
                    'election_slug': self.election_slug,
                    'image_id': str(uuid4()),
                }

                key = '{0}/{1}'.format(self.election_slug,
                                       '{}.pdf'.format(title.rsplit('.', 1)[0]))

                try:
                    body = img2pdf.convert(fd)
                except img2pdf.ImageOpenError:
                    print("Couldn't convert: {}".format(title))
                    continue

                self.s3_client.put_object(ACL='public-read',
                                          Body=body,
                                          Bucket=self.bucket,
                                          Key=key,
                                          ContentType='application/pdf',
                                          Metadata=metadata)

            os.remove(os.path.join(self.this_dir, title))

    def constructHierarchy(self, title):
        geographies = title.split('-', 1)[1].rsplit('.', 1)[0]
        county, constituency, ward, polling_center, polling_station = geographies.split('_')
        return {
            'county': county,
            'constituency': constituency,
            'ward': ward,
            'polling_center': polling_center,
            'polling_station': polling_station,
        }

syncer = SyncGoogle(election_name="Kenya rerun -- TEST")
thing = syncer.sync()
