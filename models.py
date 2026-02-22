from extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def password(self):
        """Prevent password from being accessed"""
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        """Set password to a hashed value"""
        self.password_hash = generate_password_hash(password)
    
    def set_password(self, password):
        """Convenience method to set password"""
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        """Check if password matches"""
        return check_password_hash(self.password_hash, password)
    
    def check_password(self, password):
        """Alias for verify_password (for compatibility)"""
        return self.verify_password(password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    live_link = db.Column(db.String(500))
    github_link = db.Column(db.String(500))
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with sections
    sections = db.relationship('ProjectSection', backref='project', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Project {self.title}>'


class ProjectSection(db.Model):
    __tablename__ = 'project_sections'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    section_title = db.Column(db.String(200), nullable=False)
    order_position = db.Column(db.Integer, default=0)
    
    # Single part content
    content = db.Column(db.Text)
    image = db.Column(db.String(500))  # Single image
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ProjectSection {self.section_title}>'


class NewsletterSubscriber(db.Model):
    __tablename__ = 'newsletter_subscribers'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    unsubscribe_token = db.Column(db.String(100), unique=True, nullable=True)
    
    def __repr__(self):
        return f'<Subscriber {self.email}>'