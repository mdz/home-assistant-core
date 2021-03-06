"""Provide configuration end points for Automations."""
from collections import OrderedDict
import uuid

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.automation import (
    get_debug_traces,
    get_debug_traces_for_automation,
)
from homeassistant.components.automation.config import (
    DOMAIN,
    PLATFORM_SCHEMA,
    async_validate_config_item,
)
from homeassistant.config import AUTOMATION_CONFIG_PATH
from homeassistant.const import CONF_ID, SERVICE_RELOAD
from homeassistant.helpers import config_validation as cv, entity_registry

from . import ACTION_DELETE, EditIdBasedConfigView


async def async_setup(hass):
    """Set up the Automation config API."""

    websocket_api.async_register_command(hass, websocket_automation_trace_get)
    websocket_api.async_register_command(hass, websocket_automation_trace_list)

    async def hook(action, config_key):
        """post_write_hook for Config View that reloads automations."""
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD)

        if action != ACTION_DELETE:
            return

        ent_reg = await entity_registry.async_get_registry(hass)

        entity_id = ent_reg.async_get_entity_id(DOMAIN, DOMAIN, config_key)

        if entity_id is None:
            return

        ent_reg.async_remove(entity_id)

    hass.http.register_view(
        EditAutomationConfigView(
            DOMAIN,
            "config",
            AUTOMATION_CONFIG_PATH,
            cv.string,
            PLATFORM_SCHEMA,
            post_write_hook=hook,
            data_validator=async_validate_config_item,
        )
    )
    return True


class EditAutomationConfigView(EditIdBasedConfigView):
    """Edit automation config."""

    def _write_value(self, hass, data, config_key, new_value):
        """Set value."""
        index = None
        for index, cur_value in enumerate(data):
            # When people copy paste their automations to the config file,
            # they sometimes forget to add IDs. Fix it here.
            if CONF_ID not in cur_value:
                cur_value[CONF_ID] = uuid.uuid4().hex

            elif cur_value[CONF_ID] == config_key:
                break
        else:
            cur_value = OrderedDict()
            cur_value[CONF_ID] = config_key
            index = len(data)
            data.append(cur_value)

        # Iterate through some keys that we want to have ordered in the output
        updated_value = OrderedDict()
        for key in ("id", "alias", "description", "trigger", "condition", "action"):
            if key in cur_value:
                updated_value[key] = cur_value[key]
            if key in new_value:
                updated_value[key] = new_value[key]

        # We cover all current fields above, but just in case we start
        # supporting more fields in the future.
        updated_value.update(cur_value)
        updated_value.update(new_value)
        data[index] = updated_value


@websocket_api.websocket_command(
    {vol.Required("type"): "automation/trace/get", vol.Optional("automation_id"): str}
)
@websocket_api.async_response
async def websocket_automation_trace_get(hass, connection, msg):
    """Get automation traces."""
    automation_id = msg.get("automation_id")

    if not automation_id:
        automation_traces = get_debug_traces(hass)
    else:
        automation_traces = {
            automation_id: get_debug_traces_for_automation(hass, automation_id)
        }

    connection.send_result(msg["id"], automation_traces)


@websocket_api.websocket_command({vol.Required("type"): "automation/trace/list"})
@websocket_api.async_response
async def websocket_automation_trace_list(hass, connection, msg):
    """Summarize automation traces."""
    automation_traces = get_debug_traces(hass, summary=True)

    connection.send_result(msg["id"], automation_traces)
