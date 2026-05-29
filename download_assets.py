import urllib.request
import re
import os

assets_dir = r"C:\Users\Deependra\Downloads\ROADSAFTEY\app\src\main\assets"
css_dir = os.path.join(assets_dir, "css")
fonts_dir = os.path.join(assets_dir, "fonts")

os.makedirs(css_dir, exist_ok=True)
os.makedirs(fonts_dir, exist_ok=True)

# 1. Download Tailwind
tailwind_url = "https://cdn.tailwindcss.com?plugins=forms,container-queries"
tailwind_path = os.path.join(css_dir, "tailwind.js")
print("Downloading Tailwind CSS...")
req = urllib.request.Request(tailwind_url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response, open(tailwind_path, 'wb') as f:
    f.write(response.read())

# 2. Download Plus Jakarta Sans
jakarta_url = "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap"
print("Downloading Plus Jakarta Sans CSS...")
req = urllib.request.Request(jakarta_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
with urllib.request.urlopen(req) as response:
    jakarta_css = response.read().decode('utf-8')

# Find all url(https://...) in the CSS
urls = set(re.findall(r"url\((https://fonts.gstatic.com/.*?)\)", jakarta_css))
for url in urls:
    filename = url.split('/')[-1]
    filepath = os.path.join(fonts_dir, filename)
    print(f"Downloading font {filename}...")
    with urllib.request.urlopen(url) as res, open(filepath, 'wb') as f:
        f.write(res.read())
    # replace URL in CSS
    jakarta_css = jakarta_css.replace(url, f"../fonts/{filename}")

with open(os.path.join(css_dir, "plus_jakarta_sans.css"), "w", encoding="utf-8") as f:
    f.write(jakarta_css)

# 3. Download Material Symbols Outlined
material_url = "https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
print("Downloading Material Symbols CSS...")
req = urllib.request.Request(material_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
with urllib.request.urlopen(req) as response:
    material_css = response.read().decode('utf-8')

urls = set(re.findall(r"url\((https://fonts.gstatic.com/.*?)\)", material_css))
for url in urls:
    filename = url.split('/')[-1]
    filepath = os.path.join(fonts_dir, filename)
    print(f"Downloading icon font {filename}...")
    with urllib.request.urlopen(url) as res, open(filepath, 'wb') as f:
        f.write(res.read())
    material_css = material_css.replace(url, f"../fonts/{filename}")

with open(os.path.join(css_dir, "material_symbols.css"), "w", encoding="utf-8") as f:
    f.write(material_css)

print("All assets downloaded successfully.")
