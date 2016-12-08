"""Shift PK for document_cloud_image

Revision ID: 57dd92c709b
Revises: 30c6e688863
Create Date: 2016-12-05 14:26:41.154299

"""

# revision identifiers, used by Alembic.
revision = '57dd92c709b'
down_revision = '30c6e688863'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute(''' 
        ALTER TABLE document_cloud_image 
        DROP CONSTRAINT document_cloud_image_pkey 
        CASCADE
    ''')
    op.execute(''' 
        ALTER TABLE document_cloud_image 
        ADD PRIMARY KEY (dc_id)        
    ''')
    op.execute(''' 
        ALTER TABLE document_cloud_image 
        ADD CONSTRAINT unique_dc_id UNIQUE (dc_id)
    ''')
    op.execute(''' 
        ALTER TABLE image_task_assignment
        ALTER COLUMN image_id TYPE VARCHAR
    ''')
    op.execute(''' 
        ALTER TABLE image_task_assignment 
        ADD CONSTRAINT image_to_form 
        UNIQUE (image_id, form_id)
    ''')
    op.execute(''' 
        UPDATE image_task_assignment SET
          image_id = s.image_id
        FROM (
          SELECT 
            dc.dc_id AS image_id,
            ita.id
          FROM document_cloud_image AS dc
          JOIN form_meta AS fm 
            USING(dc_project)
          JOIN image_task_assignment AS ita
            ON fm.id = ita.form_id
        ) AS s
        WHERE image_task_assignment.id = s.id
    ''')


def downgrade():
    # This is kind of a one way operation for the moment. There is more than
    # likely a way to reverse it, I just have no reason to think through it at
    # the moment.
    op.add_column('document_cloud_image', 
                  sa.Column('id', sa.INTEGER(), 
                            server_default=sa.text("nextval('document_cloud_image_id_seq'::regclass)"), 
                            nullable=False))
