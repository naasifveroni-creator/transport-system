"""add campaigns and campaign_id to users

Revision ID: 4ebffde9861b
Revises: 71d537f70d56
Create Date: 2026-09-14 14:51:16.330937

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4ebffde9861b'
down_revision = '71d537f70d56'
branch_labels = None
depends_on = None


def upgrade():
    # Create campaigns table
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('business_name', sa.String(length=160), nullable=True),
        sa.Column('contact_email', sa.String(length=160), nullable=True),
        sa.Column('contact_phone', sa.String(length=40), nullable=True),
        sa.Column('area', sa.String(length=160), nullable=True),
        sa.Column('default_pickup', sa.String(length=120), nullable=True),
        sa.Column('default_dropoff', sa.String(length=120), nullable=True),
        sa.Column('default_lat', sa.Float(), nullable=True),
        sa.Column('default_lng', sa.Float(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.String(length=64), nullable=True),
        sa.Column('created_by', sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # Add campaign_id column with an explicit FK name
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('campaign_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_users_campaign_id',
            'campaigns',
            ['campaign_id'],
            ['id']
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_campaign_id', type_='foreignkey')
        batch_op.drop_column('campaign_id')
    op.drop_table('campaigns')
