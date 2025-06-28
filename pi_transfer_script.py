import os
import time
import logging
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import json
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pi_transfer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class PiNetworkTransferBot:

    def __init__(self):
        """Initialize the Pi Network transfer bot with configuration validation."""
        self.TRANSFER_AMOUNT = 1650.0  # Pi to transfer
        self.TRANSACTION_FEE = 0.01    # Estimated transaction fee
        self.REQUIRED_BALANCE = self.TRANSFER_AMOUNT + self.TRANSACTION_FEE
        
        # Target execution time: July 20, 2025, at 3:38:09 PM UTC
        self.TARGET_DATETIME = datetime(2025, 7, 20, 15, 38, 9, tzinfo=timezone.utc)
        
        # Load configuration from environment variables
        # For testing only - replace with actual values temporarily
        self.access_token = os.getenv('PI_ACCESS_TOKEN', 'test_access_token_here')
        self.allowed_recipient = os.getenv('ALLOWED_RECIPIENT_ADDRESS', 'test_wallet_address_here')
        self.app_id = os.getenv('PI_APP_ID', 'test_app_id_here')
        self.app_secret = os.getenv('PI_APP_SECRET', 'test_app_secret_here')
        
        # Pi Platform API configuration
        self.pi_api_base_url = os.getenv('PI_API_BASE_URL', 'https://api.minepi.com')
        self.sandbox_mode = os.getenv('PI_SANDBOX_MODE', 'false').lower() == 'true'
        
        if self.sandbox_mode:
            self.pi_api_base_url = 'https://api.sandbox.minepi.com'
            logger.info("Running in sandbox mode")
        
        # Validate configuration
        self._validate_configuration()
        
        # Store wallet address after authentication
        self.wallet_address = None
        self.user_uid = None
        
        logger.info(f"Pi Transfer Bot initialized")
        logger.info(f"Target transfer time: {self.TARGET_DATETIME}")
        logger.info(f"Allowed recipient: {self.allowed_recipient}")
        logger.info(f"Sandbox mode: {self.sandbox_mode}")

    def _validate_configuration(self) -> None:
        """Validate all required configuration parameters."""
        if not self.access_token:
            raise ValueError("PI_ACCESS_TOKEN environment variable is required")
        
        if not self.allowed_recipient:
            raise ValueError("ALLOWED_RECIPIENT_ADDRESS environment variable is required")
        
        if not self.app_id:
            raise ValueError("PI_APP_ID environment variable is required")
        
        if not self.app_secret:
            raise ValueError("PI_APP_SECRET environment variable is required")
        
        # Validate recipient address format (Pi wallet address)
        if not self.allowed_recipient or len(self.allowed_recipient) < 20:
            raise ValueError("Invalid recipient address format. Must be a valid Pi wallet address")
        
        logger.info("Configuration validation passed")

    def _validate_recipient_address(self, recipient: str) -> bool:
        """Validate that the recipient address matches the allowed address."""
        if recipient != self.allowed_recipient:
            error_msg = f"Transfer denied: Recipient {recipient} is not the allowed address {self.allowed_recipient}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        return True

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get authenticated user information using Platform API."""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.pi_api_base_url}/v2/me",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                user_data = response.json()
                logger.info(f"User authenticated: {user_data.get('username', 'N/A')}")
                
                # Store user information
                self.user_uid = user_data.get('uid')
                self.wallet_address = user_data.get('wallet_address')
                
                return user_data
            else:
                logger.error(f"Failed to get user info: HTTP {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error fetching user info: {e}")
            return None

    def get_wallet_balance(self) -> Optional[Dict[str, Any]]:
        """Get the current wallet balance using Platform API."""
        if not self.wallet_address:
            logger.error("Wallet address not available. Please authenticate first.")
            return None
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Use Platform API to get wallet balance
            response = requests.get(
                f"{self.pi_api_base_url}/v2/wallets/{self.wallet_address}/balance",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                balance_data = response.json()
                logger.info(f"Balance retrieved: {balance_data}")
                return balance_data
            else:
                logger.error(f"Failed to get balance: HTTP {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error fetching balance: {e}")
            return None

    def get_available_balance(self) -> float:
        """Get the available (unlocked) Pi balance."""
        balance_data = self.get_wallet_balance()
        if balance_data:
            # Pi Network balance structure
            available = balance_data.get('available', 0)
            return float(available)
        return 0.0

    def get_pending_payments(self) -> Optional[List[Dict[str, Any]]]:
        """Get pending payments for the user."""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.pi_api_base_url}/v2/payments",
                headers=headers,
                params={'status': 'pending'},
                timeout=30
            )
            
            if response.status_code == 200:
                payments_data = response.json()
                return payments_data.get('payments', [])
            else:
                logger.error(f"Failed to get pending payments: HTTP {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error fetching pending payments: {e}")
            return None

    def confirm_unlock(self) -> bool:
        """Attempt to confirm unlock of locked Pi tokens via pending payments."""
        try:
            pending_payments = self.get_pending_payments()
            
            if not pending_payments:
                return True  # No pending payments to confirm
            
            # Process any incomplete payments that might be related to unlocking
            for payment in pending_payments:
                if not payment.get('status', {}).get('developer_completed', True):
                    payment_id = payment.get('identifier')
                    
                    # Complete the payment if it's related to unlocking
                    if self._complete_payment(payment_id):
                        logger.info(f"Completed pending payment: {payment_id}")
                    else:
                        logger.warning(f"Failed to complete pending payment: {payment_id}")
            
            return True
                
        except Exception as e:
            logger.warning(f"Error confirming unlock: {e}")
            return False

    def _complete_payment(self, payment_id: str) -> bool:
        """Complete a payment using Platform API."""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                f"{self.pi_api_base_url}/v2/payments/{payment_id}/complete",
                headers=headers,
                timeout=30
            )
            
            return response.status_code == 200
            
        except requests.RequestException as e:
            logger.error(f"Error completing payment {payment_id}: {e}")
            return False

    def create_payment(self, recipient: str, amount: float, memo: str) -> Optional[str]:
        """Create a new payment using Platform API."""
        try:
            # Validate recipient address
            self._validate_recipient_address(recipient)
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            payment_data = {
                'payment': {
                    'amount': amount,
                    'memo': memo,
                    'metadata': {
                        'transfer_type': 'automated_transfer',
                        'scheduled_time': self.TARGET_DATETIME.isoformat(),
                        'recipient': recipient
                    },
                    'uid': self.user_uid
                }
            }
            
            response = requests.post(
                f"{self.pi_api_base_url}/v2/payments",
                headers=headers,
                json=payment_data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                payment_response = response.json()
                payment_id = payment_response.get('identifier')
                logger.info(f"Payment created successfully: {payment_id}")
                return payment_id
            else:
                logger.error(f"Failed to create payment: HTTP {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return None

    def approve_payment(self, payment_id: str) -> bool:
        """Approve a payment using Platform API."""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                f"{self.pi_api_base_url}/v2/payments/{payment_id}/approve",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Payment approved: {payment_id}")
                return True
            else:
                logger.error(f"Failed to approve payment: HTTP {response.status_code}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"Error approving payment {payment_id}: {e}")
            return False

    def complete_payment(self, payment_id: str, txid: str = None) -> bool:
        """Complete a payment using Platform API."""
        return self._complete_payment(payment_id)

    def execute_transfer(self, recipient: str, amount: float) -> bool:
        """Execute the Pi transfer using Platform API payment flow."""
        try:
            logger.info(f"Initiating transfer of {amount} Pi to {recipient}")
            
            # Step 1: Create payment
            memo = f"Automated transfer of {amount} Pi - Scheduled for {self.TARGET_DATETIME}"
            payment_id = self.create_payment(recipient, amount, memo)
            
            if not payment_id:
                logger.error("Failed to create payment")
                return False
            
            # Step 2: Approve payment (server-side approval)
            if not self.approve_payment(payment_id):
                logger.error("Failed to approve payment")
                return False
            
            # Step 3: Monitor payment status and complete when ready
            max_attempts = 60  # Monitor for up to 10 minutes
            attempt = 0
            
            while attempt < max_attempts:
                payment_status = self.get_payment_status(payment_id)
                
                if payment_status:
                    status = payment_status.get('status', {})
                    
                    if status.get('transaction_verified') and not status.get('developer_completed'):
                        # Transaction is verified, complete the payment
                        txid = payment_status.get('transaction', {}).get('txid')
                        if self.complete_payment(payment_id, txid):
                            logger.info(f"Transfer completed successfully! Payment ID: {payment_id}")
                            return True
                    
                    if status.get('cancelled') or status.get('user_cancelled'):
                        logger.error(f"Payment was cancelled: {payment_id}")
                        return False
                
                attempt += 1
                time.sleep(10)  # Wait 10 seconds before checking again
            
            logger.error(f"Payment completion timeout for payment: {payment_id}")
            return False
                
        except Exception as e:
            logger.error(f"Unexpected error during transfer: {e}")
            return False

    def get_payment_status(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Get payment status using Platform API."""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.pi_api_base_url}/v2/payments/{payment_id}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get payment status: HTTP {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error getting payment status: {e}")
            return None

    def check_and_transfer(self) -> bool:
        """Check balance and execute transfer if conditions are met."""
        try:
            # First, ensure user is authenticated
            if not self.wallet_address:
                user_info = self.get_user_info()
                if not user_info:
                    logger.error("Failed to authenticate user")
                    return False
            
            # Attempt to confirm any pending unlocks
            self.confirm_unlock()
            
            # Check available balance
            available_balance = self.get_available_balance()
            logger.info(f"Current available balance: {available_balance} Pi")
            
            if available_balance >= self.REQUIRED_BALANCE:
                logger.info(f"Sufficient balance available. Executing transfer...")
                
                success = self.execute_transfer(self.allowed_recipient, self.TRANSFER_AMOUNT)
                
                if success:
                    logger.info("Transfer completed successfully!")
                    return True
                else:
                    logger.error("Transfer failed")
                    return False
            else:
                needed = self.REQUIRED_BALANCE - available_balance
                logger.info(f"Insufficient balance. Need {needed:.6f} more Pi")
                return False
                
        except Exception as e:
            logger.error(f"Error in check_and_transfer: {e}")
            return False

    def is_target_time_reached(self) -> bool:
        """Check if the target execution time has been reached."""
        current_time = datetime.now(timezone.utc)
        return current_time >= self.TARGET_DATETIME

    def run_monitoring_loop(self) -> None:
        """Main monitoring loop that runs until successful transfer or target time."""
        logger.info("Starting balance monitoring loop...")
        
        # Initial authentication
        if not self.get_user_info():
            logger.error("Failed to authenticate. Exiting...")
            return
        
        while True:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Check if target time has passed
                if self.is_target_time_reached():
                    logger.info("Target time reached. Attempting final transfer...")
                    
                    if self.check_and_transfer():
                        logger.info("Final transfer successful. Exiting...")
                        break
                    else:
                        logger.error("Final transfer failed at target time")
                        break
                
                # Regular balance check
                if self.check_and_transfer():
                    logger.info("Transfer successful before target time. Exiting...")
                    break
                
                # Calculate time until target
                time_until_target = (self.TARGET_DATETIME - current_time).total_seconds()
                
                if time_until_target > 300:  # More than 5 minutes until target
                    # Wait 5 minutes before next check
                    logger.info("Waiting 5 minutes before next balance check...")
                    time.sleep(300)
                else:
                    # Close to target time, check more frequently
                    logger.info("Close to target time. Checking every minute...")
                    time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying on error

    def run_scheduled_check(self) -> None:
        """Run a single scheduled check (for use with external schedulers)."""
        logger.info("Running scheduled balance check...")
        
        if self.is_target_time_reached():
            logger.info("Target time reached or passed")
            
        self.check_and_transfer()

def main():
    """Main function to run the Pi Network transfer bot."""
    try:
        # Initialize the transfer bot
        bot = PiNetworkTransferBot()
        
        # Log initial status
        logger.info("Pi Network Automated Transfer Bot Started")
        logger.info(f"Transfer amount: {bot.TRANSFER_AMOUNT} Pi")
        logger.info(f"Target time: {bot.TARGET_DATETIME}")
        logger.info(f"Allowed recipient: {bot.allowed_recipient}")
        
        # Run the monitoring loop
        bot.run_monitoring_loop()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Ensure all required environment variables are set
    required_env_vars = [
        'PI_ACCESS_TOKEN',
        'ALLOWED_RECIPIENT_ADDRESS', 
        'PI_APP_ID',
        'PI_APP_SECRET'
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set the following environment variables:")
        print("export PI_ACCESS_TOKEN='your_access_token_from_pi_authenticate'")
        print("export ALLOWED_RECIPIENT_ADDRESS='recipient_pi_wallet_address'")
        print("export PI_APP_ID='your_pi_app_id'")
        print("export PI_APP_SECRET='your_pi_app_secret'")
        print("export PI_SANDBOX_MODE='true'  # Optional: for sandbox testing")
        print("\nNote: You need to obtain the access token by implementing Pi.authenticate() in a web application first.")
        exit(1)
    
    main()