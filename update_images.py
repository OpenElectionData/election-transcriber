from documentcloud import DocumentCloud
from transcriber.app_config import DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW, DB_CONN
import sqlalchemy as sa
from datetime import datetime
from transcriber.models import DocumentCloudImage
import json

engine = sa.create_engine(DB_CONN, 
                       convert_unicode=True, 
                       server_side_cursors=True)

def update_from_document_cloud():
    client = DocumentCloud(DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW)
    projects = client.projects.all()
    
    for project in projects:
        project = client.projects.get_by_title(project.title)
        doc_ids = project.document_ids
        for doc_id in doc_ids:

            # adding images document_cloud_image table if they don't exist
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
                '''

                values = dict(image_type='pdf', 
                              fetch_url=doc.pdf_url, 
                              dc_project = project.title,
                              dc_id = doc_id,
                              hierarchy = doc.data['hierarchy'],
                              is_page_url = False,
                              is_current = True)
                with engine.begin() as conn:
                    conn.execute(sa.text(new_image), **values)
                
                log_message = (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), 
                               project.title, 
                               doc_id)

                print('%s added %s %s' % log_message)
                
                if doc.pages > 1:
                    for p in range(2, doc.pages+1):
                        values['fetch_url'] = '%s#page=%s' % (doc.pdf_url, p)

                        with engine.begin() as conn:
                            conn.execute(sa.text(new_image), **values)


                ##############################
                # handle documents that are
                # updates of exisiting documents
                ##############################

def string_start_match(full_string, match_strings):
    for match_string in match_strings:
        if match_string in full_string:
            return True
    return False

def create_update_assign(task):
    
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
                  form_id
                ) VALUES (
                  :image_id,
                  :task_id
                )
            '''

            with engine.begin() as conn:
                conn.execute(sa.text(image_task_assign), **params)
            print '%s updated image_task' % (datetime.utcnow().strftime('%Y-%m-%d %H:%M%S'))


def update_task_images():

    tasks = ''' 
        SELECT * FROM form_meta
    '''

    for task in engine.execute(tasks):
        create_update_assign(task)

if __name__ == "__main__":
    update_from_document_cloud()
    update_task_images()
