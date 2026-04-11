"""Initial tables

Revision ID: e78953dc0e0a
Revises: 94544b22aab5
Create Date: 2026-04-11 17:49:51.833957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e78953dc0e0a'
down_revision = '94544b22aab5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(120), unique=True, nullable=False),
        sa.Column('password', sa.String(200), nullable=False),
        sa.Column('referral_code', sa.String(20), unique=True),
        sa.Column('referred_by', sa.Integer, sa.ForeignKey('user.id'))
    )


def downgrade():
    op.drop_table('user')