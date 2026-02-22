from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for, abort, session, current_app
from flask_login import login_required, current_user
from models import Project, ProjectSection, NewsletterSubscriber
from extensions import db
from email_service import send_welcome_email, send_contact_notification, send_test_email, test_email_configuration
from datetime import datetime
import logging
import secrets
import re
import requests
import json
import os
import time
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)


OLLAMA_AVAILABLE = False
OLLAMA_URL = "http://localhost:11434/api/generate"

HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY')

FREE_MODELS = [
    {
        'name': 'google/flan-t5-large',
        'needs_key': False,
        'endpoint': 'https://api-inference.huggingface.co/models/google/flan-t5-large'
    },
    {
        'name': 'gpt2',
        'needs_key': False,
        'endpoint': 'https://api-inference.huggingface.co/models/gpt2'
    },
    {
        'name': 'distilgpt2',
        'needs_key': False,
        'endpoint': 'https://api-inference.huggingface.co/models/distilgpt2'
    },
    {
        'name': 'facebook/blenderbot-400M-distill',
        'needs_key': False,
        'endpoint': 'https://api-inference.huggingface.co/models/facebook/blenderbot-400M-distill'
    }
]

# ========== SMART FALLBACK SYSTEM ==========
class SmartFallback:
    """Intelligent fallback that provides contextually relevant responses"""
    
    def __init__(self, project):
        self.project = project
        self.sections = ProjectSection.query.filter_by(project_id=project.id).order_by(ProjectSection.order_position).all()
        
        # Build knowledge base
        self.knowledge_base = {
            'title': project.title,
            'description': project.description,
            'has_github': bool(project.github_link),
            'github_link': project.github_link,
            'has_live': bool(project.live_link),
            'live_link': project.live_link,
            'sections': [
                {
                    'title': s.section_title,
                    'content': s.content[:200] + '...' if len(s.content) > 200 else s.content
                } for s in self.sections
            ]
        }
    
    def get_response(self, user_message):
        """Get response based on message intent"""
        message = user_message.lower().strip()
        
        # Greeting detection
        if any(word in message for word in ['hello', 'hi ', 'hey', 'greetings']):
            return self._greeting_response()
        
        # Question about project overview
        if any(word in message for word in ['what is', 'tell me about', 'describe', 'overview']):
            return self._overview_response()
        
        # Question about features
        if any(word in message for word in ['feature', 'capability', 'function', 'what can it do', 'abilities']):
            return self._features_response()
        
        # Question about technologies
        if any(word in message for word in ['tech', 'stack', 'language', 'framework', 'built with', 'programming']):
            return self._tech_response()
        
        # Question about GitHub/code
        if any(word in message for word in ['github', 'code', 'source', 'repository', 'git']):
            return self._github_response()
        
        # Question about live demo
        if any(word in message for word in ['live', 'demo', 'website', 'see it', 'view', 'try it']):
            return self._live_response()
        
        # Question about specific section
        for section in self.knowledge_base['sections']:
            if section['title'].lower() in message:
                return self._section_response(section)
        
        # Question about how to use
        if any(word in message for word in ['how to use', 'how do i', 'usage', 'instructions']):
            return self._usage_response()
        
        # Question about creation date/time
        if any(word in message for word in ['when', 'created', 'date', 'time']):
            return self._date_response()
        
        # Thanks
        if any(word in message for word in ['thank', 'thanks', 'appreciate']):
            return self._thanks_response()
        
        # Help/question about what to ask
        if any(word in message for word in ['help', 'what can i ask', 'options', 'support']):
            return self._help_response()
        
        # Default response
        return self._default_response()
    
    def _greeting_response(self):
        greetings = [
            f"Hello! 👋 I'm here to help you learn more about **{self.knowledge_base['title']}**. What would you like to know?",
            f"Hi there! Feel free to ask me anything about **{self.knowledge_base['title']}**!",
            f"Welcome! I can tell you about the features, technologies, and details of **{self.knowledge_base['title']}**."
        ]
        return random.choice(greetings)
    
    def _overview_response(self):
        response = f"**{self.knowledge_base['title']}**\n\n"
        response += f"{self.knowledge_base['description']}\n\n"
        
        if self.knowledge_base['sections']:
            response += "**Key Sections:**\n"
            for section in self.knowledge_base['sections'][:3]:
                response += f"• {section['title']}\n"
        
        return response
    
    def _features_response(self):
        if not self.knowledge_base['sections']:
            return f"**{self.knowledge_base['title']}** features include: {self.knowledge_base['description']}"
        
        response = f"**Key Features of {self.knowledge_base['title']}:**\n\n"
        for i, section in enumerate(self.knowledge_base['sections'][:4], 1):
            response += f"{i}. **{section['title']}**\n"
            response += f"   {section['content'][:150]}...\n\n"
        
        return response
    
    def _tech_response(self):
        # Extract potential technology mentions from description and sections
        tech_keywords = ['python', 'javascript', 'react', 'vue', 'angular', 'node', 'django', 
                        'flask', 'html', 'css', 'sql', 'mongodb', 'postgresql', 'aws', 'docker',
                        'api', 'rest', 'graphql', 'tensorflow', 'pytorch', 'machine learning',
                        'ai', 'frontend', 'backend', 'full-stack', 'mobile', 'web']
        
        mentioned_techs = []
        text_to_search = self.knowledge_base['description'].lower()
        for section in self.knowledge_base['sections']:
            text_to_search += ' ' + section['content'].lower()
        
        for tech in tech_keywords:
            if tech in text_to_search:
                mentioned_techs.append(tech)
        
        if mentioned_techs:
            mentioned_techs = list(set(mentioned_techs))[:8]  # Remove duplicates, limit to 8
            tech_list = ', '.join([f"**{t}**" for t in mentioned_techs])
            return f"Based on the project information, it appears to use: {tech_list}. Check the project details above for more specific technology information."
        else:
            return f"You can find information about the technologies used in **{self.knowledge_base['title']}** by checking the project sections above."
    
    def _github_response(self):
        if self.knowledge_base['has_github']:
            return f"The source code for **{self.knowledge_base['title']}** is available on GitHub:\n\n{self.knowledge_base['github_link']}"
        else:
            return f"The GitHub repository for **{self.knowledge_base['title']}** is not publicly available at this time. You can contact me for more information!"
    
    def _live_response(self):
        if self.knowledge_base['has_live']:
            return f"You can view the live demo of **{self.knowledge_base['title']}** here:\n\n{self.knowledge_base['live_link']}"
        else:
            return f"A live demo for **{self.knowledge_base['title']}** is not currently available. Check back later or contact me for updates!"
    
    def _section_response(self, section):
        return f"**{section['title']}**\n\n{section['content']}"
    
    def _usage_response(self):
        return f"To use or explore **{self.knowledge_base['title']}**, check out the project details above. " + \
               ("You can also try the live demo or check the code on GitHub!" if (self.knowledge_base['has_live'] or self.knowledge_base['has_github']) else "")
    
    def _date_response(self):
        if hasattr(self.project, 'created_at') and self.project.created_at:
            date_str = self.project.created_at.strftime("%B %d, %Y")
            return f"**{self.knowledge_base['title']}** was created on {date_str}."
        return f"**{self.knowledge_base['title']}** was created recently. Check the project details for more information."
    
    def _thanks_response(self):
        thanks = [
            "You're welcome! 😊 Feel free to ask if you have any other questions!",
            "Happy to help! Let me know if you need anything else.",
            "My pleasure! Any other questions about the project?"
        ]
        return random.choice(thanks)
    
    def _help_response(self):
        return f"""**You can ask me about:**
• Project overview and description
• Features and capabilities
• Technologies used
• GitHub repository
• Live demo
• Specific project sections
• When it was created
• And more!

Just ask a question about **{self.knowledge_base['title']}**!"""
    
    def _default_response(self):
        return f"I can help you learn more about **{self.knowledge_base['title']}**! You can ask about its features, technologies, GitHub repository, live demo, or any specific details. What would you like to know?"

# Try to call Hugging Face with the correct headers
def call_huggingface_free_model(prompt, model_info):
    """Call Hugging Face free models without API key"""
    try:
        headers = {
            "Content-Type": "application/json"
        }
        
        # Different payload format for different models
        if 'flan-t5' in model_info['name']:
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_length": 300,
                    "temperature": 0.7
                }
            }
        elif 'blenderbot' in model_info['name']:
            payload = {
                "inputs": {
                    "past_user_inputs": [],
                    "generated_responses": [],
                    "text": prompt
                }
            }
        else:
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_length": 300,
                    "temperature": 0.7,
                    "do_sample": True
                }
            }
        
        logger.info(f"Calling free model: {model_info['name']}")
        response = requests.post(
            model_info['endpoint'],
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Parse different response formats
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict) and "generated_text" in result[0]:
                    return result[0]["generated_text"]
                elif isinstance(result[0], str):
                    return result[0]
            elif isinstance(result, dict):
                if "generated_text" in result:
                    return result["generated_text"]
                elif "response" in result:  # For blenderbot
                    return result["response"]
            
            return str(result)
        
        elif response.status_code == 503:
            logger.info(f"Model {model_info['name']} is loading...")
            time.sleep(10)  # Wait for model to load
            return None  # Will retry on next call
        
        else:
            logger.warning(f"Free model {model_info['name']} returned {response.status_code}")
            return None
            
    except Exception as e:
        logger.warning(f"Error with free model {model_info['name']}: {str(e)}")
        return None

def try_free_models(prompt):
    """Try multiple free models until one works"""
    for model in FREE_MODELS:
        try:
            response = call_huggingface_free_model(prompt, model)
            if response:
                logger.info(f"Success with free model: {model['name']}")
                return response, model['name']
        except Exception as e:
            logger.warning(f"Free model {model['name']} failed: {str(e)}")
            continue
    
    return None, None

@main_bp.route('/')
def index():
    """Home page"""
    # Get all projects
    all_projects = Project.query.order_by(Project.created_at.desc()).all()
    
    # Split into featured and other projects
    featured_projects = [p for p in all_projects if p.is_featured][:3]  # Limit to 3 featured
    other_projects = [p for p in all_projects if not p.is_featured]
    
    return render_template('index.html', 
                         featured_projects=featured_projects,
                         other_projects=other_projects,
                         now=datetime.now())

@main_bp.route('/projects')
def projects():
    """Projects listing page"""
    page = request.args.get('page', 1, type=int)
    per_page = 9  # Show 9 projects per page
    
    # Get paginated projects
    projects_pagination = Project.query.order_by(
        Project.is_featured.desc(),
        Project.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('projects.html',
                         projects=projects_pagination.items,
                         pagination=projects_pagination,
                         now=datetime.now())

@main_bp.route('/project/<int:project_id>')
def project_detail(project_id):
    """Project detail page"""
    project = Project.query.get_or_404(project_id)
    
    # Get sections in order
    sections = ProjectSection.query.filter_by(project_id=project.id).order_by(ProjectSection.order_position).all()
    
    # Get next and previous projects for navigation
    next_project = Project.query.filter(Project.id > project_id).order_by(Project.id.asc()).first()
    prev_project = Project.query.filter(Project.id < project_id).order_by(Project.id.desc()).first()
    
    return render_template('project_detail.html',
                         project=project,
                         sections=sections,
                         next_project=next_project,
                         prev_project=prev_project,
                         now=datetime.now())

@main_bp.route('/project/<int:project_id>/json')
def project_json(project_id):
    """Get project details as JSON (for AJAX needs)"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # Format the response
        project_data = {
            'id': project.id,
            'title': project.title,
            'description': project.description,
            'live_link': project.live_link,
            'github_link': project.github_link,
            'sections': []
        }
        
        # Add sections in order
        sections = ProjectSection.query.filter_by(project_id=project.id).order_by(ProjectSection.order_position).all()
        
        for section in sections:
            project_data['sections'].append({
                'id': section.id,
                'title': section.section_title,
                'content': section.content,
                'image': section.image
            })
        
        return jsonify(project_data)
    
    except Exception as e:
        logger.error(f"Error fetching project {project_id}: {str(e)}")
        return jsonify({'error': 'Project not found'}), 404

# ========== AI CHAT ENDPOINT ==========
@main_bp.route('/api/chat/<int:project_id>', methods=['POST'])
def chat_with_ai(project_id):
    """Handle AI chat requests"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({'error': 'Message is required'}), 400
        
        # Get project details
        project = Project.query.get_or_404(project_id)
        
        # Try free Hugging Face models first
        context = f"Project: {project.title}\nDescription: {project.description}\n\nUser question: {user_message}\n\nAnswer concisely:"
        
        response_text, model_used = try_free_models(context)
        
        # If free models failed, use smart fallback
        if not response_text:
            logger.info("Using smart fallback system")
            fallback = SmartFallback(project)
            response_text = fallback.get_response(user_message)
            model_used = "smart-fallback"
        
        return jsonify({
            'success': True,
            'response': response_text,
            'project_id': project_id,
            'model': model_used
        })
        
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

# ========== NEWSLETTER ENDPOINTS ==========
@main_bp.route('/subscribe', methods=['POST'])
def subscribe():
    """Subscribe to newsletter"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email is required'}), 400
        
        # Validate email format
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        
        # Check if subscriber already exists
        subscriber = NewsletterSubscriber.query.filter_by(email=email).first()
        
        if subscriber:
            if subscriber.is_active:
                return jsonify({'success': False, 'message': 'Email already subscribed'}), 400
            else:
                # Reactivate subscriber
                subscriber.is_active = True
                # Generate new token if needed
                if not subscriber.unsubscribe_token:
                    subscriber.unsubscribe_token = secrets.token_urlsafe(32)
                db.session.commit()
                
                # Send welcome email
                try:
                    send_welcome_email(email)
                except Exception as e:
                    logger.error(f"Failed to send welcome email: {str(e)}")
                
                return jsonify({'success': True, 'message': 'Subscription reactivated successfully! Check your email for confirmation.'})
        
        # Create new subscriber with token
        unsubscribe_token = secrets.token_urlsafe(32)
        subscriber = NewsletterSubscriber(
            email=email, 
            is_active=True,
            unsubscribe_token=unsubscribe_token
        )
        db.session.add(subscriber)
        db.session.commit()
        
        # Send welcome email
        try:
            send_welcome_email(email)
        except Exception as e:
            logger.error(f"Failed to send welcome email: {str(e)}")
        
        return jsonify({'success': True, 'message': 'Successfully subscribed to newsletter! Check your email for confirmation.'})
    
    except Exception as e:
        logger.error(f"Subscription error: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred. Please try again.'}), 500

@main_bp.route('/unsubscribe/<token>')
def unsubscribe(token):
    """Unsubscribe from newsletter using token"""
    try:
        subscriber = NewsletterSubscriber.query.filter_by(unsubscribe_token=token).first()
        
        if not subscriber:
            flash('Invalid or expired unsubscribe link.', 'error')
            return redirect(url_for('main.index'))
        
        if subscriber.is_active:
            subscriber.is_active = False
            db.session.commit()
            flash(f'Successfully unsubscribed {subscriber.email} from the newsletter.', 'success')
        else:
            flash(f'{subscriber.email} is already unsubscribed.', 'info')
        
        return render_template('unsubscribe.html', email=subscriber.email)
        
    except Exception as e:
        logger.error(f"Unsubscribe error: {str(e)}")
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('main.index'))

@main_bp.route('/contact', methods=['POST'])
def contact():
    """Handle contact form submission"""
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        message = data.get('message')
        
        if not all([name, email, message]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        # Validate email
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        
        # Send notification email
        try:
            send_contact_notification(name, email, message)
        except Exception as e:
            logger.error(f"Failed to send contact notification: {str(e)}")
            return jsonify({'success': False, 'message': 'Failed to send message. Please try again.'}), 500
        
        return jsonify({'success': True, 'message': 'Message sent successfully!'})
    
    except Exception as e:
        logger.error(f"Contact form error: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred. Please try again.'}), 500

# ========== ADMIN ROUTES ==========
@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    from flask_login import login_user, current_user
    from models import User
    
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        # Use the verify_password method from the User model
        if user and user.verify_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash('Logged in successfully!', 'success')
            return redirect(next_page or url_for('admin.index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')
    
@main_bp.route('/ai')
def ai_assistant():
    """Dedicated AI assistant page"""
    # Get all projects with their sections
    all_projects = Project.query.order_by(Project.is_featured.desc(), Project.created_at.desc()).all()
    
    # Attach sections to each project for the AI to use
    for project in all_projects:
        project.sections = ProjectSection.query.filter_by(project_id=project.id).order_by(ProjectSection.order_position).all()
    
    return render_template('ai_assistant.html', 
                         all_projects=all_projects,
                         now=datetime.now())

@main_bp.route('/logout')
def logout():
    """Admin logout"""
    from flask_login import logout_user
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))
    
@main_bp.route('/reset-admin-password', methods=['GET'])
def reset_admin_password():
    """Temporary route to reset admin password (REMOVE AFTER USE)"""
    from models import User
    from flask import current_app as app
    
    # Only allow if not in production
    if app.env == 'production':
        return "Not available in production", 404
    
    try:
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user:
            # Reset password using the property setter
            admin_user.password = 'admin123'  # This will hash it properly
            db.session.commit()
            return "Admin password reset to 'admin123'. You can now login. <a href='/login'>Go to Login</a>"
        else:
            # Create new admin user
            admin_user = User(
                username='admin',
                password='admin123'
            )
            db.session.add(admin_user)
            db.session.commit()
            return "Admin user created with password 'admin123'. <a href='/login'>Go to Login</a>"
    except Exception as e:
        return f"Error: {str(e)}"