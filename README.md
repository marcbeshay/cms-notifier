# CMS Change Notifier

A Python script that monitors GUC CMS course pages for changes and sends notifications when new files are added or course descriptions are updated.

## Features

- Monitors all courses from the latest/current season automatically
- Detects new files and course description changes
- Sends notifications with course codes and names included in the title
- Persistent tracking of changes across script restarts
- Error handling for individual course failures
- Optional OpenAI integration for enhanced content processing
- Configurable notification settings

## Requirements

- Python 3.7+
- GUC CMS account credentials
- Notification service endpoint (for receiving alerts)

## Dependencies

This project uses the following main dependencies:

- `requests` & `requests-ntlm`: For authenticated HTTP requests to GUC CMS
- `beautifulsoup4`: For HTML parsing and content extraction
- `python-dotenv`: For environment variable management
- `openai`: For optional AI-powered content processing
- Additional supporting libraries listed in `requirements.txt`

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the root directory with your credentials:

3. Configure your environment variables in `.env`:

```env
# GUC CMS Credentials
GUC_USERNAME=your_guc_username
GUC_PASSWORD=your_guc_password

# Notification Settings
NOTIFICATION_ENDPOINT=your_notification_service_url
NOTIFICATIONS_API_KEY=your_api_key
SEND_NOTIFICATIONS=true

# OpenAI Integration (Optional)
OPENAI_API_KEY=your_openai_api_key
USE_OPENAI=false
```

### Environment Variables

- `GUC_USERNAME`: Your GUC username
- `GUC_PASSWORD`: Your GUC password
- `NOTIFICATION_ENDPOINT`: URL of your notification service
- `NOTIFICATIONS_API_KEY`: API key for your notification service
- `SEND_NOTIFICATIONS`: Whether to send notifications (true/false, default: true)
- `OPENAI_API_KEY`: OpenAI API key for enhanced processing (optional)
- `USE_OPENAI`: Enable OpenAI integration (true/false, default: false)

## Usage

Run the script:

```bash
# On Windows PowerShell
python src/main.py

# Or using Python module syntax
python -m src.main
```

The script will:

1. Fetch all your courses from the latest/current season
2. Monitor each course page every hour
3. Send notifications when changes are detected
4. Include the course code and name in notification titles

## Notification Format

- **New files**: `(COURSE_CODE) Course Name - New file just dropped - filename (category)`
- **Description changes**: `(COURSE_CODE) Course Name - Description changed - new description text`

Example notifications:

- `(MATH301) Mathematics III - New file just dropped - Lecture 5 (Lecture notes)`
- `(COMM401) Signal & System Theory - Description changed - Updated syllabus available`

## Data Storage

The script maintains state in JSON files:

- `description_versions.json`: Tracks course description versions and changes
- `files_versions.json`: Tracks file listings and metadata for each course

These files allow the script to detect changes across restarts and prevent duplicate notifications.

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Verify your GUC credentials in the `.env` file
2. **Network Issues**: Ensure you have access to GUC CMS and your notification endpoint
3. **Missing Dependencies**: Run `pip install -r requirements.txt` to install all required packages
4. **Permission Errors**: Make sure the script has write permissions for JSON state files

### Environment Variables

Make sure all required environment variables are properly set:

- `GUC_USERNAME` and `GUC_PASSWORD` are mandatory
- `NOTIFICATION_ENDPOINT` and `NOTIFICATIONS_API_KEY` are required for notifications
- `OPENAI_API_KEY` is only needed if `USE_OPENAI=true`

## Contributing

Feel free to submit issues and enhancement requests!
