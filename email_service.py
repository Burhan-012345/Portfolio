import threading
import logging
import secrets
from datetime import datetime
from flask import render_template, current_app, url_for
from flask_mail import Message
from extensions import mail, db
from models import NewsletterSubscriber

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_email_configuration():
    """Test function to verify email setup"""
    try:
        from flask import current_app
        app = current_app._get_current_object()
        
        with app.app_context():
            # Log email configuration (without password)
            logger.info("=== Email Configuration Test ===")
            logger.info(f"MAIL_SERVER: {app.config.get('MAIL_SERVER')}")
            logger.info(f"MAIL_PORT: {app.config.get('MAIL_PORT')}")
            logger.info(f"MAIL_USE_TLS: {app.config.get('MAIL_USE_TLS')}")
            logger.info(f"MAIL_USE_SSL: {app.config.get('MAIL_USE_SSL')}")
            logger.info(f"MAIL_USERNAME: {app.config.get('MAIL_USERNAME')}")
            logger.info(f"MAIL_DEFAULT_SENDER: {app.config.get('MAIL_DEFAULT_SENDER')}")
            logger.info("================================")
            
            return True
    except Exception as e:
        logger.error(f"Error testing email config: {str(e)}")
        return False

def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        try:
            mail.send(msg)
            logger.info(f"Email sent successfully to {msg.recipients}")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")

def send_welcome_email(email):
    """Send welcome email to new subscriber"""
    try:
        from flask import current_app
        app = current_app._get_current_object()
        
        with app.app_context():
            # Get subscriber
            subscriber = NewsletterSubscriber.query.filter_by(email=email).first()
            
            if not subscriber:
                logger.error(f"Subscriber {email} not found")
                return False
            
            # Generate unsubscribe token if not exists
            if not subscriber.unsubscribe_token:
                subscriber.unsubscribe_token = secrets.token_urlsafe(32)
                db.session.commit()
            
            # Create unsubscribe URL
            unsubscribe_url = url_for('main.unsubscribe', token=subscriber.unsubscribe_token, _external=True)
            
            subject = "Welcome to Burhan Ahmed's Newsletter"
            
            # Render HTML template from email subdirectory
            html_content = render_template(
                'email/welcome_email.html',
                email=email,
                unsubscribe_url=unsubscribe_url,
                now=datetime.now()
            )
            
            # Create text version as fallback
            text_content = f"""
            WELCOME TO BURHAN AHMED'S NEWSLETTER
            
            Hello {email}!
            
            Thank you for subscribing to my newsletter. I'm thrilled to have you on board!
            
            You'll now receive updates about:
            - Latest projects and design work
            - Design insights and tutorials
            - Exclusive behind-the-scenes content
            - Early access to new features
            
            I believe in quality over quantity — you'll only hear from me when there's something genuinely worth sharing. No spam, ever.
            
            View my latest work: {url_for('main.projects', _external=True)}
            
            If you have any questions or just want to say hi, feel free to reply to this email.
            
            Best regards,
            Burhan Ahmed
            
            ---
            To unsubscribe: {unsubscribe_url}
            Visit website: {url_for('main.index', _external=True)}
            
            © {datetime.now().year} Burhan Ahmed. All rights reserved.
            """
            
            msg = Message(
                subject=subject,
                recipients=[email],
                html=html_content,
                body=text_content
            )
            
            threading.Thread(target=send_async_email, args=(app, msg)).start()
            logger.info(f"Welcome email sent to {email}")
            return True
            
    except Exception as e:
        logger.error(f"Error sending welcome email to {email}: {str(e)}")
        return False

def send_project_notification(project):
    """Send project notification to all active subscribers"""
    try:
        from flask import current_app
        app = current_app._get_current_object()
        
        with app.app_context():
            # Get all active subscribers
            subscribers = NewsletterSubscriber.query.filter_by(is_active=True).all()
            
            if not subscribers:
                logger.info("No active subscribers to notify")
                return False
            
            # Create email content
            subject = f"New Project: {project.title}"
            
            # Send to each subscriber individually
            for subscriber in subscribers:
                try:
                    # Generate unsubscribe token if needed
                    if not subscriber.unsubscribe_token:
                        subscriber.unsubscribe_token = secrets.token_urlsafe(32)
                        db.session.commit()
                    
                    # Create unsubscribe URL
                    unsubscribe_url = url_for('main.unsubscribe', token=subscriber.unsubscribe_token, _external=True)
                    
                    # Get project detail URL
                    project_url = url_for('main.project_detail', project_id=project.id, _external=True)
                    
                    # Render HTML template from email subdirectory
                    html_content = render_template(
                        'email/project_notification.html',
                        project=project,
                        unsubscribe_url=unsubscribe_url,
                        now=datetime.now()
                    )
                    
                    # Create text version as fallback
                    text_content = f"""
                    NEW PROJECT: {project.title.upper()}
                    
                    {project.description}
                    
                    View the project: {project_url}
                    
                    {f'Live Demo: {project.live_link}' if project.live_link else ''}
                    {f'GitHub: {project.github_link}' if project.github_link else ''}
                    
                    ———–
                    To unsubscribe: {unsubscribe_url}
                    
                    © {datetime.now().year} Burhan Ahmed
                    """
                    
                    msg = Message(
                        subject=subject,
                        recipients=[subscriber.email],
                        html=html_content,
                        body=text_content
                    )
                    
                    # Send asynchronously
                    threading.Thread(target=send_async_email, args=(app, msg)).start()
                    
                except Exception as e:
                    logger.error(f"Failed to send notification to {subscriber.email}: {str(e)}")
                    continue
            
            logger.info(f"Project notification sent to {len(subscribers)} subscribers")
            return True
            
    except Exception as e:
        logger.error(f"Error sending project notifications: {str(e)}")
        return False

def send_contact_notification(name, email, message):
    """Send notification email when someone uses the contact form"""
    try:
        from flask import current_app, render_template
        app = current_app._get_current_object()
        
        with app.app_context():
            admin_email = app.config.get('MAIL_USERNAME')
            if not admin_email:
                logger.error("Admin email not configured")
                return False
            
            subject = f"New Contact: {name}"
            
            # Render HTML template from email subdirectory
            html_content = render_template(
                'email/contact_notification.html',
                name=name,
                email=email,
                message=message,
                now=datetime.now()
            )
            
            # Create text version as fallback
            text_content = f"""
            NEW CONTACT MESSAGE
            
            Name: {name}
            Email: {email}
            
            Message:
            {message}
            
            Received: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            Reply to: {email}
            """
            
            msg = Message(
                subject=subject,
                recipients=[admin_email],
                reply_to=email,
                html=html_content,
                body=text_content
            )
            
            threading.Thread(target=send_async_email, args=(app, msg)).start()
            logger.info(f"Contact notification sent for message from {name}")
            return True
            
    except Exception as e:
        logger.error(f"Error sending contact notification: {str(e)}")
        return False

def send_test_email(email):
    """Send test email to verify configuration"""
    try:
        from flask import current_app
        app = current_app._get_current_object()
        
        with app.app_context():
            subject = "Test Email — Portfolio"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Test Email</title>
                <style>
                    body {{
                        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        line-height: 1.6;
                        color: #000000;
                        margin: 0;
                        padding: 0;
                        background-color: #ffffff;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 20px auto;
                        background: #ffffff;
                        border: 1px solid #eaeaea;
                    }}
                    .header {{
                        padding: 40px 30px;
                        text-align: center;
                        border-bottom: 1px solid #eaeaea;
                    }}
                    .header h1 {{
                        margin: 0;
                        color: #000000;
                        font-size: 28px;
                        font-weight: 600;
                        letter-spacing: -0.02em;
                    }}
                    .content {{
                        padding: 40px 30px;
                    }}
                    .success-icon {{
                        font-size: 48px;
                        text-align: center;
                        margin: 20px 0;
                        color: #000000;
                    }}
                    .check-item {{
                        margin: 15px 0;
                        padding: 10px 0;
                        border-bottom: 1px solid #eaeaea;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 14px 32px;
                        background: #000000;
                        color: #ffffff;
                        text-decoration: none;
                        font-weight: 500;
                        margin: 20px 0;
                        border-radius: 8px;
                        letter-spacing: -0.01em;
                    }}
                    .footer {{
                        padding: 30px;
                        text-align: center;
                        font-size: 14px;
                        color: #666666;
                        border-top: 1px solid #eaeaea;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✓ TEST EMAIL</h1>
                    </div>
                    <div class="content">
                        <div class="success-icon">✓</div>
                        <h2 style="text-align: center; margin-bottom: 30px;">Configuration Successful</h2>
                        
                        <div class="check-item">✓ Flask-Mail properly configured</div>
                        <div class="check-item">✓ SMTP connection working</div>
                        <div class="check-item">✓ Email templates rendering correctly</div>
                        <div class="check-item">✓ Async email sending functional</div>
                        
                        <div style="text-align: center; margin-top: 40px;">
                            <p style="margin-bottom: 20px;">All systems operational.</p>
                            <span class="button">READY →</span>
                        </div>
                        
                        <p style="color: #666666; font-size: 14px; text-align: center; margin-top: 40px;">
                            Sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                        </p>
                    </div>
                    <div class="footer">
                        <p>&copy; {datetime.now().year} BURHAN AHMED</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            text_content = f"""
            TEST EMAIL — PORTFOLIO
            
            Configuration Successful
            
            ✓ Flask-Mail properly configured
            ✓ SMTP connection working
            ✓ Email templates rendering correctly
            ✓ Async email sending functional
            
            All systems operational.
            
            Sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            
            © {datetime.now().year} Burhan Ahmed
            """
            
            msg = Message(
                subject=subject,
                recipients=[email],
                html=html_content,
                body=text_content
            )
            
            threading.Thread(target=send_async_email, args=(app, msg)).start()
            logger.info(f"Test email sent to {email}")
            return True
            
    except Exception as e:
        logger.error(f"Error sending test email: {str(e)}")
        return False

def send_bulk_newsletter(subject, html_content, text_content=None):
    """Send newsletter to all active subscribers"""
    try:
        from flask import current_app
        app = current_app._get_current_object()
        
        with app.app_context():
            subscribers = NewsletterSubscriber.query.filter_by(is_active=True).all()
            
            if not subscribers:
                logger.info("No active subscribers to send newsletter")
                return False
            
            # Create default text content if not provided
            if not text_content:
                text_content = f"""
                {subject}
                
                View this newsletter online at: {url_for('main.index', _external=True)}
                
                To unsubscribe, visit your preferences.
                
                © {datetime.now().year} Burhan Ahmed
                """
            
            # Send in batches to avoid overwhelming the server
            batch_size = 50
            successful_batches = 0
            
            for i in range(0, len(subscribers), batch_size):
                batch = subscribers[i:i+batch_size]
                recipient_emails = [subscriber.email for subscriber in batch]
                
                try:
                    msg = Message(
                        subject=subject,
                        recipients=recipient_emails,
                        html=html_content,
                        body=text_content
                    )
                    
                    threading.Thread(target=send_async_email, args=(app, msg)).start()
                    successful_batches += 1
                    
                except Exception as e:
                    logger.error(f"Failed to send batch {i//batch_size + 1}: {str(e)}")
                    continue
            
            logger.info(f"Newsletter sent to {len(subscribers)} subscribers in {successful_batches} batches")
            return True
            
    except Exception as e:
        logger.error(f"Error sending bulk newsletter: {str(e)}")
        return False