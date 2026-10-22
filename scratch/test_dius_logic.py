import sys
sys.path.insert(0, ".")
import requests
from bs4 import BeautifulSoup
import re
from scraper.extractor import _clean_name, _designation_rank, _is_inside_ignored_section, _TESTIMONIAL_SALES_RE

r = requests.get('https://diusdesign.com/about', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
soup = BeautifulSoup(r.text, 'lxml')

_DESIGNATION_RE_NEW = re.compile(
    r"\b("
    r"(?:Co-)?Founders?\s*(?:&|and)\s*Principals?(?:\s+Architects?)?|"
    r"(?:Co-)?Founders?\s*(?:&|and)\s*Managing Directors?|"
    r"(?:Co-)?Founders?\s*(?:&|and)\s*(?:CEOs?|Directors?|Partners?)|"
    r"Founding Partners?\s*(?:&|and)\s*Principal Architects?|"
    r"Principal Architects?\s*(?:&|and)\s*Founders?|"
    r"Principals?\s*(?:&|and)\s*(?:Founders?|Directors?)|"
    r"Founding Partners?|Co-Founders?|Founders?|Managing Partners?|Managing Directors?|"
    r"Principal Architects?|Design Directors?|Creative Directors?|Directors?|"
    r"CEOs?|Chief Executive Officers?|Partners?|Principals?|Head of Design|"
    r"Lead Architects?|Senior Architects?|Architects?|"
    r"Interior Designers?|Studio Heads?|Business Coach(?:es)?|Coaches?|Presidents?|"
    r"Studio Directors?|Creative Leads?|Brand Strategists?"
    r")\b",
    re.IGNORECASE,
)

team_members = []
seen_names = set()

# Test 1: Sibling search with parent traversal
for h in soup.find_all(["h2", "h3", "h4", "h5"]):
    if _is_inside_ignored_section(h):
        continue
    name_clean = _clean_name(h.get_text(strip=True))
    if name_clean and name_clean.lower() not in seen_names:
        # Check direct sibling or parent sibling (for Framer/Webflow single-child wrapper divs)
        sib = (
            h.find_next_sibling(["p", "span", "div", "h4", "h5", "h6"])
            or (h.parent and len(h.parent.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])) == 1 and h.parent.find_next_sibling(["p", "span", "div", "h4", "h5", "h6"]))
            or (h.parent and h.parent.parent and len(h.parent.parent.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])) == 1 and h.parent.parent.find_next_sibling(["p", "span", "div", "h4", "h5", "h6"]))
        )
        if sib:
            sib_text = sib.get_text(strip=True)
            if _TESTIMONIAL_SALES_RE.search(sib_text):
                continue
            match = _DESIGNATION_RE_NEW.search(sib_text)
            if match:
                desig = match.group(0).title()
                rank = _designation_rank(desig)
                snippet = f"{name_clean} — {sib_text}"
                seen_names.add(name_clean.lower())
                team_members.append((name_clean, desig, rank, snippet, "Needs review", "parent_sibling"))

# Test 2: Image alt
for img in soup.find_all("img", alt=True):
    alt = (img.get("alt") or "").strip()
    if not alt or len(alt) < 5 or len(alt) > 150:
        continue
    if _TESTIMONIAL_SALES_RE.search(alt):
        continue
    parts = [p.strip() for p in re.split(r"\s*,\s*|\s*[-–—]\s*", alt)]
    if len(parts) >= 2:
        cand_name = _clean_name(parts[0])
        if cand_name and cand_name.lower() not in seen_names:
            for part in parts[1:]:
                match_desig = _DESIGNATION_RE_NEW.search(part)
                if match_desig:
                    desig = match_desig.group(0).title()
                    rank = _designation_rank(desig)
                    seen_names.add(cand_name.lower())
                    team_members.append((cand_name, desig, rank, f"Image alt: {alt}", "Source-supported", "img_alt"))
                    break

# Test 3: Adjacent lines
text = soup.get_text(separator="\n", strip=True)
lines = [l.strip() for l in text.splitlines() if l.strip()]
for i, line_clean in enumerate(lines):
    if not line_clean or len(line_clean) > 120:
        continue
    if _TESTIMONIAL_SALES_RE.search(line_clean):
        continue
    if i + 1 < len(lines):
        next_line = lines[i + 1].strip()
        cand_name = _clean_name(line_clean)
        if cand_name and cand_name.lower() not in seen_names and len(next_line) <= 60:
            if not _TESTIMONIAL_SALES_RE.search(next_line):
                desig_m = _DESIGNATION_RE_NEW.search(next_line)
                if desig_m:
                    desig = desig_m.group(0).title()
                    rank = _designation_rank(desig)
                    seen_names.add(cand_name.lower())
                    snippet = f"{cand_name} — {next_line}"
                    team_members.append((cand_name, desig, rank, snippet, "Needs review", "adjacent_lines"))

with open('scratch/test_results.txt', 'w', encoding='utf-8') as out:
    for m in team_members:
        out.write(f"Member: {m[0]} | Title: {m[1]} | Rank: {m[2]} | Source: {m[5]} | Status: {m[4]}\n")
print("Wrote results to scratch/test_results.txt")
