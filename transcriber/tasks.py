from datetime import datetime
import json

import sqlalchemy as sa

from documentcloud import DocumentCloud

from transcriber.queue import queuefunc
from transcriber.app_config import DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW, DB_CONN


@queuefunc
def update_images_by_task(task_id):
    
    from transcriber import create_app
    
    app = create_app()
    
    with app.test_request_context():
        from transcriber.database import db
        from transcriber.models import FormMeta, DocumentCloudImage, \
            ImageTaskAssignment
        
        task = db.session.query(FormMeta).get(task_id)
        task_dict = task.as_dict()
        
        if task_dict['split_image'] == False:
            doc_list = DocumentCloudImage.grab_relevant_images(task_dict['dc_project'],
                                                               task_dict['dc_filter'])
            for doc in doc_list:

                update_image_by_id(doc.id, task_dict['dc_project'])

        else:
            doc_list = DocumentCloudImage.grab_relevant_image_pages(task_dict['dc_project'], 
                                                                    task_dict['dc_filter'])
            
            for doc in doc_list:

                update_image_by_id(doc.id, task_dict['project_title'])


def update_image_by_id(image_id, project_title):
        
    from transcriber import create_app
    
    app = create_app()
    
    with app.test_request_context():
        from transcriber.database import db
        from transcriber.models import DocumentCloudImage, \
            ImageTaskAssignment, FormMeta

        tasks = ''' 
            SELECT * 
            FROM form_meta AS fm
            JOIN (
              SELECT form_id
              FROM image_task_assignment
              WHERE image_id = :image_id
            ) AS assign
              ON fm.id = assign.form_id
            WHERE fm.dc_project = :project_title
            AND status != 'deleted'
        '''
        
        params = {'image_id': image_id, 'project_title': project_title}
        tasks = list(db.session.execute(sa.text(tasks), params))
        
        if len(tasks) == 0:
            
            related_tasks = db.session.query(FormMeta)\
                              .filter(FormMeta.dc_project == project_title).all()
            
            for task in related_tasks:
                assignment = db.session.query(ImageTaskAssignment)\
                                       .filter(ImageTaskAssignment.image_id == image_id)\
                                       .filter(ImageTaskAssignment.form_id == task.id).first()
                
                if not assignment:
                    img_task_assign = ImageTaskAssignment(image_id=image_id, 
                                                          form_id=task.id)
                    db.session.add(img_task_assign)
                    db.session.commit()


@queuefunc
def update_one_from_document_cloud(doc_id, project_title):
    # adding images document_cloud_image table if they don't exist
    
    client = DocumentCloud(DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW)
    
    engine = sa.create_engine(DB_CONN, 
                           convert_unicode=True, 
                           server_side_cursors=True)
    
    existing_image = ''' 
        SELECT * FROM document_cloud_image
        WHERE dc_id = :dc_id
    '''
    
    existing_image = engine.execute(sa.text(existing_image), dc_id=doc_id).first()
    
    if existing_image == None:
        doc = client.documents.get(doc_id)
        
        new_image = ''' 
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
            RETURNING id
        '''
        
        values = dict(image_type='pdf', 
                      fetch_url=doc.pdf_url, 
                      dc_project = project_title,
                      dc_id = doc_id,
                      hierarchy = doc.data['hierarchy'],
                      is_page_url = False,
                      is_current = True)
        with engine.begin() as conn:
            image_id = conn.execute(sa.text(new_image), **values)
        
        update_image_by_id(image_id.first().id, project_title)

        log_message = (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), 
                       project_title, 
                       doc_id)

        print('%s added %s %s' % log_message)
        
        if doc.pages > 1:
            for p in range(2, doc.pages+1):
                values['fetch_url'] = '%s#page=%s' % (doc.pdf_url, p)

                with engine.begin() as conn:
                    image_id = conn.execute(sa.text(new_image), **values)
                
                update_image_by_id(image_id.first().id, project_title)
        
        ##############################
        # handle documents that are
        # updates of exisiting documents
        ##############################


def update_all_document_cloud():
    client = DocumentCloud(DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW)
    projects = client.projects.all()
    
    for project in projects:
        project = client.projects.get_by_title(project.title)
        doc_ids = project.document_ids
        for doc_id in doc_ids:
            
            update_one_from_document_cloud(doc_id, project.title)

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
