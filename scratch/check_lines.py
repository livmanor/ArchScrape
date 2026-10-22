import requests
from bs4 import BeautifulSoup

r = requests.get('https://diusdesign.com/about', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
soup = BeautifulSoup(r.text, 'lxml')
lines = [l.strip() for l in soup.get_text(separator='\n', strip=True).splitlines() if l.strip()]

with open('scratch/check_lines.txt', 'w', encoding='utf-8') as out:
    for i, line in enumerate(lines):
        if 'Subbiah' in line:
            prev = lines[i-1] if i > 0 else ""
            nxt1 = lines[i+1] if i + 1 < len(lines) else ""
            nxt2 = lines[i+2] if i + 2 < len(lines) else ""
            out.write(f"[{i}] {line}\n")
            out.write(f"   Prev: {prev}\n")
            out.write(f"   Next1: {nxt1}\n")
            out.write(f"   Next2: {nxt2}\n")
            out.write("-" * 40 + "\n")
print("Done writing scratch/check_lines.txt")
