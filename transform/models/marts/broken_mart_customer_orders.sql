{{ config(materialized='table') }}

select
    customer_id,
    definitely_missing_column
from {{ ref('stg_orders') }}