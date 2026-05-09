"""V2 three-funnel schema: drop V0/V1 tables, alter existing, add 6 new tables

Revision ID: v2_three_funnel
Revises: 9ccdcd9901f0
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'v2_three_funnel'
down_revision: Union[str, Sequence[str], None] = '9ccdcd9901f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade to V2 three-funnel schema."""

    # ===== 1. Drop V0/V1 evaluation tables (data fully discarded per user decision) =====
    op.drop_table('score_snapshot')
    op.drop_table('factor_value')

    # ===== 2. Alter existing tables =====

    # company: add instrument_type / list_date / is_excluded
    op.add_column(
        'company',
        sa.Column(
            'instrument_type',
            sa.Enum(
                'COMMON', 'REIT', 'ETF', 'FUND', 'SPAC', 'ADR', 'PREFERRED', 'WARRANT',
                'BANK', 'INSURANCE', 'BROKER', 'SHELL', 'OTHER',
                name='instrument_type_enum',
            ),
            nullable=False,
            server_default='COMMON',
        ),
    )
    op.add_column('company', sa.Column('list_date', sa.Date(), nullable=True))
    op.add_column(
        'company',
        sa.Column('is_excluded', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )
    op.create_index('ix_company_instrument_type', 'company', ['instrument_type'])

    # fact: rename taxonomy_or_account → account_code; add accepted_date / fiscal_year / amended_from_fact_id
    op.alter_column(
        'fact',
        'taxonomy_or_account',
        new_column_name='account_code',
        existing_type=sa.String(length=100),
        existing_nullable=False,
    )
    op.add_column('fact', sa.Column('fiscal_year', sa.Integer(), nullable=True))
    op.add_column('fact', sa.Column('accepted_date', sa.Date(), nullable=True))
    op.add_column('fact', sa.Column('amended_from_fact_id', sa.String(length=128), nullable=True))
    op.create_index('ix_fact_accepted_date', 'fact', ['accepted_date'])
    # Drop old index & create new with renamed column
    op.drop_index('ix_fact_company_concept_period', table_name='fact')
    op.create_index(
        'ix_fact_company_account_period', 'fact',
        ['company_id', 'account_code', 'period_end'],
    )

    # filing: add accepted_at / actual_disclosure_date / url_pdf / title
    op.add_column('filing', sa.Column('title', sa.String(length=500), nullable=True))
    op.add_column('filing', sa.Column('accepted_at', sa.DateTime(), nullable=True))
    op.add_column('filing', sa.Column('actual_disclosure_date', sa.Date(), nullable=True))
    op.add_column('filing', sa.Column('url_pdf', sa.String(length=500), nullable=True))
    op.create_index('ix_filing_company_form', 'filing', ['company_id', 'form_type'])
    op.create_index('ix_filing_accepted_at', 'filing', ['accepted_at'])

    # user: add AI provider keys + default
    op.add_column('user', sa.Column('chatgpt_api_key_encrypted', sa.Text(), nullable=True))
    op.add_column('user', sa.Column('minimax_api_key_encrypted', sa.Text(), nullable=True))
    op.add_column('user', sa.Column('minimax_group_id', sa.String(length=128), nullable=True))
    op.add_column(
        'user',
        sa.Column(
            'ai_provider_default',
            sa.Enum('chatgpt', 'minimax', name='ai_provider_enum'),
            nullable=False,
            server_default='chatgpt',
        ),
    )

    # ===== 3. Create new tables =====

    # text_document: 公告/年报/新闻原文（无 FK 到 filing 因 filing 也可能是后建的，做软关联）
    op.create_table(
        'text_document',
        sa.Column('doc_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('doc_type', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('content_text', sa.Text(), nullable=True),
        sa.Column('content_url', sa.String(length=500), nullable=True),
        sa.Column('content_sha256', sa.String(length=64), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column(
            'ingested_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('filing_id', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id']),
        sa.ForeignKeyConstraint(['filing_id'], ['filing.filing_id']),
        sa.PrimaryKeyConstraint('doc_id'),
    )
    op.create_index('ix_text_document_company_id', 'text_document', ['company_id'])
    op.create_index('ix_text_document_doc_type', 'text_document', ['doc_type'])
    op.create_index('ix_text_document_published_at', 'text_document', ['published_at'])
    op.create_index('ix_text_doc_company_published', 'text_document', ['company_id', 'published_at'])
    op.create_index('ix_text_doc_company_doctype', 'text_document', ['company_id', 'doc_type'])

    # screen_run（必须先于 risk_ai_result/screen_result/metric_lineage_log，因为是 FK target）
    op.create_table(
        'screen_run',
        sa.Column('run_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('universe_name', sa.String(length=100), nullable=True),
        sa.Column('universe_snapshot', sa.JSON(), nullable=True),
        sa.Column(
            'market',
            sa.Enum('US', 'CN_A', 'MIXED', name='run_market_enum'),
            nullable=False,
        ),
        sa.Column('as_of_date', sa.Date(), nullable=False),
        sa.Column('config_snapshot', sa.JSON(), nullable=True),
        sa.Column(
            'started_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('running', 'completed', 'failed', 'cancelled', name='run_status_enum'),
            server_default='running',
            nullable=False,
        ),
        sa.Column('total_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('passed_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('rejected_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('review_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('run_id'),
    )
    op.create_index('ix_screen_run_user_id', 'screen_run', ['user_id'])
    op.create_index('ix_screen_run_as_of_date', 'screen_run', ['as_of_date'])

    # risk_ai_result
    op.create_table(
        'risk_ai_result',
        sa.Column('result_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=True),
        sa.Column('asof_date', sa.Date(), nullable=False),
        sa.Column(
            'ai_provider',
            sa.Enum('chatgpt', 'minimax', name='ai_provider_result_enum'),
            nullable=False,
        ),
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('prompt_version', sa.String(length=50), nullable=False),
        sa.Column('prompt_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'overall_action',
            sa.Enum('PASS', 'REVIEW', 'REJECT', 'MONITOR', name='ai_action_enum'),
            nullable=False,
        ),
        sa.Column('labels', sa.JSON(), nullable=True),
        sa.Column('summary_cn', sa.Text(), nullable=True),
        sa.Column('raw_response', sa.JSON(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('error_msg', sa.String(length=500), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id']),
        sa.ForeignKeyConstraint(['run_id'], ['screen_run.run_id']),
        sa.PrimaryKeyConstraint('result_id'),
    )
    op.create_index('ix_risk_ai_result_company_id', 'risk_ai_result', ['company_id'])
    op.create_index('ix_risk_ai_result_run_id', 'risk_ai_result', ['run_id'])
    op.create_index('ix_risk_ai_result_asof_date', 'risk_ai_result', ['asof_date'])
    op.create_index('ix_risk_ai_company_asof', 'risk_ai_result', ['company_id', 'asof_date'])

    # screen_result
    op.create_table(
        'screen_result',
        sa.Column('result_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'Rejected', 'Review', 'TooExpensive', 'NearFairPrice', 'HighConviction',
                name='screen_status_enum',
            ),
            nullable=False,
        ),
        sa.Column('q_passed', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column('q_strong_track', sa.Boolean(), server_default=sa.text('0'), nullable=False),
        sa.Column(
            'r_action',
            sa.Enum('PASS', 'REVIEW', 'REJECT', 'MONITOR', 'RULE_ONLY', name='r_action_enum'),
            nullable=True,
        ),
        sa.Column(
            'v_state',
            sa.Enum('TooExpensive', 'Acceptable', 'Cheap', name='v_state_enum'),
            nullable=True,
        ),
        sa.Column('reason_codes', sa.JSON(), nullable=True),
        sa.Column('metrics_snapshot', sa.JSON(), nullable=True),
        sa.Column('ai_result_id', sa.BigInteger(), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['screen_run.run_id']),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id']),
        sa.ForeignKeyConstraint(['ai_result_id'], ['risk_ai_result.result_id']),
        sa.PrimaryKeyConstraint('result_id'),
    )
    op.create_index('ix_screen_result_run_id', 'screen_result', ['run_id'])
    op.create_index('ix_screen_result_company_id', 'screen_result', ['company_id'])
    op.create_index('ix_screen_result_status', 'screen_result', ['status'])
    op.create_index('ix_screen_result_run_status', 'screen_result', ['run_id', 'status'])
    op.create_index('ix_screen_result_company_run', 'screen_result', ['company_id', 'run_id'])

    # metric_periodic
    op.create_table(
        'metric_periodic',
        sa.Column('metric_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('metric_name', sa.String(length=60), nullable=False),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('formula_version', sa.String(length=20), server_default='v1', nullable=False),
        sa.Column(
            'computed_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column('source_fact_ids', sa.JSON(), nullable=True),
        sa.Column('notes', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id']),
        sa.PrimaryKeyConstraint('metric_id'),
        sa.UniqueConstraint(
            'company_id', 'period_end', 'metric_name', 'formula_version',
            name='uq_metric_periodic',
        ),
    )
    op.create_index('ix_metric_periodic_company_id', 'metric_periodic', ['company_id'])
    op.create_index('ix_metric_periodic_period_end', 'metric_periodic', ['period_end'])
    op.create_index('ix_metric_periodic_company_metric', 'metric_periodic', ['company_id', 'metric_name'])

    # metric_lineage_log
    op.create_table(
        'metric_lineage_log',
        sa.Column('log_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=True),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column('field_name', sa.String(length=80), nullable=False),
        sa.Column('source_code', sa.String(length=20), nullable=True),
        sa.Column('source_record_key', sa.String(length=200), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('raw_value', sa.Float(), nullable=True),
        sa.Column('normalized_value', sa.Float(), nullable=True),
        sa.Column('formula_version', sa.String(length=20), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['run_id'], ['screen_run.run_id']),
        sa.PrimaryKeyConstraint('log_id'),
    )
    op.create_index('ix_metric_lineage_log_run_id', 'metric_lineage_log', ['run_id'])
    op.create_index('ix_metric_lineage_log_company_id', 'metric_lineage_log', ['company_id'])
    op.create_index('ix_lineage_run_company', 'metric_lineage_log', ['run_id', 'company_id'])
    op.create_index('ix_lineage_company_field', 'metric_lineage_log', ['company_id', 'field_name'])


def downgrade() -> None:
    """Downgrade rolls back V2 schema. WARNING: drops all V2 data and rebuilds V0/V1 stubs."""

    # Drop new tables (reverse dependency order)
    op.drop_table('metric_lineage_log')
    op.drop_table('metric_periodic')
    op.drop_table('screen_result')
    op.drop_table('risk_ai_result')
    op.drop_table('screen_run')
    op.drop_table('text_document')

    # Drop user AI columns
    op.drop_column('user', 'ai_provider_default')
    op.drop_column('user', 'minimax_group_id')
    op.drop_column('user', 'minimax_api_key_encrypted')
    op.drop_column('user', 'chatgpt_api_key_encrypted')

    # Filing alterations rollback
    op.drop_index('ix_filing_accepted_at', table_name='filing')
    op.drop_index('ix_filing_company_form', table_name='filing')
    op.drop_column('filing', 'url_pdf')
    op.drop_column('filing', 'actual_disclosure_date')
    op.drop_column('filing', 'accepted_at')
    op.drop_column('filing', 'title')

    # Fact alterations rollback
    op.drop_index('ix_fact_company_account_period', table_name='fact')
    op.create_index(
        'ix_fact_company_concept_period', 'fact',
        ['company_id', 'concept', 'period_end'],
    )
    op.drop_index('ix_fact_accepted_date', table_name='fact')
    op.drop_column('fact', 'amended_from_fact_id')
    op.drop_column('fact', 'accepted_date')
    op.drop_column('fact', 'fiscal_year')
    op.alter_column(
        'fact',
        'account_code',
        new_column_name='taxonomy_or_account',
        existing_type=sa.String(length=100),
        existing_nullable=False,
    )

    # Company alterations rollback
    op.drop_index('ix_company_instrument_type', table_name='company')
    op.drop_column('company', 'is_excluded')
    op.drop_column('company', 'list_date')
    op.drop_column('company', 'instrument_type')

    # Recreate V0/V1 tables (empty stubs to allow rollback)
    op.create_table(
        'factor_value',
        sa.Column('factor_value_id', sa.String(length=128), nullable=False),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column('factor_code', sa.String(length=20), nullable=False),
        sa.Column('asof_date', sa.Date(), nullable=False),
        sa.Column('raw_value', sa.Float(), nullable=True),
        sa.Column('cleaned_value', sa.Float(), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('normalization_bucket', sa.String(length=50), nullable=True),
        sa.Column('lineage', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id']),
        sa.PrimaryKeyConstraint('factor_value_id'),
    )
    op.create_table(
        'score_snapshot',
        sa.Column('score_id', sa.String(length=128), nullable=False),
        sa.Column('company_id', sa.String(length=32), nullable=False),
        sa.Column('asof_date', sa.Date(), nullable=False),
        sa.Column('model_version', sa.String(length=20), nullable=False),
        sa.Column('survival', sa.Float(), nullable=True),
        sa.Column('replication', sa.Float(), nullable=True),
        sa.Column('adaptation', sa.Float(), nullable=True),
        sa.Column('moat', sa.Float(), nullable=True),
        sa.Column('valuation', sa.Float(), nullable=True),
        sa.Column('total', sa.Float(), nullable=True),
        sa.Column('tier', sa.String(length=20), nullable=True),
        sa.Column('gating_flags', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['company.company_id']),
        sa.PrimaryKeyConstraint('score_id'),
    )
