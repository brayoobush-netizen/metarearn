"""Add is_admin column to User

Revision ID: e9f2f57efafd
Revises: f7b504703d43
Create Date: 2026-04-19 17:16:25.000249
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e9f2f57efafd'
down_revision = 'f7b504703d43'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='0'))

def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('is_admin')
