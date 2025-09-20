import unittest
import os
import sys
import logging
from dotenv import load_dotenv
import boto3

# Add src directory to path for importing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Import the module to test
import notifications
from notifications import SNSNotifier, send_booking_notification, send_sms_notification

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def test_sms():
    """Test sending an SMS using the actual AWS credentials from .env file"""
    # Load environment variables from .env
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', '.env'))
    logger.info(f"Loading environment from: {env_path}")
    load_dotenv(env_path)
    
    # Verify AWS credentials are loaded
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION')
    phone = os.getenv('SMS_PHONE_NUMBER')
    enabled = os.getenv('ENABLE_SMS_NOTIFICATIONS') == 'true'
    
    if not all([access_key, secret_key, region, phone, enabled]):
        logger.error("Missing required environment variables for SMS testing")
        logger.info(f"AWS_ACCESS_KEY_ID: {'Set' if access_key else 'Missing'}")
        logger.info(f"AWS_SECRET_ACCESS_KEY: {'Set' if secret_key else 'Missing'}")
        logger.info(f"AWS_REGION: {region or 'Missing'}")
        logger.info(f"SMS_PHONE_NUMBER: {phone or 'Missing'}")
        logger.info(f"ENABLE_SMS_NOTIFICATIONS: {'Enabled' if enabled else 'Disabled'}")
        return False
    
    logger.info("All required environment variables are set")
    logger.info(f"Phone number for testing: {phone}")
    
    # First test: Direct AWS SNS client test
    try:
        logger.info("Test 1: Testing direct AWS SNS client...")
        client = boto3.client(
            'sns',
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        
        response = client.publish(
            PhoneNumber=phone,
            Message="This is a test SMS from the tennis booking AWS SNS direct test",
            Subject="Tennis SMS Test 1"
        )
        
        message_id = response.get('MessageId')
        logger.info(f"Direct AWS SNS test succeeded with MessageId: {message_id}")
    except Exception as e:
        logger.error(f"Direct AWS SNS test failed: {e}")
        return False
    
    # Second test: Using SNSNotifier class
    try:
        logger.info("Test 2: Testing SNSNotifier class...")
        notifier = SNSNotifier()
        
        if not notifier.enabled:
            logger.error("SNSNotifier is not enabled. Check environment variables.")
            return False
            
        result = notifier.send_sms(
            "This is a test SMS from the tennis booking SNSNotifier class",
            "Tennis SMS Test 2"
        )
        
        if result:
            logger.info("SNSNotifier test succeeded")
        else:
            logger.error("SNSNotifier test failed")
            return False
    except Exception as e:
        logger.error(f"SNSNotifier test failed with exception: {e}")
        return False
    
    # Important: Reinitialize the global notifier used by the helper functions
    # This ensures the global notifier is created after environment variables are loaded
    logger.info("Reinitializing global notifier...")
    notifications.notifier = SNSNotifier()
    
    # Third test: Using send_sms_notification helper
    try:
        logger.info("Test 3: Testing send_sms_notification helper function...")
        result = send_sms_notification(
            True,
            "This is a test SMS from the tennis booking send_sms_notification function"
        )
        
        if result:
            logger.info("send_sms_notification test succeeded")
        else:
            logger.error("send_sms_notification test failed")
            return False
    except Exception as e:
        logger.error(f"send_sms_notification test failed with exception: {e}")
        return False
    
    # All tests passed
    logger.info("All SMS tests completed successfully!")
    return True

if __name__ == "__main__":
    success = test_sms()
    if success:
        print("\n✅ SMS TEST SUCCESSFUL - Check your phone for three test messages")
    else:
        print("\n❌ SMS TEST FAILED - See logs above for details")
    # Exit with appropriate status code
    sys.exit(0 if success else 1)