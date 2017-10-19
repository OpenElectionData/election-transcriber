"""Make image_to_form constraint

Revision ID: 3b5bf4bf1e3
Revises: 31d5082abc8
Create Date: 2017-05-17 09:40:02.196959

"""

# revision identifiers, used by Alembic.
revision = '3b5bf4bf1e3'
down_revision = '31d5082abc8'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute('''
        ALTER TABLE image_task_assignment
        DROP CONSTRAINT IF EXISTS image_to_form
    ''')
    op.execute('''
        ALTER TABLE image_task_assignment
        ADD CONSTRAINT image_to_form UNIQUE (image_id, form_id)
    ''')


def downgrade():
    pass
