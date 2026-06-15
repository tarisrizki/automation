import httpx
from typing import Dict, Any
from app.services.connectors.base import BaseConnector

class EmailConnector(BaseConnector):
    async def execute(self, config: Dict[str, Any], params: Dict[str, Any], context_data: Dict[str, Any]) -> Any:
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError("Email/SendGrid integration missing 'api_key' in config")
        
        from_email = config.get("from_email", "noreply@example.com")
        to_email = params.get("to")
        subject = params.get("subject", "Workflow Notification")
        body = params.get("body", "")

        # SendGrid API v3 payload
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}]
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers)
            response.raise_for_status()
            return f"Email sent via SendGrid to {to_email}"

email_connector = EmailConnector()
