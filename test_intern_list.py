#!/usr/bin/env python3
"""
Test script for intern-list scraper functionality.
This creates mock data to test the intern-list pipeline.
"""

import csv
from pathlib import Path
from datetime import datetime, timedelta

def create_mock_intern_list_data():
    """Create mock data for testing the intern-list pipeline"""
    
    mock_positions = [
        {
            'company': 'TechCorp',
            'role': 'Software Engineering Intern',
            'location': 'San Francisco, CA',
            'application': 'https://example.com/techcorp-apply',
            'status': 'open',
            'date_token': '2 days ago',
            'source_repo': 'intern-list.com'
        },
        {
            'company': 'DataSystems Inc',
            'role': 'Data Science Intern',
            'location': 'New York, NY', 
            'application': 'https://jobright.ai/redirect/example123',
            'status': 'open',
            'date_token': '1 week ago',
            'source_repo': 'intern-list.com'
        },
        {
            'company': 'CloudTech',
            'role': 'Product Management Intern',
            'location': 'Toronto, ON',
            'application': 'https://example.com/cloudtech-apply',
            'status': 'open', 
            'date_token': '3 days ago',
            'source_repo': 'intern-list.com'
        }
    ]
    
    # Write mock data to CSV
    fieldnames = ["company", "role", "location", "application", "status", "date_token", "source_repo"]
    output_file = Path("intern_list_us_canada.csv")
    
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for pos in mock_positions:
            writer.writerow(pos)
    
    print(f"Created mock intern-list data with {len(mock_positions)} positions in {output_file}")

if __name__ == "__main__":
    create_mock_intern_list_data()