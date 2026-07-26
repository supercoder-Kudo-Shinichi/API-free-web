import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config

import threading

class EmailService:
    @staticmethod
    def _send_welcome_email_sync(email: str, username: str, created_at, ip_address: str = None, user_agent: str = None) -> None:
        creation_time = created_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
        ip = ip_address or "Unknown IP"
        device = user_agent or "Unknown Device"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Welcome to Clerk Clone</title>
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
              background-color: #f9fafb;
              color: #1f2937;
              margin: 0;
              padding: 0;
            }}
            .container {{
              max-width: 600px;
              margin: 20px auto;
              background: #ffffff;
              border: 1px solid #e5e7eb;
              border-radius: 12px;
              overflow: hidden;
              box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            }}
            .header {{
              background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
              padding: 30px 20px;
              text-align: center;
              color: #ffffff;
            }}
            .header h1 {{
              margin: 0;
              font-size: 24px;
              font-weight: 700;
              letter-spacing: -0.025em;
            }}
            .content {{
              padding: 40px 30px;
            }}
            .content p {{
              font-size: 16px;
              line-height: 1.6;
              margin-top: 0;
              margin-bottom: 20px;
            }}
            .details-card {{
              background-color: #f3f4f6;
              border-radius: 8px;
              padding: 20px;
              margin-bottom: 30px;
            }}
            .detail-row {{
              display: flex;
              justify-content: space-between;
              padding: 8px 0;
              border-bottom: 1px solid #e5e7eb;
              font-size: 14px;
            }}
            .detail-row:last-child {{
              border-bottom: none;
            }}
            .detail-label {{
              font-weight: 600;
              color: #4b5563;
            }}
            .detail-value {{
              color: #111827;
            }}
            .alert-card {{
              border-left: 4px solid #ef4444;
              background-color: #fef2f2;
              padding: 15px;
              border-radius: 4px;
              font-size: 14px;
              color: #991b1b;
              margin-bottom: 30px;
            }}
            .footer {{
              background-color: #f9fafb;
              padding: 20px 30px;
              text-align: center;
              font-size: 12px;
              color: #9ca3af;
              border-top: 1px solid #e5e7eb;
            }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>Welcome, {username}!</h1>
            </div>
            <div class="content">
              <p>Thank you for creating an account with us. We're excited to have you on board!</p>
              
              <div class="details-card">
                <div class="detail-row">
                  <span class="detail-label">Username</span>
                  <span class="detail-value">{username}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Gmail Address</span>
                  <span class="detail-value">{email}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Created At</span>
                  <span class="detail-value">{creation_time}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">IP Address</span>
                  <span class="detail-value">{ip}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Device</span>
                  <span class="detail-value">{device}</span>
                </div>
              </div>

              <div class="alert-card">
                <strong>Security Notice:</strong> If you did not create this account, please ignore this email or contact support immediately to secure your information.
              </div>
            </div>
            <div class="footer">
              &copy; 2026 Clerk Clone. All rights reserved.
            </div>
          </div>
        </body>
        </html>
        """

        # Check if SMTP configuration is set
        if Config.SMTP_USER and Config.SMTP_PASS:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = 'Welcome to Clerk Clone - Account Created Successfully'
                msg['From'] = f"Clerk Clone Auth <{Config.SMTP_FROM}>"
                msg['To'] = email

                msg.attach(MIMEText(html_content, 'html'))

                with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
                    # Upgrade connection to secure if port is 587
                    if Config.SMTP_PORT == 587:
                        server.starttls()
                    server.login(Config.SMTP_USER, Config.SMTP_PASS)
                    server.sendmail(Config.SMTP_FROM, email, msg.as_string())
            except Exception as e:
                print("Failed to send email via SMTP:", str(e))
        else:
            # Local fallback mock logging
            print("============= MOCK EMAIL SENT =============")
            print(f"To: {email}")
            print(f"Subject: Welcome to Clerk Clone - Account Created Successfully")
            print(f"Content HTML:\n{html_content}")
            print("============================================")

    @staticmethod
    def send_welcome_email(email: str, username: str, created_at, ip_address: str = None, user_agent: str = None) -> None:
        """Send welcome email asynchronously in a background thread.
        This prevents the email sending from blocking the HTTP response."""
        thread = threading.Thread(
            target=EmailService._send_welcome_email_sync,
            args=(email, username, created_at),
            kwargs={"ip_address": ip_address, "user_agent": user_agent},
            daemon=True
        )
        thread.start()
