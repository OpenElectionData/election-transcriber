import os
from io import BytesIO
import json
import csv
from uuid import uuid4
import itertools

import httplib2

import sqlalchemy as sa

from oauth2client.service_account import ServiceAccountCredentials
from apiclient.discovery import build
from apiclient.http import MediaIoBaseDownload
from apiclient.errors import HttpError

import boto3
import botocore

import img2pdf

from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True


from transcriber.app_config import S3_BUCKET, DB_CONN, AWS_CREDENTIALS_PATH
from transcriber.helpers import slugify

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class SyncGoogle(object):
    def __init__(self,
                 election_name=None,
                 drive_folder=None,
                 aws_creds=None,
                 google_creds=None,
                 capture_hierarchy=False):

        self.this_dir = os.path.abspath(os.path.dirname(__file__))
        self.capture_hierarchy = capture_hierarchy

        credentials = ServiceAccountCredentials.from_json_keyfile_name(google_creds,
                                                                       SCOPES)
        http = credentials.authorize(httplib2.Http())

        self.service = build('drive', 'v3', http=http)

        result = self.service.files().list(q="name contains '{}'".format(drive_folder)).execute()

        self.folder_ids = [f['id'] for f in result['files']
                           if f['mimeType'] == 'application/vnd.google-apps.folder']

        self.bucket = S3_BUCKET
        self.election_name = election_name
        self.election_slug = slugify(election_name)

        aws_key, aws_secret_key = self.awsCredentials(aws_creds)

        self.s3_client = boto3.client('s3',
                                      aws_access_key_id=aws_key,
                                      aws_secret_access_key=aws_secret_key)

        self.downloaded_images = self.downloadedImages()

    def awsCredentials(self, creds_path):

        with open(creds_path) as f:
            reader = csv.reader(f)

            next(reader)

            _, _, aws_key, aws_secret_key, _ = next(reader)

        return aws_key, aws_secret_key


    def downloadedImages(self):

        downloaded_path = os.path.join(self.this_dir, 'downloaded_images.json')

        if not os.path.exists(downloaded_path):
            with open(downloaded_path, 'w') as f:
                json.dump([], f)

        with open(downloaded_path) as f:
            return json.load(f)

    def addDownloadedImage(self, title):

        self.downloaded_images.append(title)

        with open(os.path.join(self.this_dir, 'downloaded_images.json'), 'w') as f:
            json.dump(self.downloaded_images, f)

    def downloadImage(self, file_id, title):
        contents = self.service.files().get_media(fileId=file_id)

        with open(os.path.join(self.this_dir, title), 'wb') as fd:
            media = MediaIoBaseDownload(fd, contents)
            done = False

            while done is False:

                try:
                    status, done = media.next_chunk()
                except HttpError:
                    print('Could not get file {1} ({0})'.format(file_id, title))
                    break
        if done:

            self.addDownloadedImage(title)

    def iterFiles(self):

        file_count = 0

        for folder_id in self.folder_ids:

            page_token = None

            params = {
                'q': "'{}' in parents".format(folder_id),
                'orderBy': 'name',
            }

            all_files = []

            while True:

                if page_token:
                    params['pageToken'] = page_token

                folder_files = self.service.files().list(**params).execute()

                page_token = folder_files.get('nextPageToken')

                inserts = []

                for folder_file in folder_files['files']:

                    title = folder_file['name']
                    file_id = folder_file['id']

                    if title not in self.downloaded_images:

                        self.downloadImage(file_id, title)

                    all_files.append(title)

                if not page_token:
                    break

            grouper = lambda x: x.rsplit('_', 1)[0]

            all_files_sorted = sorted(all_files, key=grouper)

            yield from itertools.groupby(all_files_sorted, key=grouper)

    def saveImage(self, key):

        try:
            image = self.s3_client.head_object(Bucket=self.bucket, Key=key)['Metadata']
        except botocore.exceptions.ClientError:
            return

        fetch_url_fmt = 'https://s3.amazonaws.com/{bucket}/{key}'

        fetch_url = fetch_url_fmt.format(bucket=self.bucket,
                                            key=key)

        values = dict(image_type='pdf',
                        fetch_url=fetch_url,
                        election_name=self.election_slug,
                        id=image['image_id'],
                        hierarchy=json.loads(image['hierarchy']),
                        is_page_url=False,
                        is_current=True)

        engine = sa.create_engine(DB_CONN)

        with engine.begin() as conn:
            conn.execute(sa.text('''
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
            '''), **values)

        del engine

    def sync(self):

        for group_name, file_group in self.iterFiles():

            filenames = list(file_group)

            if self.capture_hierarchy:
                hierarchy = self.constructHierarchy(group_name)
            else:
                hierarchy = []

            metadata = {
                'hierarchy': json.dumps(hierarchy),
                'election_name': self.election_name,
                'election_slug': self.election_slug,
                'image_id': str(uuid4()),
            }

            key = '{0}/{1}'.format(self.election_slug,
                                   '{}.pdf'.format(group_name))

            try:
                body = img2pdf.convert(filenames)
            except (img2pdf.ImageOpenError, OSError, ZeroDivisionError) as e:
                print("Couldn't convert: {0} ({1})".format(group_name, e))
                continue
            except TypeError:
                for filename in filenames:
                    file_blob = self.service.files().list(q="name = '{}'".format(filename)).execute()

                    if file_blob['files']:
                        file_id = file_blob['files'][0]['id']
                        self.downloadImage(file_id, filename)

                try:
                    body = img2pdf.convert(filenames)
                except (img2pdf.ImageOpenError, OSError, ZeroDivisionError) as e:
                    print("Couldn't convert: {0} ({1})".format(group_name, e))
                    continue

            self.s3_client.put_object(ACL='public-read',
                                      Body=body,
                                      Bucket=self.bucket,
                                      Key=key,
                                      ContentType='application/pdf',
                                      Metadata=metadata)

            self.saveImage(key)

            for title in filenames:
                os.remove(os.path.join(self.this_dir, title))

    def constructHierarchy(self, title):
        # geographies = title.split('-', 1)[1].rsplit('.', 1)[0]
        return  title.split('_')

if __name__ == "__main__":
    import argparse

    this_dir = os.path.abspath(os.path.dirname(__file__))
    default_aws_credentials = os.path.join(this_dir, 'credentials.csv')
    default_google_credentials = os.path.join(this_dir, 'credentials.json')

    parser = argparse.ArgumentParser(description='Sync and convert images from a Google Drive Folder to an S3 Bucket',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--aws-creds', type=str, help='Path to AWS credentials.', default=default_aws_credentials)
    parser.add_argument('--google-creds', type=str, help='Path to Google credentials.', default=default_google_credentials)
    parser.add_argument('-n', '--election-name', type=str, help='Short name to be used under the hood for the election', required=True)
    parser.add_argument('-f', '--drive-folder', type=str, help='Name of the Google Drive folder to sync', required=True)
    parser.add_argument('--capture-hierarchy', action='store_true', help='Capture a geographical hierarchy from the name of the file.')

    args = parser.parse_args()

    syncer = SyncGoogle(aws_creds=args.aws_creds,
                        google_creds=args.google_creds,
                        election_name=args.election_name,
                        drive_folder=args.drive_folder,
                        capture_hierarchy=args.capture_hierarchy)
    syncer.sync()
