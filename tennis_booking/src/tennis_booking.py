import os
import time
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from notifications import send_booking_notification

# Configure logging (level may be overridden in __init__ after reading env)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tennis_booking.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TennisCourtBooking:
    def __init__(self):
        # Load environment variables
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'config', '.env'))
        
        self.base_url = os.getenv('TENNIS_CLUB_URL')
        self.username = os.getenv('USERNAME')
        self.password = os.getenv('PASSWORD')
        # Preferred courts may be a comma-separated list like "3,4,5,2"
        preferred_courts_raw = os.getenv('PREFERRED_COURTS') or os.getenv('PREFERRED_COURT', '1')
        self.preferred_courts = [int(c.strip()) for c in preferred_courts_raw.split(',') if c.strip().isdigit()]
        self.preferred_time = os.getenv('PREFERRED_TIME', '18:00')
        self.booking_days_ahead = int(os.getenv('BOOKING_DAYS_AHEAD', 7))
        self.duration_minutes = int(os.getenv('DURATION_MINUTES', 60))
        self.player1 = os.getenv('PLAYER1_NAME', '').strip()
        self.player2 = os.getenv('PLAYER2_NAME', '').strip()
        self.player3 = os.getenv('PLAYER3_NAME', '').strip()
        
        # Initialize WebDriver
        self.driver = self._init_driver()
        # Prepare debug directory
        self.debug_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'debug'))
        os.makedirs(self.debug_dir, exist_ok=True)
        
        # Control variables
        self._stop_scrolling = False
        self._logged_in_flag = False  # Track login state
        self._terminal_outcome = None  # 'success' or 'alert'
        self._terminal_message = None

        # Respect LOG_LEVEL from env if provided (e.g., DEBUG, INFO)
        log_level = os.getenv('LOG_LEVEL', '').upper().strip()
        if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
            logger.setLevel(getattr(logging, log_level))
        
    def _is_logged_in(self) -> bool:
        """Heuristically determine whether the user is logged in.
        Uses a cached flag when set, checks for common UI indicators like
        a Logout/Sign out link or presence of dashboard/account elements,
        and avoids false positives on pages containing 'login'.
        """
        try:
            # Fast-path: cached flag
            if getattr(self, "_logged_in_flag", False):
                return True

            # Check page content for obvious indicators
            try:
                page_text = (self.driver.page_source or "").lower()
            except Exception:
                page_text = ""

            if ("logout" in page_text) or ("sign out" in page_text):
                self._logged_in_flag = True
                return True

            # Look for typical elements implying an authenticated session
            indicators = [
                (By.XPATH, "//a[contains(translate(., 'LOGOUT','logout'),'logout') or contains(translate(., 'SIGN OUT','sign out'),'sign out')]"),
                (By.CSS_SELECTOR, "[href*='logout'], button.logout, a.logout"),
                (By.XPATH, "//a[contains(., 'Dashboard') or contains(., 'My Account') or contains(., 'Profile')]")
            ]
            for by, selector in indicators:
                try:
                    elems = self.driver.find_elements(by, selector)
                    for el in elems:
                        try:
                            if el.is_displayed():
                                self._logged_in_flag = True
                                return True
                        except Exception:
                            continue
                except Exception:
                    continue

            # URL heuristic: not on a login page and on a known authenticated path
            try:
                url = (self.driver.current_url or "").lower()
            except Exception:
                url = ""
            if "login" not in url and any(k in url for k in ["/dashboard", "/account", "/app"]):
                self._logged_in_flag = True
                return True

        except Exception:
            pass
        return False
    
    def _init_driver(self):
        """Initialize and return a Chrome WebDriver instance with stability enhancements."""
        from selenium.webdriver.chrome.service import Service as ChromeService
        from webdriver_manager.chrome import ChromeDriverManager
        
        # Configure Chrome options
        options = webdriver.ChromeOptions()
        
        # Basic options
        options.add_argument('--start-maximized')
        options.add_argument('--disable-notifications')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # Disable Chrome password save prompts and credential services
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
        }
        try:
            options.add_experimental_option("prefs", prefs)
        except Exception:
            pass
        
        # Performance optimizations
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-browser-side-navigation')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Disable features that might cause crashes
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-backgrounding-occluded-windows')
        
        # Experimental options for stability
        options.add_experimental_option('excludeSwitches', ['enable-automation', 'enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        # Further reduce password bubble popups
        options.add_argument('--disable-features=PasswordManagerOnboarding,AutofillServerCommunication,EnableSavePasswordBubble')
        
        # Config-driven headless mode
        try:
            headless_flag = os.getenv('HEADLESS', 'false').strip().lower()
            if headless_flag in ('1', 'true', 'yes', 'on'):
                # Use new headless mode for recent Chromes
                options.add_argument('--headless=new')
                # Ensure a reasonable viewport in headless
                options.add_argument('--window-size=1920,1080')
                logger.info("Running in headless mode (configured via HEADLESS env)")
        except Exception:
            pass
        
        # Set page load strategy to 'none' to prevent hanging on page loads
        options.page_load_strategy = 'none'
        
        # Try multiple initialization strategies
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                # Strategy 1: Try with webdriver_manager
                if attempt == 1:
                    try:
                        logger.info("Initializing Chrome WebDriver using webdriver_manager...")
                        service = ChromeService(ChromeDriverManager().install())
                        driver = webdriver.Chrome(service=service, options=options)
                        logger.info("Successfully initialized Chrome with webdriver_manager")
                        break
                    except Exception as e:
                        logger.warning(f"webdriver_manager initialization failed: {e}")
                
                # Strategy 2: Try with default service
                elif attempt == 2:
                    try:
                        logger.info("Initializing Chrome WebDriver with default service...")
                        driver = webdriver.Chrome(options=options)
                        logger.info("Successfully initialized Chrome with default service")
                        break
                    except Exception as e:
                        logger.warning(f"Default service initialization failed: {e}")
                
                # Strategy 3: Try with basic options only
                else:
                    try:
                        logger.info("Initializing Chrome with minimal options...")
                        basic_options = webdriver.ChromeOptions()
                        basic_options.add_argument('--no-sandbox')
                        basic_options.add_argument('--disable-dev-shm-usage')
                        driver = webdriver.Chrome(options=basic_options)
                        logger.info("Successfully initialized Chrome with minimal options")
                        break
                    except Exception as e:
                        logger.error(f"All Chrome initialization attempts failed: {e}")
                        raise
                
            except Exception as e:
                if attempt == max_attempts:
                    logger.error("All Chrome initialization attempts failed")
                    raise
                logger.info(f"Retrying Chrome initialization (attempt {attempt + 1}/{max_attempts})...")
                time.sleep(2)  # Wait before retry
        
        # Configure the driver
        try:
            # Set timeouts to prevent hanging
            driver.set_page_load_timeout(30)  # 30 seconds
            driver.set_script_timeout(30)     # 30 seconds
            
            # Disable Selenium's own command timeouts
            driver.command_executor.set_timeout(60)  # 60 seconds
            
            # Set window size explicitly
            driver.set_window_size(1920, 1080)
            
            # Execute CDP commands to prevent detection and improve stability
            driver.execute_cdp_cmd('Network.setCacheDisabled', {'cacheDisabled': False})
            driver.execute_cdp_cmd('Network.enable', {})
            
            # Add a basic test to verify the driver is working
            driver.get('about:blank')
            if 'about:blank' not in driver.current_url:
                raise Exception("Failed to load about:blank page")
                
            return driver
            
        except Exception as e:
            logger.error(f"Error configuring WebDriver: {e}")
            try:
                driver.quit()
            except:
                pass
            raise
    
    def login(self):
        """Login to the tennis club website using flexible field detection."""
        logger.info("Attempting to log in...")
        max_attempts = 3
        
        def save_debug_info(prefix):
            """Helper to save debug information."""
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                # Save screenshot
                screenshot_path = os.path.join(self.debug_dir, f'{prefix}_{timestamp}.png')
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"Saved screenshot: {screenshot_path}")
                # Save page source
                page_source_path = os.path.join(self.debug_dir, f'{prefix}_{timestamp}.html')
                with open(page_source_path, 'w', encoding='utf-8') as f:
                    f.write(self.driver.page_source)
                logger.info(f"Saved page source: {page_source_path}")
            except Exception as e:
                logger.error(f"Error saving debug info: {e}")
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Login attempt {attempt}/{max_attempts}")
                
                # Navigate to the login page
                login_url = f"{self.base_url.rstrip('/')}/login"
                logger.info(f"Navigating to login page: {login_url}")
                self.driver.get(login_url)
                time.sleep(3)  # Wait for page to load
                
                # Save debug info
                save_debug_info(f"login_attempt_{attempt}")
                
                logger.debug(f"Page title: {self.driver.title}")
                logger.debug(f"Current URL: {self.driver.current_url}")
                
                # Check if we're already logged in
                if self._is_logged_in():
                    logger.info("Already logged in")
                    return True
                
                def find_login_elements():
                    """Find login form elements using various selectors."""
                    # Common login form selectors
                    login_selectors = [
                        # Username/Email fields
                        {'type': 'user', 'by': By.NAME, 'value': 'username'},
                        {'type': 'user', 'by': By.NAME, 'value': 'email'},
                        {'type': 'user', 'by': By.ID, 'value': 'username'},
                        {'type': 'user', 'by': By.ID, 'value': 'email'},
                        {'type': 'user', 'by': By.CSS_SELECTOR, 'value': 'input[type="email"]'},
                        {'type': 'user', 'by': By.CSS_SELECTOR, 'value': 'input[autocomplete*="username"]'},
                        {'type': 'user', 'by': By.CSS_SELECTOR, 'value': 'input[autocomplete*="email"]'},
                        {'type': 'user', 'by': By.CSS_SELECTOR, 'value': 'input[placeholder*="email" i]'},
                        {'type': 'user', 'by': By.CSS_SELECTOR, 'value': 'input[placeholder*="username" i]'},
                        
                        # Password fields
                        {'type': 'pass', 'by': By.NAME, 'value': 'password'},
                        {'type': 'pass', 'by': By.ID, 'value': 'password'},
                        {'type': 'pass', 'by': By.CSS_SELECTOR, 'value': 'input[type="password"]'},
                        {'type': 'pass', 'by': By.CSS_SELECTOR, 'value': 'input[autocomplete*="current-password"]'},
                        {'type': 'pass', 'by': By.CSS_SELECTOR, 'value': 'input[placeholder*="password" i]'},
                        
                        # Submit buttons
                        {'type': 'submit', 'by': By.CSS_SELECTOR, 'value': 'button[type="submit"]'},
                        {'type': 'submit', 'by': By.CSS_SELECTOR, 'value': 'input[type="submit"]'},
                        {'type': 'submit', 'by': By.XPATH, 'value': '//button[contains(translate(., "LOGIN", "login"), "login")]'},
                        {'type': 'submit', 'by': By.XPATH, 'value': '//input[contains(translate(@value, "LOGIN", "login"), "login")]'},
                        {'type': 'submit', 'by': By.XPATH, 'value': '//button[contains(translate(., "SIGN IN", "sign in"), "sign in")]'},
                        {'type': 'submit', 'by': By.XPATH, 'value': '//input[contains(translate(@value, "SIGN IN", "sign in"), "sign in")]'},
                    ]
                    
                    elements = {'user': None, 'pass': None, 'submit': None}
                    
                    for selector in login_selectors:
                        try:
                            elem_type = selector['type']
                            if elements[elem_type] is not None:
                                continue  # Already found this element type
                                
                            elems = self.driver.find_elements(selector['by'], selector['value'])
                            for elem in elems:
                                try:
                                    if elem.is_displayed() and elem.is_enabled():
                                        elements[elem_type] = elem
                                        logger.info(f"Found {elem_type} element: {selector['by']}={selector['value']}")
                                        # Highlight the found element for debugging
                                        try:
                                            self.driver.execute_script("arguments[0].style.border='3px solid red';", elem)
                                        except:
                                            pass
                                        break
                                except:
                                    continue
                                
                        except Exception as e:
                            logger.debug(f"Error finding element {selector}: {e}")
                            continue
                            
                    return elements
                
                # Find login elements
                login_elements = find_login_elements()
                
                # If we found all required elements, try to log in
                if login_elements['user'] and login_elements['pass']:
                    try:
                        # Take a screenshot before entering credentials
                        save_debug_info(f"login_before_credentials_{attempt}")
                        
                        # Enter username
                        logger.info("Entering username...")
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", login_elements['user'])
                        login_elements['user'].clear()
                        login_elements['user'].send_keys(self.username)
                        time.sleep(0.5)
                        
                        # Enter password
                        logger.info("Entering password...")
                        self.driver.execute_script("arguments[0].scrollIntoView(true);", login_elements['pass'])
                        login_elements['pass'].clear()
                        login_elements['pass'].send_keys(self.password)
                        time.sleep(0.5)
                        
                        # Save screenshot after entering credentials
                        save_debug_info(f"login_after_credentials_{attempt}")
                        
                        # Try to submit the form
                        if login_elements['submit']:
                            logger.info("Clicking submit button...")
                            try:
                                # Try clicking with JavaScript first
                                self.driver.execute_script("arguments[0].click();", login_elements['submit'])
                            except:
                                # Fall back to regular click
                                login_elements['submit'].click()
                        else:
                            # Try to submit by pressing Enter in the password field
                            logger.info("Submitting form by pressing Enter...")
                            login_elements['pass'].send_keys(Keys.RETURN)
                        
                        # Wait for login to complete
                        logger.info("Waiting for login to complete...")
                        time.sleep(3)
                        
                        # Save screenshot after submission
                        save_debug_info(f"login_after_submit_{attempt}")
                        
                        # Wait for URL change or a known post-login indicator
                        try:
                            WebDriverWait(self.driver, 10).until(
                                lambda d: "login" not in d.current_url.lower() or self._is_logged_in()
                            )
                            logger.info("Login successful (URL changed or login indicator found).")
                        except TimeoutException:
                            logger.warning("Login may not have completed as expected")
                        
                        # Check for login errors
                        error_messages = self.driver.find_elements(By.XPATH, 
                            "//*[contains(translate(., 'ERROR', 'error'), 'error') or "
                            "contains(translate(., 'INVALID', 'invalid'), 'invalid') or "
                            "contains(translate(., 'FAILED', 'failed'), 'failed')]"
                        )
                        
                        if error_messages:
                            logger.warning(f"Possible login error: {error_messages[0].text}")
                            save_debug_info(f"login_error_message_{attempt}")
                        
                        # Verify login was successful
                        if self._is_logged_in():
                            logger.info("Login verification successful")
                            # Save final screenshot
                            save_debug_info("login_success")
                            return True
                            
                        logger.warning("Login may not have been successful")
                        
                    except Exception as e:
                        logger.error(f"Error during login attempt: {e}")
                        save_debug_info(f"login_error_{attempt}")
                        # Try to capture any error messages
                        try:
                            alerts = self.driver.find_elements(By.CSS_SELECTOR, ".alert, .error, .message")
                            for alert in alerts:
                                if alert.is_displayed():
                                    logger.warning(f"Alert message: {alert.text}")
                        except:
                            pass
                else:
                    logger.error("Could not find required login form elements")
                    save_debug_info("login_missing_elements")
                    # Try to find any clickable elements that might lead to login
                    try:
                        login_links = self.driver.find_elements(By.XPATH, 
                            "//a[contains(translate(., 'LOGIN', 'login'), 'login') or "
                            "contains(translate(., 'SIGN IN', 'sign in'), 'sign in')]"
                        )
                        if login_links:
                            logger.info(f"Found {len(login_links)} possible login links, trying the first one...")
                            self.driver.execute_script("arguments[0].click();", login_links[0])
                            time.sleep(3)
                            continue
                    except Exception as e:
                        logger.debug(f"Error looking for login links: {e}")
                
                # If we get here, login failed or elements not found
                if attempt < max_attempts:
                    logger.info(f"Login attempt {attempt} failed, retrying...")
                    # Try refreshing the page before retry
                    try:
                        self.driver.refresh()
                        time.sleep(3)
                    except:
                        time.sleep(2)  # Fallback wait
                
            except Exception as e:
                logger.error(f"Error during login attempt {attempt}: {e}")
                self._save_debug(f"login_error_attempt_{attempt}")
                if attempt == max_attempts:
                    logger.error("Max login attempts reached")
                    raise
                time.sleep(2)  # Wait before retry
        
        logger.error("All login attempts failed")
        self._save_debug("login_failure")
        return False
    
    def navigate_to_booking_page(self):
        """Navigate to the court booking page."""
        logger.info("Navigating to booking page...")
        try:
            # Adjust the URL and selectors based on the actual website
            # First, click "To Dashboard" if visible (sometimes login lands elsewhere)
            try:
                dashboard_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//a[normalize-space()='To Dashboard' or contains(normalize-space(.), 'To Dashboard')] | //button[normalize-space()='To Dashboard' or contains(normalize-space(.), 'To Dashboard')]"))
                )
                self.driver.execute_script("arguments[0].click();", dashboard_btn)
                time.sleep(2)
            except TimeoutException:
                pass

            # Prefer direct grid path if available for Burnaby site
            tried_paths = ["/app/bookings/grid", "/court-booking", "/bookings", "/booking", "/book-online", "/reserve", "/courts"]
            navigated = False
            base = self.base_url.rstrip('/')
            for path in tried_paths:
                self.driver.get(f"{base}{path}")
                time.sleep(2)
                if "404" not in self.driver.title and "Not Found" not in self.driver.page_source:
                    navigated = True
                    break
            if not navigated:
                # Try clicking a nav link or button from Dashboard
                link = None
                for xpath in [
                    "//a[normalize-space()='Booking Grid' or contains(translate(., 'BOOKING GRID', 'booking grid'), 'booking grid')]",
                    "//button[normalize-space()='Booking Grid' or contains(translate(., 'BOOKING GRID', 'booking grid'), 'booking grid')]",
                    "//a[contains(translate(., 'COURT BOOKING', 'court booking'), 'court booking') or contains(translate(., 'COURT BOOKINGS', 'court bookings'), 'court bookings') or contains(translate(., 'BOOK', 'book'), 'book')]",
                    "//a[contains(translate(., 'RESERVE', 'reserve'), 'reserve')]",
                ]:
                    elems = self.driver.find_elements(By.XPATH, xpath)
                    if elems:
                        link = elems[0]
                        break
                if link:
                    self.driver.execute_script("arguments[0].click();", link)
                    time.sleep(2)
                else:
                    raise NoSuchElementException("Could not find booking page link")
            # Wait for a heading or calendar/grid to confirm page
            try:
                WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.XPATH, "//h1[contains(translate(., 'COURT BOOKINGS', 'court bookings'), 'court bookings')] | //div[contains(@class, 'booking-calendar')] | //div[contains(@class, 'booking-grid') or contains(@class,'grid')]"))
                )
            except TimeoutException:
                # Not strictly necessary; proceed with next steps but we saved debug on failure
                pass
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to booking page: {str(e)}")
            self._save_debug("navigate_booking_failure")
            return False
    
    def select_preferred_date(self):
        """Select the preferred booking date (7 days from today by default)."""
        target_date = (datetime.now() + timedelta(days=self.booking_days_ahead)).strftime("%Y-%m-%d")
        logger.info(f"Selecting booking date: {target_date}")
        
        try:
            # Preferred Strategy for Burnaby grid: click the day tab like "Wed 24th"
            try:
                label = self._format_day_tab_label(self.booking_days_ahead)
                if self._click_day_tab_if_present(label):
                    logger.info(f"Clicked day tab '{label}'")
                else:
                    logger.debug(f"Day tab '{label}' not found; trying generic date inputs")
            except Exception as e:
                logger.debug(f"Day tab click skipped: {e}")
            # After switching the day, nudge scroll to top then down a bit to ensure grid loads rows
            try:
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.2)
                self._nudge_scroll()
            except Exception:
                pass

            # Strategy A: native date input
            date_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='date']")
            if date_inputs:
                date_picker = date_inputs[0]
                self.driver.execute_script("arguments[0].focus();", date_picker)
                self.driver.execute_script(f"arguments[0].value = '{target_date}';", date_picker)
                self.driver.execute_script("arguments[0].dispatchEvent(new Event('change', {bubbles: true}))", date_picker)
                time.sleep(2)
            else:
                # Strategy B: text input with date
                candidates = []
                selectors = [
                    (By.CSS_SELECTOR, "input[name*='date' i]"),
                    (By.CSS_SELECTOR, "input[placeholder*='date' i]"),
                    (By.XPATH, "//input[contains(translate(@aria-label,'DATE','date'),'date')]")
                ]
                for by, sel in selectors:
                    elems = self.driver.find_elements(by, sel)
                    if elems:
                        candidates = elems
                        break
                if candidates:
                    date_input = candidates[0]
                    date_input.clear()
                    date_input.send_keys(target_date)
                    date_input.send_keys("\n")
                    time.sleep(2)
                else:
                    # Strategy C: click date picker button and pick from calendar (try to open calendar)
                    opened = False
                    for opener in self.driver.find_elements(By.XPATH, "//button[contains(@class,'date') or contains(@aria-label,'date') or contains(., 'Date')]"):
                        try:
                            self.driver.execute_script("arguments[0].click();", opener)
                            time.sleep(1)
                            opened = True
                            break
                        except Exception:
                            continue
                    if opened:
                        # Try selecting day by data-date or text
                        y, m, d = target_date.split('-')
                        picked = False
                        for xpath in [
                            f"//td[@data-date='{target_date}']",
                            f"//button[@data-date='{target_date}']",
                            f"//td//button[normalize-space()='{int(d)}']",
                        ]:
                            elems = self.driver.find_elements(By.XPATH, xpath)
                            if elems:
                                self.driver.execute_script("arguments[0].click();", elems[0])
                                picked = True
                                break
                        if picked:
                            time.sleep(2)
                        else:
                            logger.debug("Calendar opened but could not pick the target date")
                    else:
                        # Strategy D: use next/prev day navigation n times
                        # Look for Next buttons and click delta days
                        try:
                            today_label = self.driver.find_element(By.XPATH, "//span[contains(@class,'date') or contains(@class,'current-date')]")
                            # If we can parse displayed date, compute delta here (skipped due to variability)
                        except Exception:
                            pass
                        # Blindly click Next day up to booking_days_ahead times
                        for _ in range(self.booking_days_ahead):
                            next_btns = self.driver.find_elements(By.XPATH, "//button[contains(translate(., 'NEXT', 'next'), 'next') or contains(@aria-label,'Next')]")
                            if not next_btns:
                                break
                            self.driver.execute_script("arguments[0].click();", next_btns[0])
                            time.sleep(0.8)

            # Attempt to set duration if there is a control for it
            self._select_duration_if_available()
            return True
            
        except Exception as e:
            logger.error(f"Failed to select date: {str(e)}")
            self._save_debug("select_date_failure")
            return False

    def find_and_book_court(self):
        """Find and book the first available court (from preferred list) at the preferred time."""
        logger.info(f"Looking for courts {self.preferred_courts} at {self.preferred_time} for {self.duration_minutes} minutes")
        
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_retries} to book court...")

                # Ensure the page and grid are ready
                try:
                    WebDriverWait(self.driver, 15).until(
                        lambda d: d.execute_script('return document.readyState') == 'complete'
                    )
                    WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//div[contains(@class,'grid') or contains(@class,'booking-grid') or self::table] | //div[contains(@class,'MuiBox-root')]//p[contains(text(),'Court')]"
                        ))
                    )
                except Exception as e:
                    logger.warning(f"Grid not found on attempt {attempt}: {str(e)}")
                    if attempt < max_retries:
                        time.sleep(retry_delay)
                        continue
                    raise

                # Click the day tab again just in case the grid defaulted to another day
                try:
                    label = self._format_day_tab_label(self.booking_days_ahead)
                    if self._click_day_tab_if_present(label):
                        time.sleep(1)
                except Exception as e:
                    logger.debug(f"Could not click day tab: {str(e)}")

                # Prepare time labels
                time_label = self._format_time_label(self.preferred_time)
                time_variants = self._time_label_variants(self.preferred_time, time_label)
                logger.debug(f"Using time variants: {time_variants}")

                # Scroll grid to make time visible
                for scroll_attempt in range(3):
                    try:
                        self._scroll_to_grid_end()
                        time.sleep(0.5)
                        self._scroll_time_into_view(time_label)
                        time.sleep(0.5)
                        break
                    except Exception as e:
                        logger.debug(f"Scroll attempt {scroll_attempt + 1} failed: {str(e)}")
                        if scroll_attempt == 2:
                            logger.warning("Failed to properly scroll the grid")
                        time.sleep(0.5)

                # Ensure book buttons are present
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//button[contains(translate(., 'BOOK', 'book'), 'book')] | //div[contains(@class,'MuiButton-root')]//p[contains(translate(., 'BOOK', 'book'), 'book')]"
                        ))
                    )
                except Exception as e:
                    logger.debug(f"No book buttons found initially: {str(e)}")

                # Try booking strategies per court
                for court_number in self.preferred_courts:
                    logger.info(f"Attempting to book Court {court_number} at {time_label}")

                    strategies = [
                        ("Burnaby Column Time Click", lambda cn, tl: self._try_burnaby_column_time_click(cn, tl)),
                        ("Click Book Button Label", lambda cn, _: self._try_click_book_button_label(cn, time_variants)),
                        ("Table Grid Book", lambda cn, tl: self._try_table_grid_book(cn, tl)),
                        ("Data Attr Grid Book", lambda cn, tl: self._try_data_attr_grid_book(cn, tl)),
                        ("Heuristic Book", lambda cn, tl: self._try_heuristic_book(cn, tl)),
                        ("JS Scan and Click", lambda cn, _: self._try_js_scan_and_click(cn, time_variants)),
                    ]

                    for strategy_name, strategy_func in strategies:
                        try:
                            logger.debug(f"Trying strategy: {strategy_name}")
                            if strategy_func(court_number, time_label):
                                logger.info(f"Successfully booked court using strategy: {strategy_name}")
                                return True
                            # If _confirm_booking() set a terminal outcome, stop immediately
                            if self._terminal_outcome == 'alert':
                                logger.error(f"Stopping after booking alert: {self._terminal_message}")
                                return False
                            if self._terminal_outcome == 'success':
                                logger.info("Stopping: terminal success state reached.")
                                return True
                        except Exception as e:
                            logger.debug(f"Strategy {strategy_name} failed: {str(e)}")
                            try:
                                self.driver.save_screenshot(f"error_{strategy_name.lower().replace(' ', '_')}.png")
                            except Exception:
                                pass

                    # If we have an alert or success state after trying strategies for this court, stop
                    if self._terminal_outcome == 'alert':
                        logger.error(f"Terminating after alert: {self._terminal_message}")
                        return False
                    if self._terminal_outcome == 'success':
                        logger.info("Terminating after success state.")
                        return True

                    logger.info(f"Could not book Court {court_number} at {time_label}; trying next preferred court")

                # If we get here in this attempt without success
                # If a terminal outcome was set, don't retry
                if self._terminal_outcome == 'alert':
                    logger.error(f"Not retrying due to alert: {self._terminal_message}")
                    return False
                if self._terminal_outcome == 'success':
                    logger.info("Not retrying due to success state.")
                    return True

                if attempt < max_retries:
                    logger.info(f"Retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error during court booking (attempt {attempt}/{max_retries}): {error_msg}", exc_info=True)
                self._save_debug(f"booking_error_attempt{attempt}")

                if "chrome not reachable" in error_msg.lower() or "session deleted" in error_msg.lower():
                    logger.warning("Chrome appears to have crashed, attempting to reinitialize...")
                    try:
                        self.driver.quit()
                    except Exception:
                        pass
                    self.driver = self._init_driver()
                    self.login()
                    self.navigate_to_booking_page()
                    self.select_preferred_date()

                if attempt == max_retries:
                    logger.error("All attempts to book court failed")
                    return False

                time.sleep(retry_delay)

        # If we get here, no court was booked after all retries
        return False

    def _try_burnaby_column_time_click(self, court_number: int, time_label: str) -> bool:
        """Use the observed DOM: each court column is a div.MuiBox-root.css-0 containing a header <p> 'Court N' and a list of <button>s.
        Find the column for the given court and click the button with nested <p> exactly 'Book <time_label>'.
        """
        try:
            # Set flag to stop any ongoing scrolling
            self._stop_scrolling = True

            # Scroll to make sure the time is visible
            self._scroll_time_into_view(time_label)

            # Find all court columns
            court_columns = self.driver.find_elements(By.CSS_SELECTOR, "div.MuiBox-root.css-0")

            for column in court_columns:
                try:
                    # Check if this is the right court column
                    header = column.find_element(By.TAG_NAME, "p")
                    if f"Court {court_number}" in header.text:
                        # Find all book buttons in this column
                        buttons = column.find_elements(By.TAG_NAME, "button")
                        for button in buttons:
                            try:
                                # Look for a <p> tag inside the button with the exact time text
                                p_tags = button.find_elements(By.TAG_NAME, "p")
                                for p in p_tags:
                                    if p.text.strip() == f"Book {time_label}":
                                        # Scroll the button into view
                                        self.driver.execute_script("""
                                            arguments[0].scrollIntoView({
                                                behavior: 'smooth',
                                                block: 'center',
                                                inline: 'nearest'
                                            });
                                            window.scrollBy(0, -100);  // Adjust for any fixed headers
                                        """, button)
                                        time.sleep(0.5)  # Allow time for scrolling

                                        # Click the button
                                        self.driver.execute_script("arguments[0].click();", button)
                                        logger.info(f"Clicked 'Book {time_label}' button for Court {court_number}")

                                        # Handle the booking dialog
                                        return self._handle_booking_dialog()

                            except Exception as e:
                                logger.debug(f"Error checking button: {e}")
                                continue
                except Exception as e:
                    logger.debug(f"Error checking column: {e}")
                    continue

            return False
        except Exception as e:
            logger.error(f"_try_burnaby_column_time_click failed: {e}")
            return False
        
    def _handle_booking_dialog(self):
        """Handle the booking dialog after clicking a time slot."""
        try:
            # Stop any ongoing scrolling
            self._stop_scrolling = True
            
            # Wait for the dialog to appear
            try:
                dialog = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR, 
                        "div[role='dialog'], .MuiDialog-root, .booking-dialog"
                    ))
                )
                logger.info("Booking dialog appeared")
            except Exception as e:
                logger.error("Booking dialog did not appear after clicking time slot")
                self._save_debug("dialog_not_found")
                return False
            
            # Handle the booking form
            if not self._handle_booking_form():
                logger.error("Failed to handle booking form")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error in _handle_booking_dialog: {e}")
            self._save_debug("dialog_error")
            return False
            
    def _handle_booking_form(self):
        """Handle the booking form in the dialog."""
        try:
            # Add players
            if not self._fill_additional_players_if_required():
                logger.warning("Could not fill player names")
                
            # Select duration
            if not self._select_duration_if_available():
                logger.warning("Could not select duration")
                
            # Confirm booking
            return self._confirm_booking()
            
        except Exception as e:
            logger.error(f"Error handling booking form: {e}")
            self._save_debug("booking_form_error")
            return False
            
    def _time_label_variants(self, time_24h: str, pretty: str) -> list:
        """Return a list of common textual variants for a time label (e.g., '21:00' -> ['9:00 pm','9 pm','9pm','21:00','21'])."""
        try:
            dt = datetime.strptime(time_24h, '%H:%M')
            h24 = int(dt.strftime('%H'))
            m = int(dt.strftime('%M'))
            ampm = 'pm' if h24 >= 12 else 'am'
            h12 = h24 % 12 or 12
            variants = set()
            variants.add(pretty)                  # e.g., '9:00 pm'
            variants.add(f"{h12}:{m:02d}{ampm}")  # '9:00pm'
            variants.add(f"{h12} {ampm}")         # '9 pm'
            variants.add(f"{h12}{ampm}")          # '9pm'
            variants.add(time_24h)                # '21:00'
            variants.add(f"{h24}")               # '21'
            return list(variants)
        except Exception:
            return [pretty, time_24h]

    def _button_in_court_column(self, button_el, court_number: int) -> bool:
        """Try to determine if the given button is within the desired court column by inspecting ancestor text or headers."""
        try:
            # Quick heuristic: check nearby ancestor text
            try:
                ancestor_text = button_el.find_element(By.XPATH, "ancestor::*[position()<=3]").text.lower()
                if f"court {court_number}" in ancestor_text or f"court #{court_number}" in ancestor_text:
                    return True
            except Exception:
                pass

            # Table-based check: compare column index with header label
            try:
                cell = button_el.find_element(By.XPATH, "ancestor::td[1] | ancestor::*[@role='cell'][1]")
                # Count index within row
                siblings = cell.find_elements(By.XPATH, "preceding-sibling::td | preceding-sibling::*[@role='cell']")
                col_idx = len(siblings) + 1
                # Map to header text
                header = cell.find_element(By.XPATH, f"ancestor::table[1]//thead//th[{col_idx}] | ancestor::*[contains(@class,'grid')]//*[self::th or self::div or self::span][{col_idx}]")
                header_text = header.text.strip().lower()
                if (
                    f"court {court_number}" in header_text or
                    f"court #{court_number}" in header_text or
                    header_text == str(court_number) or
                    header_text == f"#{court_number}"
                ):
                    return True
            except Exception:
                pass
            return False
        except Exception:
            return False

    def _format_day_tab_label(self, days_ahead: int) -> str:
        """Return a label like 'Wed 24th' for the target day."""
        target = datetime.now() + timedelta(days=days_ahead)
        dow = target.strftime('%a')  # Mon, Tue, Wed
        day = int(target.strftime('%d'))
        # Ordinal suffix
        if 11 <= day % 100 <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return f"{dow} {day}{suffix}"

    def _click_day_tab_if_present(self, label: str) -> bool:
        """Click a day tab button if its label is present. Returns True if clicked."""
        try:
            # Look for exact or partial match ignoring case and extra spaces
            xpath_btn = (
                f"//a[normalize-space()='{label}' or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label.lower()}')] | "
                f"//button[normalize-space()='{label}' or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label.lower()}')]"
            )
            elems = self.driver.find_elements(By.XPATH, xpath_btn)
            if elems:
                self.driver.execute_script("arguments[0].click();", elems[0])
                time.sleep(1.5)
                return True

            # Support chips where the label is inside a span (e.g., MUI Chip)
            xpath_span = (
                f"//span[contains(@class,'MuiChip-label')][normalize-space()='{label}' or contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{label.lower()}')]"
            )
            spans = self.driver.find_elements(By.XPATH, xpath_span)
            if spans:
                # Click nearest clickable ancestor (button or chip root)
                try:
                    clickable = spans[0].find_element(By.XPATH, "ancestor::button | ancestor::a | ancestor::*[contains(@class,'MuiChip')][1]")
                except Exception:
                    clickable = spans[0]
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", clickable)
                self.driver.execute_script("arguments[0].click();", clickable)
                time.sleep(1.5)
                return True
            return False
        except Exception:
            return False

    def _format_time_label(self, time_24h: str) -> str:
        """Convert '21:00' to '9:00 pm' to match typical grid labels."""
        try:
            dt = datetime.strptime(time_24h, '%H:%M')
            return dt.strftime('%-I:%M %p').lower()
        except Exception:
            # macOS strftime supports %-I, but if not, fall back
            hour, minute = map(int, time_24h.split(':'))
            ampm = 'am' if hour < 12 else 'pm'
            hour12 = hour % 12 or 12
            return f"{hour12}:{minute:02d} {ampm}"
 
    def _nudge_scroll(self):
        """Perform a small scroll up and down to trigger lazy loading or grid render."""
        try:
            self.driver.execute_script("window.scrollBy(0, -200);")
            time.sleep(0.1)
            self.driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.1)
        except Exception:
            pass
    
    def _scroll_to_grid_end(self):
        """Scroll to the bottom of the page or grid container to ensure elements render."""
        try:
            # Try to find a grid container and scroll it
            containers = self.driver.find_elements(By.XPATH, "//div[contains(@class,'grid') or contains(@class,'booking-grid') or contains(@class,'MuiBox-root')]")
            for c in containers[:3]:
                try:
                    self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", c)
                except Exception:
                    continue
            # Also scroll the window
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
    
    def _scroll_time_into_view(self, time_label: str):
        """Attempt to locate a time label (like '9:00 pm') and scroll it into view."""
        try:
            # Try different xpath patterns to find displayed time labels
            xpaths = [
                f"//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{time_label.lower()}')]",
                f"//p[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{time_label.lower()}')]",
                f"//span[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{time_label.lower()}')]",
            ]
            for xp in xpaths:
                elems = self.driver.find_elements(By.XPATH, xp)
                for el in elems:
                    try:
                        if el.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            return
                    except Exception:
                        continue
            # If not found, nudge scroll a bit
            self._nudge_scroll()
        except Exception:
            pass
 
    def _try_table_grid_book(self, court_number: int, time_label: str) -> bool:
        """Handle a table-based grid by finding column 'Court N' and row with time label."""
        try:
            # Ensure the time row is visible by scrolling
            self._scroll_time_into_view(time_label)
            # Find headers
            headers = self.driver.find_elements(By.XPATH, "//table//thead//th | //div[contains(@class,'grid-header')]//*[self::div or self::span or self::th]")
            header_texts = [h.text.strip() for h in headers if h.text.strip()]
            if header_texts:
                logger.debug(f"Grid headers detected: {header_texts}")
            if not header_texts:
                return False
            # Determine court column index (1-based for XPath)
            target_header_idx = None
            for idx, txt in enumerate(header_texts, start=1):
                low = txt.lower()
                if (
                    f"court {court_number}" in low or
                    f"court #{court_number}" in low or
                    low.strip() == f"{court_number}" or
                    low.strip() == f"#{court_number}"
                ):
                    target_header_idx = idx
                    break
            if not target_header_idx:
                return False

            # Find the row index by time label in first column
            rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
            row_idx = None
            for i, row in enumerate(rows, start=1):
                first_cell_text = ''
                try:
                    first_cell_text = row.find_element(By.XPATH, "./th|./td[1]").text.strip().lower()
                except Exception:
                    pass
                if i <= 5 and first_cell_text:
                    logger.debug(f"Row {i} first cell: {first_cell_text}")
                if time_label in first_cell_text:
                    row_idx = i
                    break
            if not row_idx:
                # Try scrolling further down to find more rows
                for _ in range(6):
                    if not self._scroll_time_into_view(time_label):
                        break
                    rows = self.driver.find_elements(By.XPATH, "//table//tbody//tr")
                    for i, row in enumerate(rows, start=1):
                        try:
                            first_cell_text = row.find_element(By.XPATH, "./th|./td[1]").text.strip().lower()
                        except Exception:
                            first_cell_text = ''
                        if time_label in first_cell_text:
                            row_idx = i
                            break
                    if row_idx:
                        break
            if not row_idx:
                return False

            # Locate the target cell and look for a Book button
            cell_xpath = f"(//table//tbody//tr)[{row_idx}]//td[{target_header_idx}]//button| (//table//tbody//tr)[{row_idx}]//td[{target_header_idx}]//a"
            buttons = self.driver.find_elements(By.XPATH, cell_xpath)
            for btn in buttons:
                if 'book' in btn.text.strip().lower():
                    self.driver.execute_script("arguments[0].click();", btn)
                    self._select_duration_if_available()
                    self._fill_additional_players_if_required()
                    if self._confirm_booking():
                        return True
            return False
        except Exception:
            return False

    def _try_data_attr_grid_book(self, court_number: int, time_label: str) -> bool:
        """Handle grids exposing data attributes like data-court and data-time."""
        try:
            self._scroll_time_into_view(time_label)
            # Generate possible values for data-time
            dt24 = self.preferred_time
            candidates = [dt24, time_label, time_label.upper()]
            for val in candidates:
                xpath = (
                    f"//*[@data-court='{court_number}' and (@data-time='{dt24}' or contains(translate(@data-time,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{time_label}'))]"
                    "//*[self::button or self::a]"
                )
                buttons = self.driver.find_elements(By.XPATH, xpath)
                for btn in buttons:
                    if 'book' in btn.text.strip().lower():
                        self.driver.execute_script("arguments[0].click();", btn)
                        self._select_duration_if_available()
                        self._fill_additional_players_if_required()
                        if self._confirm_booking():
                            return True
            return False
        except Exception:
            return False

    def _try_heuristic_book(self, court_number: int, time_label: str) -> bool:
        """Last-resort: search for 'Book' buttons and filter by nearby court/time labels."""
        try:
            self._scroll_time_into_view(time_label)
            buttons = self.driver.find_elements(By.XPATH, "//button[contains(translate(., 'BOOK', 'book'), 'book')] | //a[contains(translate(., 'BOOK', 'book'), 'book')]")
            for btn in buttons:
                ancestor_text = btn.find_element(By.XPATH, "ancestor::*[position()<=3]").text.lower()
                if f"court {court_number}" in ancestor_text and (time_label in ancestor_text or self.preferred_time in ancestor_text):
                    self.driver.execute_script("arguments[0].click();", btn)
                    self._select_duration_if_available()
                    self._fill_additional_players_if_required()
                    if self._confirm_booking():
                        return True
            return False
        except Exception:
            return False
    def _select_duration_if_available(self):
        """Attempt to select the desired duration on the page if a control exists."""
        try:
            # Prefer selecting within the open dialog
            container = None
            try:
                container = self.driver.find_element(By.XPATH, "//div[@role='dialog' or contains(@class,'Dialog') or contains(@class,'booking-dialog')]")
            except Exception:
                container = self.driver

            # Click a button labeled "2.0 hr" or variants
            xpaths = [
                "//button[contains(normalize-space(.), '2.0 hr')]",
                "//button[contains(normalize-space(.), '2 hr')]",
                "//button[contains(normalize-space(.), '2hr')]",
                "//button[contains(translate(., 'HOUR','hour'),'2 hour')]",
            ]
            for xp in xpaths:
                try:
                    btns = container.find_elements(By.XPATH, xp)
                    for b in btns:
                        if b.is_displayed() and b.is_enabled():
                            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                            self.driver.execute_script("arguments[0].click();", b)
                            logger.info("Selected duration: 2 hours")
                            self.duration_minutes = 120
                            return True
                except Exception:
                    continue

            # Fallback to other duration selection methods if 2-hour button not found
            logger.debug("2-hour button not found, trying other duration selectors...")
            try:
                radios = container.find_elements(
                    By.XPATH,
                    "//label[contains(., '2.0 hr') or contains(., '2 hr')]/preceding::input[1] | "
                    "//input[@type='radio' and (contains(@value,'120') or contains(@aria-label,'2'))]"
                )
                for r in radios:
                    try:
                        if r.is_displayed() and r.is_enabled():
                            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", r)
                            self.driver.execute_script("arguments[0].click();", r)
                            logger.info("Selected duration via radio: 2 hours")
                            self.duration_minutes = 120
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

            logger.warning("Could not find 2-hour duration control, using default duration")
            return False
        except Exception as e:
            logger.error(f"Error in duration selection: {e}")
            return False

    def _fill_additional_players_if_required(self):
        """Fill in additional player names following strict sequence:
        - Type into Player 2
        - Wait 1s
        - Click "+ Add Player" and wait 1s
        - Type next player
        - Repeat until all additional players entered
        """
        try:
            names = [n for n in [self.player1, self.player2, self.player3] if n]
            if not names:
                logger.info("No additional player names provided in config")
                return False

            logger.info(f"Filling players in strict order: {names}")

            # Work within dialog if present
            try:
                dialog = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//div[@role='dialog' or contains(@class,'Dialog') or contains(@class,'booking-dialog')]"))
                )
            except Exception:
                dialog = self.driver

            def find_player_input_by_label(label_text: str):
                # Try label above input: //*[text()='Player 2']/following::input[1]
                xpaths = [
                    f"//*[normalize-space(text())='{label_text}']/following::input[1]",
                    f"//label[contains(normalize-space(.), '{label_text}')]/following::input[1]",
                    f"//input[contains(@placeholder, '{label_text.split()[-1]}')]",
                ]
                for xp in xpaths:
                    els = dialog.find_elements(By.XPATH, xp)
                    for el in els:
                        if el.is_displayed():
                            return el
                return None

            def list_inputs():
                return [e for e in dialog.find_elements(By.CSS_SELECTOR, "input") if e.is_displayed()]

            # Helper: pick from autocomplete dropdown for a given input
            def _pick_from_dropdown(inp):
                try:
                    # Try ARROWDOWN then ENTER to select the top suggestion
                    try:
                        inp.send_keys(Keys.ARROW_DOWN)
                        time.sleep(1.0)  # allow dropdown to render highlighted option
                        inp.send_keys(Keys.ENTER)
                        return True
                    except Exception:
                        pass

                    # Try clicking the first visible option in listbox/option elements
                    containers = dialog.find_elements(By.XPATH, "//*[@role='listbox'] | //ul[contains(@class,'MuiAutocomplete') or contains(@class,'autocomplete')] | //div[contains(@class,'MuiAutocomplete')]")
                    options = []
                    for c in containers:
                        try:
                            options.extend([o for o in c.find_elements(By.XPATH, ".//*[@role='option'] | .//li")])
                        except Exception:
                            continue
                    if not options:
                        options = self.driver.find_elements(By.XPATH, "//*[@role='option'] | //li[contains(@class,'MuiAutocomplete-option')]")
                    for opt in options:
                        try:
                            if opt.is_displayed() and opt.is_enabled():
                                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", opt)
                                self.driver.execute_script("arguments[0].click();", opt)
                                return True
                        except Exception:
                            continue
                except Exception:
                    pass
                return False

            # 1) Player 2: type first name directly into Player 2 input
            first_name = names[0]
            p2 = find_player_input_by_label("Player 2")
            if p2 is None:
                # fallback: choose next empty input after first visible input
                inputs = list_inputs()
                start_idx = 1 if (inputs and (inputs[0].get_attribute('value') or '').strip()) else 0
                p2 = inputs[start_idx] if len(inputs) > start_idx else None
            if p2 is not None:
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", p2)
                except Exception:
                    pass
                try:
                    p2.clear()
                except Exception:
                    pass
                p2.send_keys(first_name)
                # Attempt to choose from dropdown first; fallback to Enter
                if not _pick_from_dropdown(p2):
                    try:
                        p2.send_keys(Keys.ENTER)
                    except Exception:
                        pass
                logger.info(f"Filled Player 2: {first_name}")
                time.sleep(1.2)
            else:
                logger.warning("Could not locate Player 2 input")

            # For remaining names, click Add Player then type
            for name in names[1:]:
                # Click + Add Player
                add_btns = dialog.find_elements(By.XPATH, "//button[contains(., 'Add Player') or contains(., '+ Add Player')]")
                if add_btns:
                    self.driver.execute_script("arguments[0].click();", add_btns[0])
                    time.sleep(1.2)
                else:
                    logger.warning("'+ Add Player' button not found when needed")

                # Wait for a new empty input to appear
                try:
                    prev_count = len(list_inputs())
                    WebDriverWait(self.driver, 5).until(lambda d: len(list_inputs()) > prev_count)
                except Exception:
                    pass

                # Choose last visible input (newly added) or next empty
                inputs = list_inputs()
                target = None
                # Prefer last input if empty
                if inputs:
                    if not (inputs[-1].get_attribute('value') or '').strip():
                        target = inputs[-1]
                if target is None:
                    for el in inputs:
                        if not (el.get_attribute('value') or '').strip():
                            target = el
                            break
                if target is None and inputs:
                    target = inputs[-1]

                if target is not None:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
                    except Exception:
                        pass
                    try:
                        target.clear()
                    except Exception:
                        pass
                    target.send_keys(name)
                    # Try to select from autocomplete dropdown; fallback to Enter
                    if not _pick_from_dropdown(target):
                        try:
                            target.send_keys(Keys.ENTER)
                        except Exception:
                            pass
                    logger.info(f"Filled next Player: {name}")
                    time.sleep(1.2)
                else:
                    logger.warning(f"Could not locate input to fill player '{name}'")

            return True

        except Exception as e:
            logger.error(f"Error in _fill_additional_players_if_required: {e}")
            return False

    def _confirm_booking(self):
        """Handle the booking confirmation dialog with improved error handling and logging."""
        try:
            # First, save a debug screenshot before attempting to confirm
            self._save_debug("pre_confirmation")
            
            # Look for confirmation button with various possible selectors
            confirm_selectors = [
                "//div[@role='dialog']//button[normalize-space(.)='Book']",
                "//button[normalize-space(.)='Book']",
                "button.confirm-booking, button[type='submit'], button.primary, button.success",
                "//button[contains(., 'Confirm') or contains(., 'Book Now') or contains(., 'Submit') or contains(., 'Complete Booking')]",
                "//a[contains(., 'Confirm') or contains(., 'Book Now') or contains(., 'Submit') or contains(., 'Complete Booking')]",
            ]

            confirm_button = None
            for selector in confirm_selectors:
                try:
                    if selector.strip().startswith("//"):
                        elements = self.driver.find_elements(By.XPATH, selector)
                    else:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)

                    for elem in elements:
                        try:
                            if elem.is_displayed() and elem.is_enabled():
                                confirm_button = elem
                                logger.debug(f"Found confirm button with text: {elem.text}")
                                break
                        except Exception:
                            continue

                    if confirm_button:
                        break
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")

            if not confirm_button:
                raise Exception("Could not find confirmation button")

            # Scroll to the button and click it
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", confirm_button)
            time.sleep(0.5)  # Small delay for any animations
            
            # Try different click methods if the first one fails
            try:
                confirm_button.click()
            except:
                try:
                    self.driver.execute_script("arguments[0].click();", confirm_button)
                except Exception as e:
                    logger.error(f"Failed to click confirm button: {e}")
                    raise
            
            logger.info("Clicked confirm button, waiting for booking to complete...")
            # User-requested verification: wait 2 seconds, then check if Book button still exists
            time.sleep(2)

            try:
                dialog_container = None
                try:
                    dialog_container = self.driver.find_element(By.XPATH, "//div[@role='dialog' or contains(@class,'Dialog') or contains(@class,'booking-dialog')]")
                except Exception:
                    dialog_container = None

                # Reuse the same selectors to look for a visible Book button
                still_present = False
                for selector in confirm_selectors:
                    try:
                        elems = []
                        if selector.strip().startswith("//"):
                            elems = (dialog_container or self.driver).find_elements(By.XPATH, selector)
                        else:
                            elems = (dialog_container or self.driver).find_elements(By.CSS_SELECTOR, selector)
                        for e in elems:
                            if e.is_displayed() and e.is_enabled():
                                still_present = True
                                break
                        if still_present:
                            break
                    except Exception:
                        continue

                if not still_present:
                    logger.info("Book button no longer present after 2s; assuming booking success.")
                    self._terminal_outcome = 'success'
                    self._terminal_message = 'Booking completed (Book button disappeared)'
                    self._save_debug("booking_confirmed")
                    return True

                # If still present, attempt to read any alert message and end
                try:
                    alerts = self.driver.find_elements(By.CSS_SELECTOR, ".MuiAlert-message, [role='alert'] .MuiAlert-message, .MuiAlert-root .MuiAlert-message")
                    for a in alerts:
                        try:
                            if a.is_displayed():
                                msg = a.text.strip()
                                if msg:
                                    logger.error(f"Booking alert: {msg}")
                                    self._terminal_outcome = 'alert'
                                    self._terminal_message = msg
                                    self._save_debug("booking_alert")
                                    return False
                        except Exception:
                            continue
                except Exception:
                    pass
            except Exception:
                pass
            
            # Wait for success message or redirect
            success = False
            try:
                # Look for success indicators
                success_indicators = [
                    (By.CLASS_NAME, "booking-success"),
                    (By.CSS_SELECTOR, ".alert-success, .success-message, .confirmation-message"),
                    (By.XPATH, "//*[contains(., 'success') or contains(., 'confirmed') or contains(., 'complete')]"),
                    (By.XPATH, "//*[contains(., 'Booking Confirmation') or contains(., 'Booking Complete')]")
                ]
                
                for by, value in success_indicators:
                    try:
                        WebDriverWait(self.driver, 10).until(
                            EC.visibility_of_element_located((by, value))
                        )
                        success = True
                        logger.info("Booking confirmed successfully!")
                        break
                    except:
                        continue
                
                # Also check for URL changes that might indicate success
                if not success and "confirmation" in self.driver.current_url.lower():
                    success = True
                    logger.info("Detected booking confirmation via URL")
                
                # Save final confirmation screenshot
                self._save_debug("booking_confirmed")
                
                if success:
                    self._terminal_outcome = 'success'
                    self._terminal_message = 'Booking confirmed via success indicator/URL'
                return success
                
            except Exception as e:
                logger.warning(f"Could not verify success message, but continuing: {e}")
                self._save_debug("post_confirm_unknown")
                return True  # Assume success if we can't verify
            
        except Exception as e:
            error_msg = f"Failed to confirm booking: {str(e)}"
            logger.error(error_msg)
            self._save_debug("confirm_failure")
            
            # Check for error messages on the page
            try:
                error_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, ".error, .alert-error, .error-message, .validation-error"
                )
                for elem in error_elements:
                    if elem.is_displayed():
                        logger.error(f"Page error: {elem.text.strip()}")
            except:
                pass
                
            return False

    def _save_debug(self, prefix: str):
        """Save page HTML and screenshot to debug folder with timestamp for troubleshooting."""
        try:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            html_path = os.path.join(self.debug_dir, f"{prefix}_{ts}.html")
            png_path = os.path.join(self.debug_dir, f"{prefix}_{ts}.png")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            try:
                self.driver.save_screenshot(png_path)
            except Exception:
                pass
            logger.info(f"Saved debug artifacts: {html_path} and {png_path}")
        except Exception as e:
            logger.debug(f"Failed to save debug artifacts: {e}")
    
    def run(self):
        """Run the booking process."""
        try:
            if not self.login():
                return False
                
            if not self.navigate_to_booking_page():
                return False
                
            if not self.select_preferred_date():
                return False
                
            return self.find_and_book_court()
            
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            return False
        finally:
            # Keep the browser open for debugging
            # self.driver.quit()
            pass

def main():
    booking = TennisCourtBooking()
    if booking.run():
        logger.info("Tennis court booking completed successfully!")
        send_booking_notification(True, "Booking successfully")
    else:
        logger.error("Failed to complete the booking process.")
        send_booking_notification(False, "Booking failed")

if __name__ == "__main__":
    main()