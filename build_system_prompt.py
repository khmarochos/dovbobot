#!/usr/bin/env python

# The script loads 3 files:
#   - the template from etc/system_prompt.txt.j2;
#   - the query JSON scheme from etc/query_scheme.json;
#   - the answer JSON scheme from etc/query_answer.json.
# Then the script builds the system prompt by including the schemes into the
# template and saves the result to the etc/system_prompt.txt file.
# All the paths are related to the directory where the script resides.

import json
from jinja2 import Environment, FileSystemLoader

# Define file paths
template_path = 'openai/system_prompt.txt.j2'
query_schema_path = 'openai/query_schema.json'
answer_schema_path = 'openai/answer_schema.json'
output_path = 'openai/system_prompt.txt'

# Load the template
env = Environment(loader=FileSystemLoader('openai'))
template = env.get_template('system_prompt.txt.j2')

# Load the JSON schemes
with open(query_schema_path, 'r') as file:
    query_schema = json.load(file)

with open(answer_schema_path, 'r') as file:
    answer_schema = json.load(file)

# Render the template with the JSON schemes
output_content = template.render(
    query_schema=query_schema,
    answer_schema=answer_schema
)

# Save the result to the output file
with open(output_path, 'w') as file:
    file.write(output_content)

print(f'System prompt has been built and saved to {output_path}')