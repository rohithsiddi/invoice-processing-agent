"""
Configuration loader for Invoice Processing Agent
"""
import os
import yaml
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()


class Config:
    """Application configuration"""
    
    # API Keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    GOOGLE_VISION_API_KEY = os.getenv('GOOGLE_VISION_API_KEY')
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./invoices.db')
    
    # ERP
    ERP_SYSTEM = os.getenv('ERP_SYSTEM', 'mock_erp')
    ERP_API_URL = os.getenv('ERP_API_URL', 'http://localhost:8001')
    ERP_API_KEY = os.getenv('ERP_API_KEY')
    
    # Email/Notifications
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@invoiceprocessing.com')
    SENDGRID_FROM_NAME = os.getenv('SENDGRID_FROM_NAME', 'Invoice Processing System')
    SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
    
    # Matching Configuration
    MATCH_THRESHOLD = float(os.getenv('MATCH_THRESHOLD', '0.85'))
    TOLERANCE_PERCENTAGE = float(os.getenv('TOLERANCE_PERCENTAGE', '5.0'))
    AUTO_APPROVE_THRESHOLD = float(os.getenv('AUTO_APPROVE_THRESHOLD', '1000.00'))
    
    # Human Review
    REVIEW_UI_URL = os.getenv('REVIEW_UI_URL', 'http://localhost:8000/review')
    HUMAN_REVIEW_API_URL = os.getenv('HUMAN_REVIEW_API_URL', 'http://localhost:8000')
    REVIEWER_EMAILS = os.getenv('REVIEWER_EMAILS', 'ap-manager@company.com').split(',')
    
    # Application Settings
    APP_HOST = os.getenv('APP_HOST', '0.0.0.0')
    APP_PORT = int(os.getenv('APP_PORT', '8000'))
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
    
    # Checkpoint Storage
    CHECKPOINT_DB_PATH = os.getenv('CHECKPOINT_DB_PATH', './checkpoints/checkpoints.db')
    
    @classmethod
    def load_tools_config(cls):
        """Load tools configuration from YAML"""
        config_path = Path(__file__).parent / 'tools.yaml'
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        return {}


# Create singleton instance
config = Config()
