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
    
    # Try to extract from HTML tables first
    html_positions = extract_from_html_tables(text, repo)
    if html_positions:
        positions.extend(html_positions)
    
    # Also try markdown table extraction
    markdown_positions = extract_from_markdown_tables(text, repo)
    if markdown_positions:
        positions.extend(markdown_positions)
    
    # Remove duplicates based on application link
    seen_links = set()
    unique_positions = []
    for pos in positions:
        link = pos.get('application', '')
        if link and link not in seen_links:
            seen_links.add(link)
            unique_positions.append(pos)
        elif not link:  # Keep positions without links
            unique_positions.append(pos)
    
    return unique_positions

def extract_from_html_tables(text: str, repo: str):
    positions = []
    
    # Use regex to find HTML table rows
    import re
    
    # Pattern to match table rows with company, role, location, application, age
    row_pattern = r'<tr>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>.*?(?:href="([^"]*)"|src="[^"]*").*?</td>.*?<td[^>]*>(.*?)</td>.*?</tr>'
    
    matches = re.findall(row_pattern, text, re.DOTALL | re.IGNORECASE)
    
    for match in matches:
        company_raw, role_raw, location_raw, application_link, age_raw = match
        
        # Clean up the extracted data
        company = clean_html_text(company_raw)
        role = clean_html_text(role_raw)
        location = clean_html_text(location_raw)
        
        # Extract application link if not already captured
        if not application_link:
            link_match = re.search(r'href="([^"]*)"', company_raw + role_raw + location_raw)
            if link_match:
                application_link = link_match.group(1)
        
        # Skip if this looks like a header or empty row
        if not company or company.lower().strip() in ['company', '↳'] or len(company.strip()) < 2:
            continue
            
        position = {
            'company': company,
            'role': role,
            'location': location,
            'application': application_link,
            'status': 'open',  # Assume open if in active table
            'date_token': age_raw.strip() if age_raw else '',
            'source_repo': repo
        }
        
        positions.append(position)
    
    return positions

def extract_from_markdown_tables(text: str, repo: str):
    lines = text.splitlines()
    positions = []
    
    # Find table headers
    header_line = None
    for i, line in enumerate(lines):
        if '|' in line and ('company' in line.lower() or 'role' in line.lower()):
            header_line = i
            break
    
    if not header_line:
        return positions
    
    # Parse headers
    headers = [h.strip().lower().replace(' ', '_') for h in lines[header_line].split('|') if h.strip()]
    
    # Parse data rows
    for line in lines[header_line + 2:]:  # Skip header separator
        if '|' not in line or line.strip().startswith('|---'):
            continue
            
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if len(parts) < len(headers):
            continue
            
        position = {'source_repo': repo}
        
        for i, part in enumerate(parts):
            if i < len(headers):
                header = headers[i]
                position[header] = part
        
        # Extract application link from HTML tags
        if 'application' in position:
            link_match = re.search(r'href="([^"]*)"', position['application'])
            if link_match:
                position['application'] = link_match.group(1)
        
        # Clean up company name
        if 'company' in position:
            position['company'] = clean_html_text(position['company'])
        
        positions.append(position)
    
    return positions

def clean_html_text(text: str) -> str:
    """Clean HTML tags and extract text content"""
    import re
    
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    
    # Remove extra whitespace
    clean = ' '.join(clean.split())
    
    # Remove common artifacts
    clean = clean.replace('↳', '').strip()
    
    return clean

def standardize_fields_with_ai(positions):
    """Use Hugging Face model to standardize field names"""
    
    # Define our target schema
    target_fields = {
        'company': ['company', 'organization', 'employer', 'firm'],
        'role': ['role', 'position', 'job', 'title', 'internship'],
        'location': ['location', 'place', 'city', 'state', 'country'],
        'application': ['application', 'link', 'apply', 'url', 'href'],
        'status': ['status', 'state', 'availability', 'open', 'closed'],
        'date_token': ['date', 'posted', 'created', 'age', 'time']
    }
    
    standardized_positions = []
    
    for pos in positions:
        standardized = {'source_repo': pos.get('source_repo', '')}
        
        # Try to map each field using AI if needed
        for target_field, possible_names in target_fields.items():
            # First try exact matches
            for key in pos.keys():
                if key.lower() in possible_names or any(name in key.lower() for name in possible_names):
                    standardized[target_field] = pos[key]
                    break
            
            # If no match found, try AI-powered mapping for complex cases
            if target_field not in standardized:
                best_match = find_best_field_match(pos.keys(), target_field, possible_names)
                if best_match:
                    standardized[target_field] = pos[best_match]
        
        # Ensure we have the basic required fields
        if 'company' not in standardized:
            standardized['company'] = 'Unknown Company'
        if 'role' not in standardized:
            standardized['role'] = 'Unknown Role'
        if 'location' not in standardized:
            standardized['location'] = 'Unknown Location'
        if 'application' not in standardized:
            standardized['application'] = ''
        if 'status' not in standardized:
            standardized['status'] = 'open'  # Default to open
        if 'date_token' not in standardized:
            standardized['date_token'] = ''
            
        standardized_positions.append(standardized)
    
    return standardized_positions

def find_best_field_match(available_fields, target_field, possible_names):
    """Find the best matching field name using simple heuristics"""
    
    # Convert to lowercase for comparison
    available_lower = [f.lower() for f in available_fields]
    
    # Look for exact matches first
    for name in possible_names:
        if name in available_lower:
            idx = available_lower.index(name)
            return available_fields[idx]
    
    # Look for partial matches
    for i, field in enumerate(available_lower):
        for name in possible_names:
            if name in field or field in name:
                return available_fields[i]
    
    # Look for abbreviations or similar patterns
    field_abbrevs = {
        'company': ['co', 'corp', 'inc', 'ltd', 'llc'],
        'role': ['pos', 'job', 'title'],
        'location': ['loc', 'place', 'addr'],
        'application': ['app', 'link', 'url'],
        'status': ['stat', 'state'],
        'date_token': ['date', 'time', 'posted']
    }
    
    if target_field in field_abbrevs:
        for abbrev in field_abbrevs[target_field]:
            if abbrev in available_lower:
                idx = available_lower.index(abbrev)
                return available_fields[idx]
    
    return None

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
            all_positions.append(pos)

    # Standardize field names using AI-powered mapping
    all_positions = standardize_fields_with_ai(all_positions)

    # Filter for US/Canada locations and open positions
    filtered_positions = []
    for pos in all_positions:
        if looks_like_us_or_canada(pos.get("location", "")) and ("open" in pos.get("status", "").lower() or "✅" in pos.get("status", "")):
            filtered_positions.append(pos)

    def parse_date(pos):
        dt = parse_date_token(pos.get("date_token",""))
        return dt or datetime(1970,1,1).date()

    all_positions_sorted = sorted(filtered_positions, key=parse_date, reverse=True)

    # Collect all unique column names
    all_columns = set()
    for pos in filtered_positions:
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
