import re

with open('final/ui.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add sv_ttk import
if "import sv_ttk" not in content:
    content = content.replace("import tkinter as tk", "import tkinter as tk\nimport sv_ttk")

# Strip out old styling blocks
style_block_pattern = r'    base_font = \("Calibri", 11\).*?style\.configure\("Treeview\.Heading", font=\("Calibri", 11, "bold"\)\)'
new_styling = '''    # Fontes modernas
    base_font = ("Segoe UI", 11)
    small_font = ("Segoe UI", 9)
    heading_font = ("Segoe UI", 16, "bold")

    # Aplica o tema moderno do Windows 11
    sv_ttk.set_theme("dark")'''

content = re.sub(style_block_pattern, new_styling, content, flags=re.DOTALL)

# Delete hardcoded backgrounds
content = re.sub(r'bg="#[0-9A-Fa-f]{6}"', 'bg="#2b2b2b"', content) # tk elements like drop_area matching sv_ttk dark
content = content.replace('root.configure(bg="#F6F6F6")', '') 
content = content.replace('popup.configure(bg="#FFFFFF")', '')

# Remap custom button styles to sv_ttk's built-in accent button
content = content.replace('style="Rounded.TButton"', 'style="Accent.TButton"')
content = content.replace('style="Ghost.TButton"', 'style="TButton"')

# Remap other styles to default
content = re.sub(r'style="Sidebar\.[A-Za-z]+"', '', content)
content = re.sub(r'style="Card\.[A-Za-z]+"', '', content)
content = content.replace('style="Heading.TLabel"', 'font=heading_font')
content = content.replace('style="Muted.TLabel"', 'font=small_font')

# Save back
with open('final/ui.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("UI atualizado!")
