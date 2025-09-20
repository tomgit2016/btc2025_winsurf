import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import logging
from io import StringIO

# Add src directory to path for importing
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Import the module to test
import notifications
from notifications import SNSNotifier, send_booking_notification, send_sms_notification

class TestSNSNotifier(unittest.TestCase):
    """Test cases for SNSNotifier class"""
    
    def setUp(self):
        """Setup test environment before each test"""
        # Capture log output for testing
        self.log_capture = StringIO()
        self.log_handler = logging.StreamHandler(self.log_capture)
        notifications.logger.addHandler(self.log_handler)
        notifications.logger.setLevel(logging.INFO)
        
        # Reset environment variables that might affect tests
        self.env_patcher = patch.dict('os.environ', {
            'AWS_ACCESS_KEY_ID': '',
            'AWS_SECRET_ACCESS_KEY': '',
            'AWS_REGION': '',
            'SMS_PHONE_NUMBER': '',
            'ENABLE_SMS_NOTIFICATIONS': 'true'
        })
        self.env_patcher.start()
        
        # Reset the global notifier to avoid test interference
        notifications.notifier = None
    
    def tearDown(self):
        """Clean up after each test"""
        # Remove log handler
        notifications.logger.removeHandler(self.log_handler)
        
        # Stop environment patching
        self.env_patcher.stop()
        
        # Reset notifier
        notifications.notifier = SNSNotifier()
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'us-east-1',
        'SMS_PHONE_NUMBER': '+11234567890',
        'ENABLE_SMS_NOTIFICATIONS': 'true'
    })
    @patch('boto3.client')
    def test_init_with_valid_credentials(self, mock_boto_client):
        """Test initialization with valid AWS credentials"""
        # Setup mock
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        
        # Create notifier
        notifier = SNSNotifier()
        
        # Assertions
        self.assertTrue(notifier.enabled)
        self.assertEqual(notifier.aws_access_key_id, 'test_key')
        self.assertEqual(notifier.aws_secret_access_key, 'test_secret')
        self.assertEqual(notifier.aws_region, 'us-east-1')
        self.assertEqual(notifier.phone_number, '+11234567890')
        
        # Verify boto3 client was created with correct parameters
        mock_boto_client.assert_called_once_with(
            'sns',
            region_name='us-east-1',
            aws_access_key_id='test_key',
            aws_secret_access_key='test_secret'
        )
        
        # Verify log message
        self.assertIn("SMS notifier initialized", self.log_capture.getvalue())
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': '',
        'AWS_SECRET_ACCESS_KEY': '',
        'ENABLE_SMS_NOTIFICATIONS': 'true'
    })
    def test_init_with_missing_credentials(self):
        """Test initialization with missing AWS credentials"""
        notifier = SNSNotifier()
        
        # Assertions
        self.assertFalse(notifier.enabled)
        self.assertIn("SMS notifications disabled", self.log_capture.getvalue())
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'us-east-1',
        'SMS_PHONE_NUMBER': '+11234567890',
        'ENABLE_SMS_NOTIFICATIONS': 'false'
    })
    def test_init_with_notifications_disabled(self):
        """Test initialization with notifications explicitly disabled"""
        notifier = SNSNotifier()
        
        # Assertions
        self.assertFalse(notifier.enabled)
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'us-east-1',
        'SMS_PHONE_NUMBER': '+11234567890',
        'ENABLE_SMS_NOTIFICATIONS': 'true'
    })
    @patch('boto3.client')
    def test_boto3_client_exception(self, mock_boto_client):
        """Test handling of boto3 client exceptions"""
        # Setup mock to raise exception
        mock_boto_client.side_effect = Exception("Test boto3 client exception")
        
        # Create notifier
        notifier = SNSNotifier()
        
        # Assertions
        self.assertFalse(notifier.enabled)
        self.assertIn("Failed to initialize SNS client", self.log_capture.getvalue())
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'us-east-1',
        'SMS_PHONE_NUMBER': '+11234567890',
        'ENABLE_SMS_NOTIFICATIONS': 'true'
    })
    @patch('boto3.client')
    def test_send_sms_success(self, mock_boto_client):
        """Test successful SMS sending"""
        # Setup mock
        mock_client = MagicMock()
        mock_client.publish.return_value = {'MessageId': 'test-message-id'}
        mock_boto_client.return_value = mock_client
        
        # Create notifier and send SMS
        notifier = SNSNotifier()
        result = notifier.send_sms("Test message", "Test subject")
        
        # Assertions
        self.assertTrue(result)
        mock_client.publish.assert_called_once()
        call_kwargs = mock_client.publish.call_args.kwargs
        self.assertEqual(call_kwargs['PhoneNumber'], '+11234567890')
        self.assertEqual(call_kwargs['Message'], 'Test message')
        self.assertEqual(call_kwargs['Subject'], 'Test subject')
        self.assertIn("SMS sent successfully", self.log_capture.getvalue())
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'us-east-1',
        'SMS_PHONE_NUMBER': '+11234567890',
        'ENABLE_SMS_NOTIFICATIONS': 'false'
    })
    def test_send_sms_disabled(self):
        """Test SMS sending when notifications are disabled"""
        notifier = SNSNotifier()
        result = notifier.send_sms("Test message", "Test subject")
        
        # Assertions
        self.assertFalse(result)
        self.assertIn("SMS notifications are disabled", self.log_capture.getvalue())
    
    @patch.dict('os.environ', {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'us-east-1',
        'SMS_PHONE_NUMBER': '+11234567890',
        'ENABLE_SMS_NOTIFICATIONS': 'true'
    })
    @patch('boto3.client')
    def test_send_sms_failure(self, mock_boto_client):
        """Test SMS sending when boto3 publish fails"""
        # Setup mock to raise exception on publish
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception("Test publish exception")
        mock_boto_client.return_value = mock_client
        
        # Create notifier and send SMS
        notifier = SNSNotifier()
        result = notifier.send_sms("Test message", "Test subject")
        
        # Assertions
        self.assertFalse(result)
        self.assertIn("Failed to send SMS", self.log_capture.getvalue())

class TestNotificationHelpers(unittest.TestCase):
    """Test cases for notification helper functions"""
    
    def setUp(self):
        """Setup test environment before each test"""
        # Capture log output for testing
        self.log_capture = StringIO()
        self.log_handler = logging.StreamHandler(self.log_capture)
        notifications.logger.addHandler(self.log_handler)
        notifications.logger.setLevel(logging.INFO)
        
        # Create a mock notifier for testing
        self.mock_notifier = MagicMock()
        # Store original notifier to restore later
        self.original_notifier = notifications.notifier
        # Replace with our mock
        notifications.notifier = self.mock_notifier
    
    def tearDown(self):
        """Clean up after each test"""
        # Remove log handler
        notifications.logger.removeHandler(self.log_handler)
        # Restore original notifier
        notifications.notifier = self.original_notifier
    
    def test_send_booking_notification_success(self):
        """Test send_booking_notification with success status"""
        # Configure mock
        self.mock_notifier.enabled = True
        self.mock_notifier.send_sms.return_value = True
        
        # Call function
        result = send_booking_notification(True, "Booking successful")
        
        # Assertions
        self.assertTrue(result)
        self.mock_notifier.send_sms.assert_called_once()
        call_args = self.mock_notifier.send_sms.call_args.kwargs
        self.assertEqual(call_args['message'], "Tennis Booking ✅ SUCCESS\nBooking successful")
        self.assertEqual(call_args['subject'], "Tennis Booking ✅ SUCCESS")
    
    def test_send_booking_notification_failure(self):
        """Test send_booking_notification with failure status"""
        # Configure mock
        self.mock_notifier.enabled = True
        self.mock_notifier.send_sms.return_value = True
        
        # Call function
        result = send_booking_notification(False, "Booking failed")
        
        # Assertions
        self.assertTrue(result)
        self.mock_notifier.send_sms.assert_called_once()
        call_args = self.mock_notifier.send_sms.call_args.kwargs
        self.assertEqual(call_args['message'], "Tennis Booking ❌ FAILED\nBooking failed")
        self.assertEqual(call_args['subject'], "Tennis Booking ❌ FAILED")
    
    def test_send_booking_notification_disabled(self):
        """Test send_booking_notification when notifications are disabled"""
        # Configure mock
        self.mock_notifier.enabled = False
        
        # Call function
        result = send_booking_notification(True, "Booking successful")
        
        # Assertions
        self.assertFalse(result)
        self.mock_notifier.send_sms.assert_not_called()
        self.assertIn("SMS notifications are disabled", self.log_capture.getvalue())
    
    def test_send_sms_notification(self):
        """Test send_sms_notification (should call send_booking_notification)"""
        # Create a patch for send_booking_notification
        with patch('notifications.send_booking_notification') as mock_send_booking:
            mock_send_booking.return_value = True
            
            # Call function
            result = send_sms_notification(True, "Test message")
            
            # Assertions
            self.assertTrue(result)
            mock_send_booking.assert_called_once_with(True, "Test message")
            self.assertIn("Sending SMS notification", self.log_capture.getvalue())

if __name__ == '__main__':
    unittest.main()