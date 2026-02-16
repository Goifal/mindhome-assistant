"""Config flow fuer MindHome Assistant."""

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_URL

from . import DOMAIN

DEFAULT_URL = "http://192.168.1.200:8200"


class MindHomeAssistantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow fuer MindHome Assistant."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")

            # Verbindung testen
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{url}/api/assistant/health",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("status") in ("ok", "degraded"):
                                return self.async_create_entry(
                                    title="MindHome Assistant",
                                    data={"url": url},
                                )
                        errors["base"] = "cannot_connect"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL, default=DEFAULT_URL): str,
            }),
            errors=errors,
        )
