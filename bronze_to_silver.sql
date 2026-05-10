DROP TABLE IF EXISTS silver_customers;

CREATE TABLE silver_customers AS
SELECT
    -- Primary key
    customer_id,

    -- Text fields (standardized)
    CAST(TRIM(business_name) AS VARCHAR(255)) AS business_name,
    CAST(UPPER(TRIM(state)) AS STRING(255)) AS state,
    CAST(UPPER(TRIM(business_type)) AS STRING(255)) AS business_type,

    -- Numeric fields (kept as-is, validated by schema)
    years_in_business,
    employee_count,
    coverage_limit,
    deductible,

    -- Financial fields (handle missing values)
    COALESCE(annual_revenue, 0) AS annual_revenue,
    COALESCE(payroll, 0) AS payroll,

    CASE WHEN employee_count < 0 THEN 0 ELSE employee_count END AS employee_count_cleaned

FROM staging_raw

-- Basic data quality filters
WHERE customer_id IS NOT NULL