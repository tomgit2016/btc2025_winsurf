import os
import boto3
import logging
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class SNSNotifier:
    def __init__(self):
        load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'config', '.env'))
        self.aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
        self.aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        self.aws_region = os.getenv('AWS_REGION', 'us-west-2')
        self.phone_number = os.getenv('SMS_PHONE_NUMBER')
        self.enabled = all([
            os.getenv('ENABLE_SMS_NOTIFICATIONS', 'true').lower() == 'true',
            self.aws_access_key_id,
            self.aws_secret_access_key,
            self.phone_number
        ])
        
        if not self.enabled:
            logger.warning("SMS notifications disabled - missing required environment variables")
            logger.info(f"AWS_ACCESS_KEY_ID: {'SET' if self.aws_access_key_id else 'NOT SET'}")
            logger.info(f"AWS_SECRET_ACCESS_KEY: {'SET' if self.aws_secret_access_key else 'NOT SET'}")
            logger.info(f"AWS_REGION: {self.aws_region}")
            logger.info(f"SMS_PHONE_NUMBER: {'SET' if self.phone_number else 'NOT SET'}")
            logger.info(f"ENABLE_SMS_NOTIFICATIONS: {os.getenv('ENABLE_SMS_NOTIFICATIONS', 'true')}")
            return
            
        try:
            self.client = boto3.client(
                'sns',
                region_name=self.aws_region,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key
            )
            logger.info("SMS notifier initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SNS client: {e}")
            self.enabled = False
    
    def send_sms(self, message: str, subject: str = "Tennis Booking Update") -> bool:
        """Send an SMS notification"""
        if not self.enabled:
            logger.warning("SMS notifications are disabled")
            return False
            
        try:
            logger.info(f"Attempting to send SMS to {self.phone_number}")
            response = self.client.publish(
                PhoneNumber=self.phone_number,
                Message=message,
                Subject=subject[:100],  # SNS subject is limited to 100 chars
                MessageAttributes={
                    'AWS.SNS.SMS.SenderID': {
                        'DataType': 'String',
                        'StringValue': 'TennisBot'
                    },
                    'AWS.SNS.SMS.SMSType': {
                        'DataType': 'String',
                        'StringValue': 'Transactional'  # Or 'Promotional' for non-critical messages
                    }
                }
            )
            logger.info(f"SMS sent successfully: {response['MessageId']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            logger.error(f"Error type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

# Global instance
notifier = SNSNotifier()

def send_booking_notification(success: bool, message: str):
    """Helper function to send booking notification"""
    if not notifier.enabled:
        logger.warning("SMS notifications are disabled, not sending notification")
        return False
        
    status = "✅ SUCCESS" if success else "❌ FAILED"
    sms_message = f"Tennis Booking {status}\n{message}"
    
    return notifier.send_sms(
        message=sms_message,
        subject=f"Tennis Booking {status}"
    )

def send_sms_notification(success: bool, message: str):
    """Alias for send_booking_notification for backwards compatibility"""
    logger.info(f"Sending SMS notification: success={success}, message={message}")
    return send_booking_notification(success, message)
