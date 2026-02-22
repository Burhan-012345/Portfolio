from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_admin import Admin
import os

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
admin = Admin(name='Burhan Ahmed Admin')  # Removed template_mode parameter

# Login configuration
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
login_manager.login_message = 'Please log in to access this page.'