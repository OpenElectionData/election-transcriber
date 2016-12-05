from datetime import datetime
import json
import os

import sqlalchemy as sa

from documentcloud import DocumentCloud

from transcriber.queue import queuefunc
from transcriber.app_config import DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW, DB_CONN
from transcriber.models import FormMeta, DocumentCloudImage, ImageTaskAssignment

engine = sa.create_engine(DB_CONN)

@queuefunc
def update_images(image_id=None):
    
    insert = ''' 
        INSERT INTO image_task_assignment (
          image_id,
          form_id,
          is_complete
        )
        SELECT 
          dc.dc_id AS image_id,
          fm.id AS form_id,
          FALSE AS is_complete
        FROM document_cloud_image AS dc
        JOIN form_meta AS fm 
          USING(dc_project)
        LEFT JOIN image_task_assignment AS ita
          ON fm.id = ita.form_id
        WHERE ita.form_id IS NULL
    '''
    
    q_args = {}
    
    if image_id:
        insert = '{} AND dc.id = :image_id'
        q_args['image_id'] = image_id

    with engine.begin() as conn:
        conn.execute(sa.text(insert), **q_args)


def update_all_document_cloud():
    client = DocumentCloud(DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW)
    projects = client.projects.all()
    
    insert_q = ''' 
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
        ON CONFLICT (dc_id) DO NOTHING
    '''
    
    inserts = []
    count = 0
    
    this_folder = os.path.abspath(os.path.dirname(__file__))
    download_folder = os.path.join(this_folder, 'downloads')

    for project in projects:
        
        print('getting images for project {}'.format(project.title))
        
        project_dir = os.path.join(download_folder, str(project.id))
        os.makedirs(project_dir, exist_ok=True)

        project = client.projects.get_by_title(project.title)

        for document_id in project.document_ids:
            
            document_path = os.path.join(project_dir, '{}.json'.format(document_id))
            
            if not os.path.exists(document_path):
                document = client.documents.get(document_id)
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

            values = dict(image_type='pdf', 
                          fetch_url=document['pdf_url'], 
                          dc_project = project.title,
                          dc_id = document['id'],
                          hierarchy = document['data']['hierarchy'],
                          is_page_url = False,
                          is_current = True)
            
            inserts.append(values)
            
            if document['pages'] > 1:
                for p in range(2, (document['pages'] + 1)):
                    values['fetch_url'] = '%s#page=%s' % (document['pdf_url'], p)

                    inserts.append(values)

        if inserts:
            with engine.begin() as conn:
                conn.execute(sa.text(insert_q), *inserts)
        
            count += len(inserts)
            print('inserted {}'.format(count))

            inserts = []

    update_images()

def string_start_match(full_string, match_strings):
    for match_string in match_strings:
        if match_string in full_string:
            return True
    return False

def create_update_assign(task):
    
    engine = sa.create_engine(DB_CONN, 
                           convert_unicode=True, 
                           server_side_cursors=True)
    
    hierarchy_filter = None

    if task.dc_filter != None:
        hierarchy_filter = json.loads(task.dc_filter)
    
    doc_list = ''' 
        SELECT * FROM document_cloud_image
        WHERE dc_project = :project 
          AND is_page_url = :page_url_flag
    '''

    doc_list = engine.execute(sa.text(doc_list), 
                              project=task.dc_project,
                              page_url_flag=task.split_image)
    
    if hierarchy_filter:
        doc_list = [r for r in doc_list \
                    if string_start_match(r.hierarchy, hierarchy_filter)]

    for doc in doc_list:
        
        image_task_assign = ''' 
            SELECT * FROM image_task_assignment
            WHERE form_id = :task_id
              AND image_id = :image_id
        '''

        params = {
            'task_id': task.id,
            'image_id': doc.id,
        }

        image_task_assign = engine.execute(sa.text(image_task_assign), **params).first()

        if image_task_assign == None:
            image_task_assign = ''' 
                INSERT INTO image_task_assignment (
                  image_id, 
                  form_id,
                  is_complete
                ) VALUES (
                  :image_id,
                  :task_id,
                  FALSE
                )
            '''

            with engine.begin() as conn:
                conn.execute(sa.text(image_task_assign), **params)
            print(  '%s updated image_task' % (datetime.utcnow().strftime('%Y-%m-%d %H:%M%S')) )


def update_task_images():
    
    engine = sa.create_engine(DB_CONN, 
                           convert_unicode=True, 
                           server_side_cursors=True)

    tasks = ''' 
        SELECT * FROM form_meta
        WHERE status IS NULL
    '''

    for task in engine.execute(tasks):
        create_update_assign(task)
