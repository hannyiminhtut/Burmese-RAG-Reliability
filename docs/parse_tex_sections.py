import re

with open("docs/paper_draft_v1.1_revised.tex", "r", encoding="utf-8") as f:
    text = f.read()

# Extract sections
# Find \section, \subsection, etc.
sections = re.split(r'\\section\{([^}]+)\}', text)
print(f"Header: {len(sections[0])} chars")
for i in range(1, len(sections), 2):
    title = sections[i]
    content = sections[i+1]
    subsections = re.findall(r'\\subsection\{([^}]+)\}', content)
    print(f"Section: {title} ({len(content)} chars) - Subsections: {subsections}")
