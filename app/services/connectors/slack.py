import httpx
from typing import Dict, Any
from app.services.connectors.base import BaseConnector

class SlackConnector(BaseConnector):
    async def execute(self, config: Dict[str, Any], params: Dict[str, Any], context_data: Dict[str, Any]) -> Any:
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            raise ValueError("Slack integration missing 'webhook_url' in config")

        message = params.get("message", "Default Slack Message")

        payload = {"text": message}

        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            return f"Slack message sent. Status: {response.status_code}"

slack_connector = SlackConnector()
