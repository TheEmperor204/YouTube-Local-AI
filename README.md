# YouTube Shorts Auto-Poster

Automated YouTube Shorts uploader with AI-powered caption generation, content moderation, and scheduling.

## Requirements

- Linux (tested on Fedora/Ubuntu)
- Python 3.10+
- ffmpeg
- Ollama (with llava:7b model)
- faster-whisper (medium model)

## Setup

### 1. Python Virtual Environment

```bash
cd <project_directory>
python3 -m venv youtubee-env
source youtubee-env/bin/activate
pip install -r requirements.txt
```

### 2. Google Cloud Console Setup

1. Go to https://console.cloud.google.com
2. Create a new project (or select existing)
3. Enable YouTube Data API v3
4. Go to Credentials then Create Credentials then OAuth client ID
5. Choose Desktop app as application type
6. Download the credentials JSON file
7. Rename to client_secrets.json and place in project root

### 3. OAuth Consent Screen (for Testing)

1. Go to APIs and Services then OAuth consent screen
2. Choose External user type
3. Fill in required fields (app name, user support email)
4. Add test users: your Gmail address
5. Save - do NOT publish (keep in testing mode)

### 4. First Run Authorization

1. Launch the tray app
2. Click Run Poster from the system tray menu
3. Browser will open asking for YouTube authorization
4. Select your Gmail account, grant permissions
5. Token saved to yt_token.pickle - future runs do not need browser auth

### 5. Configuration (.env)

Key settings:
- YT_DRY_RUN=true - Test mode (no real uploads)
- VIDEO_FOLDER=videos_to_upload/ - Videos to process
- POSTED_SHORTS_DIR=youtube_posted_archive/ - Archived videos
- NTFY_TOPIC=YouTube-AI-Emperor204 - Phone notifications
- GPU_GUARD=true - Wait for GPU idle before processing

## Usage

### Desktop Launcher

Search for "YouTube Shorts Auto-Poster" in your app menu, or launch from terminal:

```bash
python3 tray_app.py &
```

### Processing Pipeline

1. Pre-screen: Transcription + banned word detection
2. Approval: Manual review via GUI for flagged videos
3. Segmentation: Split videos >60s into parts
4. Analysis: Frame-by-frame vision (LLaVA) + audio transcription
5. Moderation: Bleep explicit words, quarantine violations
6. Captioning: AI-generated title + description with #shorts
7. Upload: OAuth2 authenticated upload to YouTube

### Quota Limits

- Daily quota: 10,000 units
- Per upload: 1,600 units
- Max uploads/day: ~6
- Resets at midnight Pacific Time

## Troubleshooting

### OAuth2 errors

- Verify client_secrets.json is in project root
- Confirm Gmail is added as test user in Google Cloud Console
- Delete yt_token.pickle and re-run to restart auth flow

### Ollama 404 errors

- Check Ollama version compatibility (ollama list to see models)
- Try restarting Ollama: ollama serve &
- Verify llava:7b is installed: ollama pull llava:7b

### Video stuck in pending

- Check approval_queue.json for manual actions required
- Review explicit_videos/ folder for quarantined content
- Check temp_segments/ for stuck segment processing

### Notification issues

- Verify NTFY_TOPIC is set in .env
- Ensure ntfy.sh phone app is subscribed to topic
- Check tray_app.py _save_settings() preserves NTFY_TOPIC

## License

Internal use only. Not for redistribution.
