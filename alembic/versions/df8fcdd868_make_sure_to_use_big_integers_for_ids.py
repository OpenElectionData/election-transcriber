"""Make sure to use big integers for ids

Revision ID: df8fcdd868
Revises: 4b92e3a80f5
Create Date: 2017-05-17 09:02:43.260460

"""

# revision identifiers, used by Alembic.
revision = 'df8fcdd868'
down_revision = '4b92e3a80f5'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute('''
        ALTER TABLE document_cloud_image
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE image_task_assignment
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE task_group
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE form_meta
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE form_section
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE form_field
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE ndi_user
        ALTER COLUMN id TYPE BIGINT
    ''')
    op.execute('''
        ALTER TABLE ndi_user
        ALTER COLUMN id TYPE BIGINT
    ''')


def downgrade():
    op.execute('''
        ALTER TABLE document_cloud_image
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE image_task_assignment
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE task_group
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE form_meta
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE form_section
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE form_field
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE ndi_user
        ALTER COLUMN id TYPE INTEGER
    ''')
    op.execute('''
        ALTER TABLE ndi_user
        ALTER COLUMN id TYPE INTEGER
    ''')
