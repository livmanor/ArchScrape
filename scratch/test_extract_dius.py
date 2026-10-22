import requests
from bs4 import BeautifulSoup

r = requests.get('https://diusdesign.com/about', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
soup = BeautifulSoup(r.text, 'lxml')

with open('scratch/dius_dump.txt', 'w', encoding='utf-8') as f:
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'div']):
        text = h.get_text(separator=' ', strip=True)
        if 'Subbiah' in text and len(text) < 150:
            f.write(f"TAG: {h.name} | CLASS: {h.get('class')} | DATA-FRAMER: {h.get('data-framer-name')}\n")
            f.write(f"TEXT: {text}\n")
            f.write(f"PARENT: {h.parent.name if h.parent else None} | PARENT CLASS: {h.parent.get('class') if h.parent else None}\n")
            if h.parent:
                f.write(f"PARENT SIBLINGS: {[s.name for s in h.parent.find_next_siblings()]}\n")
            f.write("-" * 50 + "\n")
print("Dumped to scratch/dius_dump.txt")
