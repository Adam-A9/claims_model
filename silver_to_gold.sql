DROP TABLE IF EXISTS gold_customers;

CREATE TABLE gold_customers AS
SELECT
    customer_id,
    business_name,
    UPPER(state) AS state,
    UPPER(business_type) AS business_type,
    years_in_business,
    annual_revenue,
    employee_count,
    payroll,
    coverage_limit,
    deductible,

    -- =========================
    -- BUSINESS LOGIC METRICS
    -- =========================

    CASE
        WHEN employee_count > 0
        THEN payroll / employee_count
        ELSE NULL
    END AS payroll_per_employee,

    CASE
        WHEN annual_revenue > 0
        THEN payroll / annual_revenue
        ELSE NULL
    END AS payroll_to_revenue_ratio,

    -- =========================
    -- RISK SIGNALS
    -- =========================

    CASE
        WHEN years_in_business < 2 THEN 'HIGH_RISK'
        WHEN years_in_business BETWEEN 2 AND 10 THEN 'MEDIUM_RISK'
        ELSE 'LOW_RISK'
    END AS tenure_risk_band,

    CASE
        WHEN employee_count < 10 THEN 'SMALL'
        WHEN employee_count BETWEEN 10 AND 100 THEN 'MID'
        ELSE 'LARGE'
    END AS business_size_band,

    -- =========================
    -- SIMPLE UNDERWRITING FLAG
    -- =========================

    CASE
        WHEN payroll / NULLIF(annual_revenue, 0) > 0.6 THEN 1
        ELSE 0
    END AS high_cost_structure_flag

FROM silver_customers;