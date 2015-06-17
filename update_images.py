from transcriber.views import update_image_table
from documentcloud import DocumentCloud
from transcriber.app_config import DOCUMENTCLOUD_USER, DOCUMENTCLOUD_PW, DB_CONN
import sqlalchemy as sa
from datetime import datetime

engine = sa.create_engine(DB_CONN, 
                       convert_unicode=True, 
                       server_side_cursors=True)

def update_all():
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

                for p in range(1, doc.pages+1):
                    values['fetch_url'] = '%s#page=%s' % (doc.pdf_url, p)

                    with engine.begin() as conn:
                        conn.execute(sa.text(new_image), **values)


                ##############################
                # handle documents that are
                # updates of exisiting documents
                ##############################

if __name__ == "__main__":
    update_all()
