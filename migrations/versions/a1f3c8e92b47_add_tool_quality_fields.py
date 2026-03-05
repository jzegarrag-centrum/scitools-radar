"""add tool quality fields

Revision ID: a1f3c8e92b47
Revises: eae7f52c79f1
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f3c8e92b47'
down_revision = 'eae7f52c79f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tool', schema=None) as batch_op:
        batch_op.add_column(sa.Column('features', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('editorial', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('auto_updated', sa.Boolean(), nullable=True, server_default=sa.false()))
        batch_op.add_column(sa.Column('quality_score', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('tool', schema=None) as batch_op:
        batch_op.drop_column('quality_score')
        batch_op.drop_column('auto_updated')
        batch_op.drop_column('editorial')
        batch_op.drop_column('features')
