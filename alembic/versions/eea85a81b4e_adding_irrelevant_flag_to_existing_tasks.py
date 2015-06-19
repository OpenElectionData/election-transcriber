"""adding irrelevant flag to existing tasks

Revision ID: eea85a81b4e
Revises: 3e96ae10921f
Create Date: 2015-06-19 16:12:13.181098

"""

# revision identifiers, used by Alembic.
revision = 'eea85a81b4e'
down_revision = '3e96ae10921f'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

connection = op.get_bind()

def upgrade():
    q = 'SELECT table_name from form_meta'
    tasks = connection.execute(q)
    table_names = [task.table_name for task in tasks]

    for table_name in table_names:
        this_table = sa.Table(table_name, sa.MetaData(), autoload=True, autoload_with=connection)
        if not 'flag_irrelevant' in [c.name for c in this_table.columns]:
            op.add_column(table_name, sa.Column('flag_irrelevant', sa.Boolean(), nullable=True))
        


def downgrade():
    pass
