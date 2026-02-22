import os
import uuid
import secrets
import json
from flask import redirect, url_for, flash, request, render_template, jsonify
from flask_admin import AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from werkzeug.utils import secure_filename
from werkzeug.exceptions import HTTPException
from wtforms.validators import DataRequired
from extensions import db, admin
from models import Project, ProjectSection, NewsletterSubscriber, User
from email_service import send_project_notification
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SecureModelView(ModelView):
    """Base secure model view requiring authentication"""
    
    def is_accessible(self):
        return current_user.is_authenticated
    
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('main.login', next=request.url))
    
    def handle_view_exception(self, exc):
        if isinstance(exc, HTTPException) and exc.code == 404:
            return redirect(url_for('main.index'))
        return super().handle_view_exception(exc)

class SecureAdminIndexView(AdminIndexView):
    """Secure admin index view"""
    
    @expose('/')
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for('main.login'))
        
        # Get statistics for dashboard
        total_projects = Project.query.count()
        featured_projects = Project.query.filter_by(is_featured=True).count()
        total_subscribers = NewsletterSubscriber.query.filter_by(is_active=True).count()
        total_sections = ProjectSection.query.count()
        
        # Get recent projects with their sections
        recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()
        
        # Calculate image count
        images_count = 0
        for project in recent_projects:
            for section in project.sections:
                if section.image:
                    images_count += 1
        
        return self.render('admin/index.html',
                         total_projects=total_projects,
                         featured_projects=featured_projects,
                         total_subscribers=total_subscribers,
                         total_sections=total_sections,
                         projects=recent_projects,
                         images_count=images_count,
                         now=datetime.now())

class ProjectAdminView(SecureModelView):
    """Admin view for projects"""
    
    # Explicitly enable all actions
    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    
    # Custom templates
    create_template = 'admin/project/create.html'
    edit_template = 'admin/project/edit.html'
    
    # List configuration
    column_list = ['id', 'title', 'is_featured', 'sections_count', 'created_at']
    column_searchable_list = ['title', 'description']
    column_filters = ['is_featured', 'created_at']
    column_editable_list = ['title', 'is_featured']
    column_default_sort = ('created_at', True)  # Descending order
    
    # Form configuration
    form_columns = ['title', 'description', 'live_link', 'github_link', 'is_featured']
    
    # Column formatting
    column_formatters = {
        'is_featured': lambda v, c, m, p: '✅' if m.is_featured else '❌',
        'created_at': lambda v, c, m, p: m.created_at.strftime('%Y-%m-%d %H:%M') if m.created_at else '',
        'sections_count': lambda v, c, m, p: len(m.sections)
    }
    
    column_labels = {
        'sections_count': 'Sections'
    }
    
    # Action buttons in list view
    column_display_actions = True
    action_disallowed_list = []  # Allow all actions
    
    def create_model(self, form):
        """Create new project with sections"""
        try:
            # Create the project first
            project = Project(
                title=form.title.data,
                description=form.description.data,
                live_link=form.live_link.data,
                github_link=form.github_link.data,
                is_featured=form.is_featured.data
            )
            db.session.add(project)
            db.session.flush()  # Get project ID
            
            # Process sections from form data
            self._process_sections(project, request.form, request.files)
            
            db.session.commit()
            
            # Send notification if featured
            if project.is_featured:
                try:
                    send_project_notification(project)
                    flash(f'✨ Project "{project.title}" marked as featured. Notification emails are being sent to subscribers.', 'success')
                except Exception as e:
                    flash(f'⚠️ Error sending notifications: {str(e)}', 'error')
                    logger.error(f"Failed to send notifications for project {project.id}: {str(e)}")
            
            flash(f'✅ Project "{project.title}" created successfully!', 'success')
            return project
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating project: {str(e)}', 'error')
            logger.error(f"Error creating project: {str(e)}")
            return False
    
    def update_model(self, form, model):
        """Update existing project with sections"""
        try:
            # Update project details
            model.title = form.title.data
            model.description = form.description.data
            model.live_link = form.live_link.data
            model.github_link = form.github_link.data
            model.is_featured = form.is_featured.data
            
            # Process sections from form data
            self._process_sections(model, request.form, request.files)
            
            db.session.commit()
            
            # Send notification if featured (and it wasn't featured before)
            if model.is_featured:
                try:
                    send_project_notification(model)
                    flash(f'✨ Project "{model.title}" marked as featured. Notification emails are being sent to subscribers.', 'success')
                except Exception as e:
                    flash(f'⚠️ Error sending notifications: {str(e)}', 'error')
                    logger.error(f"Failed to send notifications for project {model.id}: {str(e)}")
            
            flash(f'✅ Project "{model.title}" updated successfully!', 'success')
            return model
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating project: {str(e)}', 'error')
            logger.error(f"Error updating project: {str(e)}")
            return False
    
    def _process_sections(self, project, form_data, files):
        """Process section data from form (single part per section)"""
        # Get section data from form
        section_titles = form_data.getlist('section_title[]')
        section_contents = form_data.getlist('section_content[]')
        section_ids = form_data.getlist('section_id[]')
        section_orders = form_data.getlist('section_order[]')
        
        # Keep track of processed section IDs
        processed_ids = []
        
        for i in range(len(section_titles)):
            title = section_titles[i] if i < len(section_titles) else ''
            content = section_contents[i] if i < len(section_contents) else ''
            section_id = section_ids[i] if i < len(section_ids) else None
            order = int(section_orders[i]) if i < len(section_orders) else i
            
            # Handle image upload
            image = self._handle_section_image(files.get(f'section_image_{i}'))
            
            if section_id and section_id != 'new':
                # Update existing section
                section = ProjectSection.query.get(int(section_id))
                if section and section.project_id == project.id:
                    section.section_title = title
                    section.order_position = order
                    section.content = content
                    if image:
                        # Delete old image if exists
                        if section.image:
                            self._delete_image(section.image)
                        section.image = image
                    processed_ids.append(section.id)
            else:
                # Create new section
                section = ProjectSection(
                    project_id=project.id,
                    section_title=title,
                    order_position=order,
                    content=content,
                    image=image
                )
                db.session.add(section)
                db.session.flush()
                processed_ids.append(section.id)
        
        # Delete sections that were removed
        for section in project.sections:
            if section.id not in processed_ids:
                # Delete associated image
                if section.image:
                    self._delete_image(section.image)
                db.session.delete(section)
    
    def _handle_section_image(self, uploaded_file):
        """Handle individual section image upload"""
        if uploaded_file and uploaded_file.filename:
            try:
                # Validate file type
                filename = uploaded_file.filename.lower()
                if not any(filename.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']):
                    raise ValueError('Invalid file type. Allowed: png, jpg, jpeg, webp, gif')
                
                # Validate file size (5MB)
                uploaded_file.seek(0, os.SEEK_END)
                file_size = uploaded_file.tell()
                uploaded_file.seek(0)
                if file_size > 5 * 1024 * 1024:
                    raise ValueError('File size must be less than 5MB')
                
                # Secure filename and add UUID
                original_filename = secure_filename(uploaded_file.filename)
                ext = original_filename.rsplit('.', 1)[1].lower()
                new_filename = f"{uuid.uuid4().hex}.{ext}"
                
                # Save file
                upload_folder = os.path.join('static', 'uploads', 'projects')
                os.makedirs(upload_folder, exist_ok=True)
                filepath = os.path.join(upload_folder, new_filename)
                uploaded_file.save(filepath)
                
                logger.info(f"Image uploaded: {new_filename}")
                return f"uploads/projects/{new_filename}"
            except Exception as e:
                logger.error(f"Image upload error: {str(e)}")
                flash(f'Error uploading image: {str(e)}', 'error')
        
        return None
    
    def _delete_image(self, image_path):
        """Delete image file"""
        if image_path:
            try:
                full_path = os.path.join('static', image_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info(f"Deleted image: {image_path}")
            except Exception as e:
                logger.error(f"Error deleting image {image_path}: {str(e)}")
    
    def after_model_delete(self, model):
        """Delete associated images when project is deleted"""
        for section in model.sections:
            if section.image:
                self._delete_image(section.image)

class ProjectSectionAdminView(SecureModelView):
    """Admin view for project sections (single part)"""
    
    can_create = True
    can_edit = True
    can_delete = True
    
    column_list = ['id', 'section_title', 'project', 'order_position', 'has_image']
    column_searchable_list = ['section_title', 'content']
    column_filters = ['project', 'order_position']
    column_editable_list = ['section_title', 'order_position']
    
    form_columns = ['project', 'section_title', 'order_position', 'content', 'image']
    
    column_formatters = {
        'image': lambda v, c, m, p: '✅' if m.image else '❌',
        'project': lambda v, c, m, p: m.project.title if m.project else 'No Project',
        'has_image': lambda v, c, m, p: '✅' if m.image else '❌'
    }
    
    column_labels = {
        'has_image': 'Has Image'
    }
    
    # Form widget overrides
    form_ajax_refs = {
        'project': {
            'fields': ['title'],
            'page_size': 10
        }
    }
    
    # Customize form to handle image upload properly
    form_widget_args = {
        'image': {
            'type': 'file',
            'accept': 'image/*'
        }
    }
    
    def on_model_change(self, form, model, is_created):
        """Handle image uploads"""
        try:
            # Handle image - check if a file was uploaded
            if hasattr(form, 'image') and form.image.data:
                # Check if it's a file upload or just a string path
                if hasattr(form.image.data, 'filename') and form.image.data.filename:
                    image = self._handle_image_upload(form.image.data)
                    if image:
                        # Delete old image if exists
                        if model.image:
                            self._delete_image(model.image)
                        model.image = image
                
        except Exception as e:
            flash(f'Error uploading image: {str(e)}', 'error')
            logger.error(f"Image upload error: {str(e)}")
    
    def _handle_image_upload(self, uploaded_file):
        """Handle image upload for sections"""
        if uploaded_file and hasattr(uploaded_file, 'filename') and uploaded_file.filename:
            # Validate file type
            filename = uploaded_file.filename.lower()
            if not any(filename.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']):
                raise ValueError('Invalid file type. Allowed: png, jpg, jpeg, webg, gif')
            
            # Validate file size (5MB)
            uploaded_file.seek(0, os.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)
            if file_size > 5 * 1024 * 1024:
                raise ValueError('File size must be less than 5MB')
            
            # Secure filename and add UUID
            original_filename = secure_filename(uploaded_file.filename)
            ext = original_filename.rsplit('.', 1)[1].lower()
            new_filename = f"{uuid.uuid4().hex}.{ext}"
            
            # Save file
            upload_folder = os.path.join('static', 'uploads', 'projects')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, new_filename)
            uploaded_file.save(filepath)
            
            return f"uploads/projects/{new_filename}"
        
        return None
    
    def _delete_image(self, image_path):
        """Delete image file"""
        if image_path:
            try:
                full_path = os.path.join('static', image_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception as e:
                logger.error(f"Error deleting image {image_path}: {str(e)}")

class NewsletterSubscriberAdminView(SecureModelView):
    """Admin view for newsletter subscribers"""
    
    can_create = True
    can_edit = True
    can_delete = True
    
    column_list = ['id', 'email', 'subscribed_at', 'is_active']
    column_searchable_list = ['email']
    column_filters = ['subscribed_at', 'is_active']
    column_editable_list = ['is_active']
    
    # Add email to form columns and make it required
    form_columns = ['email', 'is_active']
    
    # Make email required in the form
    form_args = {
        'email': {
            'validators': [DataRequired()],
            'render_kw': {'required': True}
        }
    }
    
    column_formatters = {
        'is_active': lambda v, c, m, p: '✅ Active' if m.is_active else '❌ Inactive',
        'subscribed_at': lambda v, c, m, p: m.subscribed_at.strftime('%Y-%m-%d %H:%M') if m.subscribed_at else ''
    }
    
    can_export = True
    export_types = ['csv', 'json']
    
    def on_model_change(self, form, model, is_created):
        """Handle unsubscribe_token generation for new subscribers"""
        if is_created:
            # Generate unsubscribe token for new subscribers
            if not model.unsubscribe_token:
                model.unsubscribe_token = secrets.token_urlsafe(32)
            
            # Ensure email is provided
            if not model.email:
                raise ValueError('Email is required for newsletter subscribers')
    
    def create_model(self, form):
        """Override create_model to ensure email is provided"""
        try:
            # Check if email is provided
            if not form.email.data:
                flash('Email is required for newsletter subscribers', 'error')
                return False
            
            # Check for duplicate email
            existing = NewsletterSubscriber.query.filter_by(email=form.email.data).first()
            if existing:
                flash(f'Email {form.email.data} is already subscribed', 'error')
                return False
            
            # Create the model
            model = NewsletterSubscriber(
                email=form.email.data,
                is_active=form.is_active.data if hasattr(form, 'is_active') else True,
                unsubscribe_token=secrets.token_urlsafe(32)
            )
            
            db.session.add(model)
            db.session.commit()
            
            flash(f'Successfully added subscriber: {model.email}', 'success')
            return model
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating subscriber: {str(e)}', 'error')
            logger.error(f"Error creating subscriber: {str(e)}")
            return False
    
    def update_model(self, form, model):
        """Override update_model to validate email changes"""
        try:
            # If email is being changed, check for duplicates
            if form.email.data and form.email.data != model.email:
                existing = NewsletterSubscriber.query.filter_by(email=form.email.data).first()
                if existing and existing.id != model.id:
                    flash(f'Email {form.email.data} is already subscribed to another account', 'error')
                    return False
            
            # Update the model
            model.email = form.email.data
            model.is_active = form.is_active.data
            
            db.session.commit()
            
            flash(f'Successfully updated subscriber: {model.email}', 'success')
            return model
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating subscriber: {str(e)}', 'error')
            logger.error(f"Error updating subscriber: {str(e)}")
            return False
    
    def after_model_delete(self, model):
        logger.info(f"Subscriber deleted: {model.email}")

class UserAdminView(SecureModelView):
    """Admin view for users (read-only)"""
    column_list = ['id', 'username', 'created_at']
    can_create = False
    can_edit = False
    can_delete = False
    column_formatters = {
        'created_at': lambda v, c, m, p: m.created_at.strftime('%Y-%m-%d %H:%M') if m.created_at else ''
    }

def init_admin(app):
    """Initialize admin interface"""
    # Set custom admin index view
    admin.index_view = SecureAdminIndexView(
        name='Dashboard',
        template='admin/index.html',
        url='/admin'
    )
    
    # Add views
    admin.add_view(ProjectAdminView(Project, db.session, name='Projects', category='Content'))
    admin.add_view(ProjectSectionAdminView(ProjectSection, db.session, name='Sections', category='Content'))
    admin.add_view(NewsletterSubscriberAdminView(NewsletterSubscriber, db.session, name='Subscribers', category='Users'))
    admin.add_view(UserAdminView(User, db.session, name='Admin Users', category='Users'))
    
    # Initialize with app
    admin.init_app(app)