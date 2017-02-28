from datetime import datetime
import json
import os

import sqlalchemy as sa

from documentcloud import DocumentCloud

from transcriber.app_config import DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW, DB_CONN
from transcriber.models import FormMeta, DocumentCloudImage, ImageTaskAssignment
from transcriber.queue import queuefunc

engine = sa.create_engine(DB_CONN)

@queuefunc
def update_from_document_cloud(project_title=None, overwrite=False):
    updater = ImageUpdater(overwrite=overwrite)

    if project_title == 'Emailed documents':
        updater.updateEmailedDocuments()
    elif project_title:
        updater.updateDocumentCloudProject(project_title)
    else:
        updater.updateAllDocumentCloud()

    print('complete!')


class ImageUpdater(object):
    def __init__(self, overwrite=False):
        self.client = DocumentCloud(DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW)
        self.this_folder = os.path.abspath(os.path.dirname(__file__))
        self.download_folder = os.path.join(self.this_folder, 'downloads')
        self.overwrite = overwrite
        self.inserts = []

    @property
    def document_cloud_upsert(self):
        return '''
            INSERT INTO document_cloud_image (
              image_type,
              fetch_url,
              dc_project,
              dc_id,
              hierarchy,
              is_page_url,
              is_current
            ) VALUES (
              :image_type,
              :fetch_url,
              :dc_project,
              :dc_id,
              :hierarchy,
              :is_page_url,
              :is_current
            )
            ON CONFLICT (dc_id) DO UPDATE SET
              image_type = :image_type,
              fetch_url = :fetch_url,
              dc_project = :dc_project,
              hierarchy = :hierarchy,
              is_page_url = :is_page_url,
              is_current = :is_current

        '''

    def updateImages(self):

        forms = '''
            SELECT
              dc_project,
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
                  dc.dc_id AS image_id,
                  :form_id AS form_id,
                  FALSE AS is_complete
                FROM document_cloud_image AS dc
                LEFT JOIN image_task_assignment AS ita
                  ON dc.dc_id = ita.image_id
                WHERE dc.dc_project = :dc_project
                ON CONFLICT ON CONSTRAINT image_to_form
                DO NOTHING
            '''

            with engine.begin() as conn:
                conn.execute(sa.text(insert), 
                             form_id=form.form_id,
                             dc_project=form.dc_project)

    def fetchOrWrite(self, project_dir, document_id):

        document_path = os.path.join(project_dir, '{}.json'.format(document_id))

        if not os.path.exists(document_path) or self.overwrite:
            document = self.client.documents.get(document_id)
            document = {
                'pdf_url': document.pdf_url,
                'id': document.id,
                'data': document.data,
                'pages': document.pages,
            }
            with open(document_path, 'w') as f:
                f.write(json.dumps(document))
        else:
            document = json.load(open(document_path))

        return document

    def updateAllDocumentCloud(self):
        self.updateDocumentCloudProjects()
        self.updateEmailedDocuments()

    def updateDocumentCloudProjects(self):
        projects = self.client.projects.all()

        for project in projects:
            self.updateDocumentCloudProject(project.title)

        self.updateImages()

    def updateDocumentCloudProject(self, project_title):

        print('getting images for project {}'.format(project_title))

        self.inserts = []

        project = self.client.projects.get_by_title(project_title)

        project_dir = os.path.join(self.download_folder, str(project.id))
        os.makedirs(project_dir, exist_ok=True)

        for document_id in project.document_ids:

            document = self.fetchOrWrite(project_dir, document_id)
            self.addToDCInserts(project.title, document)

        if self.inserts:
            with engine.begin() as conn:
                conn.execute(sa.text(self.document_cloud_upsert), *self.inserts)


    def addToDCInserts(self, project_title, document):

        values = dict(image_type='pdf',
                      fetch_url=document['pdf_url'],
                      dc_project = project_title,
                      dc_id = document['id'],
                      hierarchy = document['data'].get('hierarchy'),
                      is_page_url = False,
                      is_current = True)

        self.inserts.append(values)

        if document['pages'] > 1:
            for p in range(2, (document['pages'] + 1)):
                values['fetch_url'] = '%s#page=%s' % (document['pdf_url'], p)

                self.inserts.append(values)

    def updateEmailedDocuments(self):

        self.inserts = []

        project_dir = os.path.join(self.download_folder, 'emailed')
        os.makedirs(project_dir, exist_ok=True)

        emailed = self.client.documents.search('uploaded:email group:nationaldemocraticinstitute')

        for document in emailed:
            document = self.fetchOrWrite(project_dir, document.id)

            self.addToDCInserts('Emailed documents', document)

        if self.inserts:
            with engine.begin() as conn:
                conn.execute(sa.text(self.document_cloud_upsert), *self.inserts)

        self.updateImages()


