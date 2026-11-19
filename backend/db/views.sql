-- Analytics Views (S9)
-- Human-readable reference for the 5 analytics views.
-- Managed by migration 009_analytics_views.py (initial creation) and
-- migration 018_doc_proc_analytics_views.py (repointed onto the typed
-- contract_metadata columns from the document-processing schema change,
-- plan section 7.3).
--
-- Every object is qualified with the project schema, because the database is
-- shared with other projects. The schema name is not written here: it comes
-- from the DB_SCHEMA / PROJECT_NAMESPACE setting. In this file it appears as
-- the psql variable :"schema"; to run a statement by hand, pass the value of
-- the setting:  psql -v schema=<db_schema> -f db/views.sql
-- tests/unit/test_analytics_views_sql.py keeps this file in step with the
-- migration.

-- ---------------------------------------------------------------------------
-- 1. v_contract_intelligence
--    One row per contract: metadata + latest contract-level risk score.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS :"schema".v_contract_intelligence;
CREATE VIEW :"schema".v_contract_intelligence AS
SELECT
    c.id                        AS contract_id,
    c.title,
    c.contract_type,
    c.paper_origin,
    c.status,
    c.counterparty_id,
    p.display_name              AS counterparty_name,
    cm.effective_date,
    cm.expiry_date,
    cm.governing_law,
    cm.auto_renewal,
    cm.renewal_notice_days,
    cm.liability_cap_amount,
    cm.liability_cap_basis,
    cm.payment_terms_days,
    rs.score                    AS risk_score,
    rs.max_clause_severity,
    c.created_at,
    c.updated_at
FROM :"schema".contract c
LEFT JOIN :"schema".contract_metadata cm ON cm.contract_id = c.id
LEFT JOIN :"schema".party p ON p.id = c.counterparty_id
LEFT JOIN LATERAL (
    SELECT score, max_clause_severity
    FROM :"schema".risk_score
    WHERE contract_id = c.id AND clause_id IS NULL
    ORDER BY created_at DESC
    LIMIT 1
) rs ON true;


-- ---------------------------------------------------------------------------
-- 2. v_portfolio_risk
--    Severity-weighted roll-up: high=3, medium=2, low=1.
--    Portfolio score = SUM(weighted_flags) / total_contracts (via AVG).
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS :"schema".v_portfolio_risk;
CREATE VIEW :"schema".v_portfolio_risk AS
WITH flag_weights AS (
    SELECT
        contract_id,
        SUM(CASE severity WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END) AS weighted_flag_score,
        COUNT(*) FILTER (WHERE severity = 'high')   AS high_count,
        COUNT(*) FILTER (WHERE severity = 'medium') AS medium_count,
        COUNT(*) FILTER (WHERE severity = 'low')    AS low_count,
        COUNT(*)                                     AS total_flags
    FROM :"schema".flag
    GROUP BY contract_id
),
contract_risk AS (
    SELECT
        fw.contract_id,
        fw.weighted_flag_score,
        fw.high_count,
        fw.medium_count,
        fw.low_count,
        fw.total_flags,
        rs.score          AS risk_score,
        rs.max_clause_severity
    FROM flag_weights fw
    LEFT JOIN LATERAL (
        SELECT score, max_clause_severity
        FROM :"schema".risk_score
        WHERE contract_id = fw.contract_id AND clause_id IS NULL
        ORDER BY created_at DESC
        LIMIT 1
    ) rs ON true
)
SELECT
    COUNT(*)                         AS total_contracts,
    SUM(high_count)                  AS total_high_flags,
    SUM(medium_count)                AS total_medium_flags,
    SUM(low_count)                   AS total_low_flags,
    SUM(total_flags)                 AS total_flags,
    ROUND(AVG(weighted_flag_score)::numeric, 2) AS avg_weighted_flag_score,
    ROUND(AVG(risk_score)::numeric, 4)          AS avg_risk_score,
    COUNT(*) FILTER (WHERE max_clause_severity = 'high')   AS contracts_high_severity,
    COUNT(*) FILTER (WHERE max_clause_severity = 'medium') AS contracts_medium_severity,
    COUNT(*) FILTER (WHERE max_clause_severity = 'low')    AS contracts_low_severity
FROM contract_risk;


-- ---------------------------------------------------------------------------
-- 3. v_contract_value
--    One row per contract: typed financial columns from contract_metadata.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS :"schema".v_contract_value;
CREATE VIEW :"schema".v_contract_value AS
SELECT
    c.id                                              AS contract_id,
    c.title,
    c.contract_type,
    c.counterparty_id,
    p.display_name                                    AS counterparty_name,
    cm.total_value_amount,
    cm.currency,
    cm.liability_cap_amount,
    cm.liability_cap_basis,
    cm.payment_terms_days,
    cm.effective_date,
    cm.expiry_date,
    CASE
        WHEN cm.effective_date IS NOT NULL AND cm.expiry_date IS NOT NULL
        THEN (cm.expiry_date - cm.effective_date)
    END                                               AS duration_days,
    c.status,
    c.created_at
FROM :"schema".contract c
LEFT JOIN :"schema".contract_metadata cm ON cm.contract_id = c.id
LEFT JOIN :"schema".party p ON p.id = c.counterparty_id;


-- ---------------------------------------------------------------------------
-- 4. v_tabular_review
--    One row per contract: metadata + flag counts + obligation counts +
--    redline counts.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS :"schema".v_tabular_review;
CREATE VIEW :"schema".v_tabular_review AS
SELECT
    c.id                           AS contract_id,
    c.title,
    c.contract_type,
    c.paper_origin,
    c.status,
    p.display_name                 AS counterparty_name,
    cm.effective_date,
    cm.expiry_date,
    cm.governing_law,
    cm.auto_renewal,
    cm.renewal_notice_days,
    cm.payment_terms_days,
    cm.liability_cap_amount,
    cm.liability_cap_basis,
    rs.score                       AS risk_score,
    rs.max_clause_severity,
    COALESCE(flag_counts.high_flags, 0)   AS high_flags,
    COALESCE(flag_counts.medium_flags, 0) AS medium_flags,
    COALESCE(flag_counts.low_flags, 0)    AS low_flags,
    COALESCE(ob_counts.open_obligations, 0)    AS open_obligations,
    COALESCE(ob_counts.overdue_obligations, 0) AS overdue_obligations,
    rl_counts.proposed_redlines,
    rl_counts.accepted_redlines,
    c.created_at,
    c.updated_at
FROM :"schema".contract c
LEFT JOIN :"schema".contract_metadata cm ON cm.contract_id = c.id
LEFT JOIN :"schema".party p ON p.id = c.counterparty_id
LEFT JOIN LATERAL (
    SELECT score, max_clause_severity
    FROM :"schema".risk_score
    WHERE contract_id = c.id AND clause_id IS NULL
    ORDER BY created_at DESC
    LIMIT 1
) rs ON true
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE severity = 'high')   AS high_flags,
        COUNT(*) FILTER (WHERE severity = 'medium') AS medium_flags,
        COUNT(*) FILTER (WHERE severity = 'low')    AS low_flags
    FROM :"schema".flag
    WHERE contract_id = c.id
) flag_counts ON true
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE status = 'open')    AS open_obligations,
        COUNT(*) FILTER (WHERE status = 'overdue') AS overdue_obligations
    FROM :"schema".obligation
    WHERE contract_id = c.id
) ob_counts ON true
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE status = 'proposed')  AS proposed_redlines,
        COUNT(*) FILTER (WHERE status = 'accepted')  AS accepted_redlines
    FROM :"schema".redline
    WHERE contract_id = c.id
) rl_counts ON true;


-- ---------------------------------------------------------------------------
-- 5. v_renewal_dashboard
--    One row per contract: expiry metadata + risk score + latest renewal alert.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS :"schema".v_renewal_dashboard;
CREATE VIEW :"schema".v_renewal_dashboard AS
SELECT
    c.id                           AS contract_id,
    c.title,
    c.contract_type,
    c.counterparty_id,
    p.display_name                 AS counterparty_name,
    cm.expiry_date,
    cm.auto_renewal,
    cm.renewal_notice_days,
    cm.governing_law,
    rs.score                       AS risk_score,
    rs.max_clause_severity,
    al.payload->>'recommendation'  AS renewal_recommendation,
    al.payload->>'rationale'       AS renewal_rationale,
    al.payload->>'compliance_pass' AS compliance_pass,
    al.fired_at                    AS last_alert_at,
    al.acknowledged                AS alert_acknowledged,
    c.status                       AS contract_status
FROM :"schema".contract c
LEFT JOIN :"schema".contract_metadata cm ON cm.contract_id = c.id
LEFT JOIN :"schema".party p ON p.id = c.counterparty_id
LEFT JOIN LATERAL (
    SELECT score, max_clause_severity
    FROM :"schema".risk_score
    WHERE contract_id = c.id AND clause_id IS NULL
    ORDER BY created_at DESC
    LIMIT 1
) rs ON true
LEFT JOIN LATERAL (
    SELECT payload, fired_at, acknowledged
    FROM :"schema".alert
    WHERE contract_id = c.id AND alert_type = 'renewal'
    ORDER BY fired_at DESC
    LIMIT 1
) al ON true;
