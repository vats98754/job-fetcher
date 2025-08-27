import csv
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

# Repos to pull internship data from (US/Canada focus)
REPOS = [
    "SimplifyJobs/Summer2026-Internships",
    "vanshb03/Summer2026-Internships",
    "speedyapply/2026-SWE-College-Jobs",
    "arunike/Summer-2025-Internship-List",
    "isaiahiruoha/Canadian-Tech-And-Business-Internships-Summer-2025",
    "Dannny-Babs/Canadian-Tech-Internships-2025",
]

OUT_CSV = Path("internships_us_canada.csv")

DATE_PATTERNS = [
    (re.compile(r"(\d{2}/\d{2}/\d{4})"), "%m/%d/%Y"),
    (re.compile(r"(\d{4}-\d{2}-\d{2})"), "%Y-%m-%d"),
    (re.compile(r"([A-Za-z]{3,9} \d{1,2},? \d{4})"), "%B %d, %Y"),
    (re.compile(r"([A-Za-z]{3} \d{1,2})"), "%b %d"),
]

def parse_date_token(token: str):
    token = token.strip()
    m = re.match(r"^(\d+)d$", token)
    if m:
        return datetime.now().date() - timedelta(days=int(m.group(1)))
    for pat, fmt in DATE_PATTERNS:
        m = pat.search(token)
        if m:
            txt = m.group(1)
            try:
                if fmt == "%b %d":
                    dt = datetime.strptime(txt + f", {datetime.now().year}", "%b %d, %Y")
                else:
                    dt = datetime.strptime(txt, fmt)
                return dt.date()
            except:
                pass
    return None

def shallow_clone(repo: str, dest: Path):
    repo_url = f"https://github.com/{repo}.git"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(dest)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        print(f"Failed to clone {repo}")
        return False

US_STATE_ABBREVS = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS',
    'KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY',
    'NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'
}

def looks_like_us_or_canada(loc: str) -> bool:
    if not loc: return False
    s = loc.lower()
    if "usa" in s or "united states" in s or " us" in s: return True
    if "canada" in s or "ontario" in s or "toronto" in s or "vancouver" in s: return True
    tokens = re.split(r"[\s,]+", loc.upper())
    return any(t in US_STATE_ABBREVS for t in tokens)

def extract_positions_from_text(text: str, repo: str):
    lines = text.splitlines()
    positions = []
    for line in lines:
        if line.strip().startswith("#") or line.strip().startswith("---"):
            continue
        parts = [p.strip() for p in re.split(r"\|", line) if p.strip()]
        if len(parts) >= 3:
            company, role = parts[0], parts[1]
            location, date_token, app_link, status = "", "", "", ""
            for p in parts[2:]:
                if "http" in p: app_link = p
                if "open" in p.lower() or "✅" in p: status = p
                if re.search(r"\d{1,2}/\d{1,2}/\d{4}", p) or re.search(r"[A-Za-z]{3} \d{1,2}", p) or re.search(r"\d+d", p):
                    date_token = p
                if looks_like_us_or_canada(p): location = p
            if not location and len(parts) >= 3: location = parts[2]
            positions.append({
                "company": company, "role": role, "location": location,
                "application": app_link, "status": status,
                "date_token": date_token, "source_repo": repo,
            })
    return positions

def main():
    temp = Path(tempfile.mkdtemp(prefix="internscan_"))
    all_positions = []

    for repo in REPOS:
        target = temp / repo.replace("/", "_")
        if not shallow_clone(repo, target): continue

        content = ""
        for fn in ["README.md","readme.md","README.MD"]:
            if (target/fn).exists():
                content = (target/fn).read_text(errors="ignore")
                break
        if not content:
            for p in target.glob("**/*"):
                if p.is_file() and "intern" in p.name.lower():
                    content = p.read_text(errors="ignore")
                    break
        if not content: continue

        for pos in extract_positions_from_text(content, repo):
            if looks_like_us_or_canada(pos["location"]) and ("open" in pos["status"].lower() or "✅" in pos["status"]):
                all_positions.append(pos)

    def parse_date(pos):
        dt = parse_date_token(pos.get("date_token",""))
        return dt or datetime(1970,1,1).date()

    all_positions_sorted = sorted(all_positions, key=parse_date, reverse=True)

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company","role","location","application","status","date_token","source_repo"])
        writer.writeheader()
        for p in all_positions_sorted:
            writer.writerow(p)

    shutil.rmtree(temp)
    print(f"Wrote {len(all_positions_sorted)} positions to {OUT_CSV}")

if __name__ == "__main__":
    main()
