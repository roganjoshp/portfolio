"""empty message

Revision ID: dda651b4a22d
Revises: 
Create Date: 2020-07-22 09:46:38.207906

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dda651b4a22d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('machines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=20), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_machines'))
    )
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=255), nullable=True),
    sa.Column('data', sa.LargeBinary(), nullable=True),
    sa.Column('expiry', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('session_id', name=op.f('uq_sessions_session_id'))
    )
    op.create_table('current_machine_status',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('machine_id', sa.Integer(), nullable=True),
    sa.Column('hourly_product_count', sa.Integer(), nullable=True),
    sa.Column('is_down', sa.Boolean(), nullable=True),
    sa.Column('last_down', sa.DateTime(), nullable=True),
    sa.Column('hourly_down_count', sa.Integer(), nullable=True),
    sa.Column('total_secs_down', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], name=op.f('fk_current_machine_status_machine_id_machines'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_current_machine_status'))
    )
    with op.batch_alter_table('current_machine_status', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_current_machine_status_machine_id'), ['machine_id'], unique=False)

    op.create_table('machine_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('machine_id', sa.Integer(), nullable=True),
    sa.Column('datetime', sa.DateTime(), nullable=True),
    sa.Column('product_count', sa.Integer(), nullable=True),
    sa.Column('down_count', sa.Integer(), nullable=True),
    sa.Column('down_secs', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], name=op.f('fk_machine_history_machine_id_machines'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_machine_history'))
    )
    with op.batch_alter_table('machine_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_machine_history_datetime'), ['datetime'], unique=False)
        batch_op.create_index(batch_op.f('ix_machine_history_machine_id'), ['machine_id'], unique=False)

    op.create_table('machine_stats',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('machine_id', sa.Integer(), nullable=True),
    sa.Column('ideal_run_rate', sa.Integer(), nullable=True),
    sa.Column('efficiency', sa.Float(), nullable=True),
    sa.Column('min_downtime_secs', sa.Integer(), nullable=True),
    sa.Column('downtime_probability', sa.Float(), nullable=True),
    sa.Column('restart_probability', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['machine_id'], ['machines.id'], name=op.f('fk_machine_stats_machine_id_machines'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_machine_stats'))
    )
    with op.batch_alter_table('machine_stats', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_machine_stats_machine_id'), ['machine_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('machine_stats', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_machine_stats_machine_id'))

    op.drop_table('machine_stats')
    with op.batch_alter_table('machine_history', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_machine_history_machine_id'))
        batch_op.drop_index(batch_op.f('ix_machine_history_datetime'))

    op.drop_table('machine_history')
    with op.batch_alter_table('current_machine_status', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_current_machine_status_machine_id'))

    op.drop_table('current_machine_status')
    op.drop_table('sessions')
    op.drop_table('machines')
    # ### end Alembic commands ###
