import os
from io import BytesIO
import json

import httplib2

from oauth2client.service_account import ServiceAccountCredentials
from apiclient.discovery import build
from apiclient.http import MediaIoBaseDownload
from apiclient.errors import HttpError

from documentcloud import DocumentCloud

from transcriber.app_config import DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

class SyncGoogle(object):
    def __init__(self, dc_project=None):
        self.this_dir = os.path.dirname(__file__)
        secrets_path = os.path.join(self.this_dir, 'credentials.json')

        credentials = ServiceAccountCredentials.from_json_keyfile_name(secrets_path,
                                                                       SCOPES)
        http = credentials.authorize(httplib2.Http())

        self.service = build('drive', 'v3', http=http)

        result = self.service.files().list(q='sharedWithMe=true').execute()

        self.folder_ids = [f['id'] for f in result['files']
                           if f['mimeType'] == 'application/vnd.google-apps.folder']

        self.dc_project = dc_project
        self.dc_client = DocumentCloud(DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW)

        self.project, _ = self.dc_client.projects.get_or_create_by_title(self.dc_project)

        self.synced_images = self.getSyncedImages()

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
                'q': "'{}' in parents".format(folder_id)
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
                                status, done = media.next_chunk()

                                if not status.total_size:
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

                hierarchy = '/{}'.format(title.rsplit('.')[0].replace('_', '/'))
                metadata = {
                    'hierarchy': hierarchy,
                }

                self.dc_client.documents.upload(fd,
                                                title,
                                                access='public',
                                                project=str(self.project.id),
                                                data=metadata)

            os.remove(os.path.join(self.this_dir, title))

syncer = SyncGoogle(dc_project="Kenya rerun -- TEST")
thing = syncer.sync()
