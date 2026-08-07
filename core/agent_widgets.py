"""Core engine for AIMAOS agent UI widgets (interactive fillable forms and alert banners).

Allows office agents (Alix, Finn, Kai, Zoe, Marley) to publish structured input
specifications and priority callout banners into the browser workstation.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("aimaos.widgets")

SUPPORTED_FIELD_TYPES = {"text", "textarea", "select", "checkbox", "date", "file", "radio"}
SUPPORTED_BANNER_LEVELS = {"urgent", "warning", "info"}


def validate_widget_schema(widget_data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize and validate an interactive form schema or alert banner payload.

    Returns a clean dictionary safe for serialization and browser rendering.
    """
    if not isinstance(widget_data, dict):
        raise ValueError("Widget specification must be a dictionary.")

    clean_widget: dict[str, Any] = {}

    # 1. Interactive Form Validation
    if "interactive_form" in widget_data or "fields" in widget_data:
        form_spec = widget_data.get("interactive_form") if "interactive_form" in widget_data else widget_data
        if not isinstance(form_spec, dict):
            raise ValueError("interactive_form must be a dictionary.")

        raw_fields = form_spec.get("fields", [])
        if not isinstance(raw_fields, list):
            raise ValueError("Form fields must be a list.")

        clean_fields = []
        for idx, field in enumerate(raw_fields[:50]):  # Limit max fields per form
            if not isinstance(field, dict):
                continue
            field_id = str(field.get("id") or field.get("name") or f"field_{idx}").strip()
            field_type = str(field.get("type", "text")).strip().lower()
            if field_type not in SUPPORTED_FIELD_TYPES:
                field_type = "text"

            label = str(field.get("label") or field_id).strip()[:200]
            description = str(field.get("description") or "").strip()[:500]
            placeholder = str(field.get("placeholder") or "").strip()[:200]
            required = bool(field.get("required", False))

            raw_options = field.get("options", [])
            clean_options = []
            if isinstance(raw_options, list):
                for opt in raw_options[:100]:
                    if isinstance(opt, dict):
                        val = str(opt.get("value") or opt.get("label") or "").strip()[:200]
                        lbl = str(opt.get("label") or opt.get("value") or "").strip()[:200]
                        if val:
                            clean_options.append({"value": val, "label": lbl or val})
                    elif opt is not None:
                        opt_str = str(opt).strip()[:200]
                        if opt_str:
                            clean_options.append({"value": opt_str, "label": opt_str})

            clean_fields.append({
                "id": field_id,
                "type": field_type,
                "label": label,
                "description": description or None,
                "placeholder": placeholder or None,
                "required": required,
                "options": clean_options if field_type in {"select", "radio", "checkbox"} else [],
                "default_value": str(field.get("default_value", ""))[:500] if field.get("default_value") is not None else None,
            })

        clean_widget["interactive_form"] = {
            "title": str(form_spec.get("title") or "Required Information").strip()[:200],
            "instructions": str(form_spec.get("instructions") or "").strip()[:1000] or None,
            "submit_label": str(form_spec.get("submit_label") or "Submit to Agent").strip()[:100],
            "fields": clean_fields,
        }

    # 2. Alert Banner Validation
    if "alert_banner" in widget_data or "level" in widget_data:
        banner_spec = widget_data.get("alert_banner") if "alert_banner" in widget_data else widget_data
        if isinstance(banner_spec, dict):
            level = str(banner_spec.get("level", "info")).strip().lower()
            if level not in SUPPORTED_BANNER_LEVELS:
                level = "info"
            title = str(banner_spec.get("title") or "Notice").strip()[:200]
            message = str(banner_spec.get("message") or "").strip()[:500]
            action_label = str(banner_spec.get("action_label") or "").strip()[:100]
            action_target = str(banner_spec.get("action_target") or "").strip()[:200]

            clean_widget["alert_banner"] = {
                "level": level,
                "title": title,
                "message": message or None,
                "action_label": action_label or None,
                "action_target": action_target or None,
            }

    return clean_widget


def build_form_field(
    field_id: str,
    label: str,
    field_type: str = "text",
    *,
    required: bool = False,
    options: list[str | dict[str, str]] | None = None,
    placeholder: str | None = None,
    description: str | None = None,
    default_value: Any = None,
) -> dict[str, Any]:
    """Helper to build a single field schema dictionary for an interactive form."""
    return {
        "id": field_id,
        "label": label,
        "type": field_type,
        "required": required,
        "options": options or [],
        "placeholder": placeholder,
        "description": description,
        "default_value": default_value,
    }


def build_interactive_form(
    title: str,
    fields: list[dict[str, Any]],
    *,
    instructions: str | None = None,
    submit_label: str = "Submit to Agent",
) -> dict[str, Any]:
    """Helper to build a complete interactive_form dictionary."""
    raw = {
        "interactive_form": {
            "title": title,
            "instructions": instructions,
            "submit_label": submit_label,
            "fields": fields,
        }
    }
    return validate_widget_schema(raw)["interactive_form"]


def build_alert_banner(
    title: str,
    message: str,
    *,
    level: str = "warning",
    action_label: str | None = None,
    action_target: str | None = None,
) -> dict[str, Any]:
    """Helper to build a complete alert_banner dictionary."""
    raw = {
        "alert_banner": {
            "level": level,
            "title": title,
            "message": message,
            "action_label": action_label,
            "action_target": action_target,
        }
    }
    return validate_widget_schema(raw)["alert_banner"]
