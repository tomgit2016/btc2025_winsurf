# Tennis Court Booking Automation

This Python script automates the process of booking tennis courts on a tennis club website using Selenium WebDriver.

## Prerequisites

- Python 3.7+
- Google Chrome browser installed
- ChromeDriver (automatically managed by webdriver-manager)

## Setup

1. Clone this repository or download the files.

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the `config` directory by copying the example:
   ```bash
   cp config/.env.example config/.env
   ```

4. Edit the `config/.env` file with your tennis club website credentials and preferences. New settings are supported for multiple preferred courts, booking duration, and player names. Example:
   ```env
   TENNIS_CLUB_URL=https://www.example-tennis-club.com/
   USERNAME=your_username
   PASSWORD=your_password

   # Preferences
   PREFERRED_COURTS=3,4,5,2   # Tried in this order
   PREFERRED_TIME=21:00        # Start time (24h)
   BOOKING_DAYS_AHEAD=7        # Days in advance
   DURATION_MINUTES=120        # 2 hours

   # Additional players (optional)
   PLAYER1_NAME=
   PLAYER2_NAME=
   PLAYER3_NAME=
   ```

## Usage

Run the script:
```bash
python src/tennis_booking.py
```

### Run Automatically on GitHub Actions

This repository includes a workflow at `.github/workflows/tennis_booking.yml` to run the booking script on a schedule (weekly Monday & Thursday at 9:01 PM Pacific, with both PDT and PST cron entries). You can also run it manually via the workflow_dispatch event.

1. Create the following Repository Secrets in GitHub (Settings → Secrets and variables → Actions → New repository secret):
   - `TENNIS_CLUB_URL`
   - `USERNAME`
   - `PASSWORD`
   - `PREFERRED_COURTS` (e.g., `3,4,5,2`)
   - `PREFERRED_TIME` (e.g., `21:00`)
   - `BOOKING_DAYS_AHEAD` (e.g., `7`)
   - `DURATION_MINUTES` (e.g., `120`)
   - `PLAYER1_NAME`
   - `PLAYER2_NAME`
   - `PLAYER3_NAME`
   - Optional: `LOG_LEVEL` (e.g., `INFO` or `DEBUG`)

2. The workflow will generate `tennis_booking/config/.env` from these secrets and run the script headlessly.

3. On failure, the workflow uploads debug artifacts (screenshots, HTML, and logs) to help diagnose issues.

### Running in Headless Mode (Config-driven)

Set an environment flag in `config/.env` to toggle headless mode without editing code:

```env
# Run Chrome in headless mode (accepted values: true/false, 1/0, yes/no, on/off)
HEADLESS=true
```

The script reads `HEADLESS` in `TennisCourtBooking._init_driver()` and, when enabled, uses `--headless=new` with a `1920x1080` window size. Set `HEADLESS=false` (or remove it) to run with a visible browser window.

Chrome password save prompts are disabled automatically via driver options.

## Features

- Automatic login to the tennis club website
- Navigation to the booking page
- Selection of preferred date (default: 7 days in advance)
- Automatic detection and booking of preferred court and time slot
- Tries a list of preferred courts in order (e.g., `3,4,5,2`)
- Supports selecting desired booking duration (e.g., 120 minutes)
- Optional filling of additional player names if required by the site
- Error handling and logging

## Customization

You may need to modify the following selectors in the `tennis_booking.py` file to match your tennis club's website structure:

- Login form selectors
- Booking page URL and selectors
- Date picker interaction
- Court and time slot selection logic
- Booking confirmation flow
- Duration controls (dropdown/radio) if applicable
- Additional player fields if applicable

## Logging

The script logs all actions to both the console and a `tennis_booking.log` file in the same directory.

## Notes

- This script is provided as a starting point and may need adjustments based on the specific tennis club website's structure.
- Be mindful of the tennis club's terms of service regarding automated bookings.
- The script includes a delay (`time.sleep(2)`) after date selection to ensure the page updates. Adjust as needed based on the website's response time.
- Keep your real credentials in `config/.env` and do not commit that file to source control.

## License

This project is for educational purposes only. Use it responsibly and in accordance with the tennis club's terms of service.
