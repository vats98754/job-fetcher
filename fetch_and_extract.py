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
        return datetime.utcnow().date() - timedelta(days=int(m.group(1)))
    for pat, fmt in DATE_PATTERNS:
        m = pat.search(token)
        if m:
            txt = m.group(1)
            try:
                if fmt == "%b %d":
                    dt = datetime.strptime(txt + f", {datetime.utcnow().year}", "%b %d, %Y")
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
    
    # First, try to find table headers
    headers = []
    for line in lines:
        if "|" in line and not line.strip().startswith("#"):
            parts = [p.strip() for p in re.split(r"\|", line) if p.strip()]
            if len(parts) >= 3 and not any(char.isdigit() for char in line):  # Likely headers
                headers = parts
                break
    
    if not headers:
        # Fallback to basic extraction
        headers = ["Company", "Role", "Location", "Application", "Status", "Date", "Source"]
    
    for line in lines:
        if line.strip().startswith("#") or line.strip().startswith("---") or "|" not in line:
            continue
        parts = [p.strip() for p in re.split(r"\|", line) if p.strip()]
        if len(parts) >= 3:
            position = {"source_repo": repo}
            
            # Map parts to headers
            for i, part in enumerate(parts):
                if i < len(headers):
                    header = headers[i].lower().replace(" ", "_")
                    position[header] = part
            
            # Ensure we have basic fields
            if "company" not in position and len(parts) > 0:
                position["company"] = parts[0]
            if "role" not in position and len(parts) > 1:
                position["role"] = parts[1]
            if "location" not in position and len(parts) > 2:
                position["location"] = parts[2]
            
            # Extract application link
            app_link = ""
            for p in parts:
                if re.search(r'\[([^\]]+)\]\(([^)]+)\)', p):
                    m = re.search(r'\[([^\]]+)\]\(([^)]+)\)', p)
                    if m:
                        app_link = m.group(2)
                        break
                elif "http" in p:
                    app_link = p
                    break
            position["application"] = app_link
            
            # Extract status
            status = ""
            for p in parts:
                if "open" in p.lower() or "✅" in p or "available" in p.lower():
                    status = p
                    break
            position["status"] = status
            
            positions.append(position)
    
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

    # Collect all unique column names
    all_columns = set()
    for pos in all_positions:
        all_columns.update(pos.keys())
    
    # Ensure basic columns are included
    basic_columns = ["company", "role", "location", "application", "status", "date_token", "source_repo"]
    for col in basic_columns:
        all_columns.add(col)
    
    fieldnames = sorted(list(all_columns))

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in all_positions_sorted:
            writer.writerow(p)

    # Generate HTML page
    html_file = Path("index.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tech Internships US/Canada</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; cursor: pointer; }
        input { margin-bottom: 10px; padding: 5px; width: 100%; }
    </style>
</head>
<body>
    <h1>Tech Internships US/Canada</h1>
    <p>Filter: <input type="text" id="filter" onkeyup="filterTable()"></p>
    <table id="internships">
        <thead>
            <tr>
                <th onclick="sortTable(0)">Company</th>
                <th onclick="sortTable(1)">Role</th>
                <th onclick="sortTable(2)">Location</th>
                <th>Application</th>
                <th onclick="sortTable(4)">Status</th>
                <th onclick="sortTable(5)">Date</th>
                <th onclick="sortTable(6)">Source</th>
            </tr>
        </thead>
        <tbody>
""")
        with open(OUT_CSV, "r", encoding="utf-8") as csvf:
            reader = csv.DictReader(csvf)
            for row in reader:
                app_link = row["application"]
                if app_link:
                    app_html = f'<a href="{app_link}" target="_blank">Apply</a>'
                else:
                    app_html = ""
                f.write(f"""
            <tr>
                <td>{row["company"]}</td>
                <td>{row["role"]}</td>
                <td>{row["location"]}</td>
                <td>{app_html}</td>
                <td>{row["status"]}</td>
                <td>{row["date_token"]}</td>
                <td>{row["source_repo"]}</td>
            </tr>
""")
        f.write("""
        </tbody>
    </table>
    <script>
        function filterTable() {
            const input = document.getElementById('filter');
            const filter = input.value.toUpperCase();
            const table = document.getElementById('internships');
            const tr = table.getElementsByTagName('tr');
            for (let i = 1; i < tr.length; i++) {
                const td = tr[i].getElementsByTagName('td');
                let txtValue = '';
                for (let j = 0; j < td.length; j++) {
                    txtValue += td[j].textContent || td[j].innerText;
                }
                if (txtValue.toUpperCase().indexOf(filter) > -1) {
                    tr[i].style.display = '';
                } else {
                    tr[i].style.display = 'none';
                }
            }
        }
        function sortTable(n) {
            const table = document.getElementById('internships');
            let rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
            switching = true;
            dir = 'asc';
            while (switching) {
                switching = false;
                rows = table.rows;
                for (i = 1; i < (rows.length - 1); i++) {
                    shouldSwitch = false;
                    x = rows[i].getElementsByTagName('TD')[n];
                    y = rows[i + 1].getElementsByTagName('TD')[n];
                    if (dir == 'asc') {
                        if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {
                            shouldSwitch = true;
                            break;
                        }
                    } else if (dir == 'desc') {
                        if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {
                            shouldSwitch = true;
                            break;
                        }
                    }
                }
                if (shouldSwitch) {
                    rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
                    switching = true;
                    switchcount++;
                } else {
                    if (switchcount == 0 && dir == 'asc') {
                        dir = 'desc';
                        switching = true;
                    }
                }
            }
        }
    </script>
</body>
</html>
""")

    shutil.rmtree(temp)
    print(f"Wrote {len(all_positions_sorted)} positions to {OUT_CSV}")
    print(f"Generated index.html")

if __name__ == "__main__":
    main()
