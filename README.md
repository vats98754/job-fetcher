# job-fetcher
A fun repo for pulling jobs automatically with GitHub actions running some python files. I apply to all my jobs manually except those that use workday because workday sucks.

## Workflow Features

- **Automated Job Fetching**: Runs hourly to pull internship data from multiple GitHub repositories
- **Smart Filtering**: Focuses on US and Canada positions with open status
- **Automatic Updates**: Commits and pushes updated CSV data back to the repository
- **Conflict Resolution**: Handles concurrent runs with proper git pull/rebase logic
