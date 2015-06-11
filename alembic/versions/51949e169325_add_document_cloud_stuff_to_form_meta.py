"""add document cloud stuff to form_meta

Revision ID: 51949e169325
Revises: 30838544ae51
Create Date: 2015-06-11 16:07:43.493648

"""

# revision identifiers, used by Alembic.
revision = '51949e169325'
down_revision = '30838544ae51'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('form_meta', sa.Column('dc_filter', sa.Text(), nullable=True))
    op.add_column('form_meta', sa.Column('dc_project', sa.String(), nullable=True))
    op.add_column('form_meta', sa.Column('split_image', sa.Boolean(), nullable=True))
    op.drop_column('form_meta', 'image_location')
    op.drop_column('form_meta', 'image_view_count')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('form_meta', sa.Column('image_view_count', sa.INTEGER(), autoincrement=False, nullable=True))
    op.add_column('form_meta', sa.Column('image_location', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_column('form_meta', 'split_image')
    op.drop_column('form_meta', 'dc_project')
    op.drop_column('form_meta', 'dc_filter')
    ### end Alembic commands ###
