from flask import Flask
from flask_migrate import Migrate
from datetime import datetime
import os
import logging

# Import extensions from extensions.py (NOT re-initializing them)
from extensions import db, login_manager, admin, mail

def create_app(config_object=None):
    """Application factory function"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object('config.Config')
    
    if config_object:
        app.config.from_object(config_object)
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    
    # Initialize migrate separately
    migrate = Migrate()
    migrate.init_app(app, db)
    
    # Configure login
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # Import models here to avoid circular imports
    from models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    from routes import main_bp
    app.register_blueprint(main_bp)
    
    # ===== FIXED: Better database setup with schema updates =====
    with app.app_context():
        try:
            # Check if we need to update the schema
            from sqlalchemy import inspect
            
            # Get existing tables and columns
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if 'newsletter_subscribers' in existing_tables:
                # Check if unsubscribe_token column exists
                columns = [col['name'] for col in inspector.get_columns('newsletter_subscribers')]
                
                if 'unsubscribe_token' not in columns:
                    # Add the missing column
                    print("📝 Adding unsubscribe_token column to newsletter_subscribers table...")
                    db.session.execute(db.text('ALTER TABLE newsletter_subscribers ADD COLUMN unsubscribe_token VARCHAR(100) UNIQUE'))
                    db.session.commit()
                    print("✅ Column added successfully!")
            
            # Create any missing tables
            db.create_all()
            print("✓ Database tables created/verified successfully!")
            
            # Now we can safely query
            from models import User
            from werkzeug.security import generate_password_hash
            
            # Check if we need to create default admin user
            if User.query.count() == 0:
                # FIXED: Use the property setter which automatically hashes
                # Don't hash it manually here - let the model's password setter handle it
                admin_user = User(
                    username='admin',
                    password='admin123'  # Password will be hashed by the property setter
                )
                db.session.add(admin_user)
                db.session.commit()
                print("✓ Default admin user created (username: admin, password: admin123)")
                print("  ⚠️  IMPORTANT: Change this password after first login!")
                
        except Exception as e:
            print(f"⚠️  Warning during database setup: {e}")
            # If there's an error, try a more aggressive approach
            try:
                print("Attempting to recreate tables...")
                db.drop_all()
                db.create_all()
                print("✅ Tables recreated successfully!")
                
                # Recreate admin user - FIXED: Don't double-hash
                from models import User
                
                admin_user = User(
                    username='admin',
                    password='admin123'  # Let the property setter hash it
                )
                db.session.add(admin_user)
                db.session.commit()
                print("✓ Default admin user created (username: admin, password: admin123)")
            except Exception as e2:
                print(f"❌ Critical error: {e2}")
    # ===== END OF FIX =====
    
    # Setup admin interface
    # Import admin view classes
    from admin import SecureAdminIndexView, ProjectAdminView, ProjectSectionAdminView, NewsletterSubscriberAdminView, UserAdminView
    from models import Project, ProjectSection, NewsletterSubscriber, User
    
    # Configure admin with custom index view
    admin.index_view = SecureAdminIndexView(
        name='Dashboard',
        template='admin/index.html',
        url='/admin'
    )
    
    # Add views to admin
    admin.add_view(ProjectAdminView(Project, db.session, name='Projects', category='Content'))
    admin.add_view(ProjectSectionAdminView(ProjectSection, db.session, name='Sections', category='Content'))
    admin.add_view(NewsletterSubscriberAdminView(NewsletterSubscriber, db.session, name='Subscribers', category='Users'))
    admin.add_view(UserAdminView(User, db.session, name='Admin Users', category='Users'))
    
    # Initialize admin with app
    admin.init_app(app)
    # ===== END OF ADMIN SETUP =====
    
    # Add context processor to inject current datetime into all templates
    @app.context_processor
    def inject_now():
        """Inject current datetime into all templates"""
        return {'now': datetime.now()}
    
    # Ensure upload directories exist
    os.makedirs(os.path.join('static', 'uploads', 'projects'), exist_ok=True)
    
    # Setup logging
    if not app.debug:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.info('Portfolio application started')
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)