# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a tennis court booking automation system that uses Selenium WebDriver to automatically book tennis courts at a club's website. The project is designed to run both locally and via GitHub Actions on a schedule.

## Core Architecture

### Main Components

**`tennis_booking/src/tennis_booking.py`** (~1600 lines)
- `TennisCourtBooking` class: Main orchestrator for the booking workflow
  - `login()`: Adaptive login using flexible selectors to find username/password fields
  - `navigate_to_booking_page()`: Navigates to the booking interface
  - `select_preferred_date()`: Calculates and selects future booking dates
  - `find_and_book_court()`: Core booking logic with court preference fallback
  - `_is_logged_in()`: Heuristic-based login state detection
  - `_init_driver()`: Chrome WebDriver initialization with stability enhancements
  - `_save_debug()`: Captures HTML and screenshots for debugging
- Uses environment-driven configuration via `.env` files
- Supports headless mode via `HEADLESS` env variable
- Implements retry logic and debug artifact generation

**`tennis_booking/src/notifications.py`**
- `SNSNotifier` class: AWS SNS integration for SMS notifications
- `send_booking_notification()`: Helper to send success/failure alerts
- Controlled via `ENABLE_SMS_NOTIFICATIONS` env variable

### Configuration

Environment variables are loaded from `tennis_booking/config/.env`:
- Required: `TENNIS_CLUB_URL`, `USERNAME`, `PASSWORD`
- Booking preferences: `PREFERRED_COURTS` (comma-separated list), `PREFERRED_TIME`, `BOOKING_DAYS_AHEAD`, `DURATION_MINUTES`
- Optional players: `PLAYER1_NAME`, `PLAYER2_NAME`, `PLAYER3_NAME`
- AWS SNS: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `SMS_PHONE_NUMBER`
- Behavior: `HEADLESS` (true/false), `LOG_LEVEL` (DEBUG/INFO)

Template available at `.test.env` for reference.

### GitHub Actions Workflow

`.github/workflows/tennis_booking.yml`:
- Scheduled runs: Monday & Thursday at 9:01 PM Pacific (handles both PDT/PST)
- Manual trigger via `workflow_dispatch`
- Secrets are injected into `tennis_booking/config/.env` at runtime
- Headless mode forced on CI
- Debug artifacts (screenshots, HTML, logs) uploaded on failure

## Common Commands

### Local Development

```bash
# Install dependencies
pip install -r tennis_booking/requirements.txt

# Run the booking script (uses config/.env)
python tennis_booking/src/tennis_booking.py

# Run tests
pytest tennis_booking/tests/

# Run specific test file
pytest tennis_booking/tests/test_notifications.py
pytest tennis_booking/tests/test_sms.py
```

### Environment Setup

```bash
# Create config directory and .env file
mkdir -p tennis_booking/config
cp .test.env tennis_booking/config/.env

# Edit with actual credentials
nano tennis_booking/config/.env
```

## Key Design Patterns

### Adaptive Element Detection
The booking script uses multiple selector strategies to find login fields, buttons, and booking elements. When modifying selectors:
- Check the arrays of selectors in `find_login_elements()` and similar functions
- Add new selectors to the list rather than replacing existing ones
- Test with `HEADLESS=false` to see element highlighting (red borders)

### Debug Artifacts
The script automatically saves HTML and screenshots to `tennis_booking/debug/` at key points:
- Before/after login
- During date selection
- Court selection attempts
- Booking confirmation
- On errors

These are critical for troubleshooting selector changes or site updates.

### Retry and Fallback Logic
- Login: 3 attempts
- Court selection: Tries each court in `PREFERRED_COURTS` order
- WebDriver initialization: 3 strategies (webdriver_manager, default, minimal options)

### Terminal Outcome Tracking
`_terminal_outcome` and `_terminal_message` capture the final booking state for notification purposes.

## Testing

Tests use `unittest` with mocking:
- `test_notifications.py`: SNS integration tests (mocks boto3)
- `test_sms.py`: Additional SMS notification tests

Run with pytest: `pytest tennis_booking/tests/` or `pytest -v` for verbose output.

## Dependencies

- `selenium>=4.15.0`: Browser automation
- `python-dotenv>=1.0.0`: Environment variable management
- `webdriver-manager>=4.0.0`: Automatic ChromeDriver management
- `boto3>=1.26.0`: AWS SNS for notifications
- `pytest==7.4.3`: Testing framework

## Important Notes for Code Changes

1. **Selector Updates**: When the tennis club website changes, update the selector arrays in the relevant methods. Always test multiple fallback selectors.

2. **Headless Mode**: Set `HEADLESS=false` in `config/.env` for local debugging. The script highlights found elements with red borders.

3. **Debug Directory**: Check `tennis_booking/debug/` for HTML/screenshots after failed runs to diagnose issues.

4. **Environment Variables**: Never commit `config/.env`. Use `.test.env` as a template and keep credentials in GitHub Secrets for Actions.

5. **Stability Options**: The WebDriver initialization includes extensive stability options. Be cautious when modifying `_init_driver()` as these prevent crashes in CI environments.

6. **Git Repository**: The output directory has its own git repository; use the git repository located in the output directory for version control operations related to generated site files.
