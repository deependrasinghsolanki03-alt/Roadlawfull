import os
import markdown

input_dir = r'C:\Users\Deependra\.gemini\antigravity\brain\479ba27b-81e8-45b6-b37b-99d366d063ac'
output_dir = r'C:\Users\Deependra\Downloads\ROADSAFTEY\Documentation'

os.makedirs(output_dir, exist_ok=True)

files = [
    ('project_documentation.md', 'Project_Documentation.doc'),
    ('deep_technical_documentation.md', 'Deep_Technical_Documentation.doc'),
    ('online_offline_architecture.md', 'Online_Offline_Architecture.doc'),
    ('README.md', 'README.doc')
]

html_template = """<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 40px; }}
h1, h2, h3 {{ color: #2c3e50; }}
code {{ background-color: #f4f4f4; padding: 2px 5px; border-radius: 3px; font-family: monospace; }}
pre {{ background-color: #f4f4f4; padding: 15px; border-radius: 5px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #f2f2f2; }}
</style>
</head>
<body>
{}
</body>
</html>"""

for md_file, doc_file in files:
    md_path = os.path.join(input_dir, md_file)
    doc_path = os.path.join(output_dir, doc_file)
    if os.path.exists(md_path):
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        html_content = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
        final_html = html_template.format(html_content)
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(final_html)
        print(f'Created {doc_file}')
