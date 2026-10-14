{% macro generate_schema_name(custom_schema_name, node) -%}
{#- One schema per layer, taken from the top-level model folder. -#}
{%- if custom_schema_name is not none -%}
    {{ custom_schema_name | trim }}
{%- elif node.resource_type == 'model' -%}
    {{ node.fqn[1] }}
{%- else -%}
    {{ target.schema }}
{%- endif -%}
{%- endmacro %}
