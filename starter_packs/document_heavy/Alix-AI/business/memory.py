import os
import json
from datetime import datetime

class ConversationMemory:
    def __init__(self, sessions_dir, session_id=None):
        self.sessions_dir = sessions_dir
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = session_id
        self.filepath = os.path.join(self.sessions_dir, f"session_{self.session_id}.json")
        self.messages = []
        self.load()

    def add_message(self, role, content, name=None, tool_calls=None, tool_call_id=None):
        """Append a new message to the memory list."""
        msg = {
            "role": role,
            "content": content or "",
            "timestamp": datetime.now().isoformat()
        }
        if name:
            msg["name"] = name
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
            
        self.messages.append(msg)
        self.save()

    def get_messages(self):
        """Return raw messages formatted for the LLM."""
        formatted = []
        for msg in self.messages:
            f_msg = {
                "role": msg["role"],
                "content": msg.get("content") or ""
            }
            if "name" in msg:
                f_msg["name"] = msg["name"]
            if "tool_calls" in msg:
                f_msg["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                f_msg["tool_call_id"] = msg["tool_call_id"]
            formatted.append(f_msg)
        return formatted

    def clear(self):
        """Clear memory."""
        self.messages = []
        self.save()

    def save(self):
        """Save history to local JSON file."""
        try:
            with open(self.filepath, "w") as f:
                json.dump({
                    "session_id": self.session_id,
                    "updated_at": datetime.now().isoformat(),
                    "messages": self.messages
                }, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save session history: {e}")

    def load(self):
        """Load history from local JSON file if exists."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                    self.messages = data.get("messages", [])
            except Exception as e:
                print(f"Warning: Failed to load session history: {e}")
                self.messages = []


class DocumentProductionMemory:
    """Persistent long-term memory engine for document preferences, template field mappings, and audit history."""
    
    def __init__(self, memory_dir="./workspace/.memory"):
        self.memory_dir = memory_dir
        os.makedirs(self.memory_dir, exist_ok=True)
        
        self.prefs_file = os.path.join(self.memory_dir, "preferences.json")
        self.mappings_file = os.path.join(self.memory_dir, "field_mappings.json")
        self.history_file = os.path.join(self.memory_dir, "production_history.json")
        
        self.preferences = self._load_json(self.prefs_file, default=[])
        self.field_mappings = self._load_json(self.mappings_file, default={})
        self.production_history = self._load_json(self.history_file, default=[])

    def _load_json(self, filepath, default):
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load {filepath}: {e}")
        return default

    def _save_json(self, filepath, data):
        try:
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save {filepath}: {e}")

    # --- Preferences ---
    def add_preference(self, rule):
        rule = rule.strip()
        if rule and rule not in self.preferences:
            self.preferences.append(rule)
            self._save_json(self.prefs_file, self.preferences)
            return True
        return False

    def remove_preference(self, rule_text_or_index):
        try:
            if isinstance(rule_text_or_index, int) or str(rule_text_or_index).isdigit():
                idx = int(rule_text_or_index) - 1
                if 0 <= idx < len(self.preferences):
                    removed = self.preferences.pop(idx)
                    self._save_json(self.prefs_file, self.preferences)
                    return f"Removed preference: '{removed}'"
            # Try text match
            for rule in list(self.preferences):
                if rule_text_or_index.lower() in rule.lower():
                    self.preferences.remove(rule)
                    self._save_json(self.prefs_file, self.preferences)
                    return f"Removed preference: '{rule}'"
        except Exception as e:
            return f"Error removing preference: {e}"
        return "Preference not found."

    def get_preferences(self):
        return list(self.preferences)

    # --- Template Field Mappings ---
    def add_field_mapping(self, template_name, intake_field, placeholder_field):
        template_name = template_name.lower().strip()
        if template_name not in self.field_mappings:
            self.field_mappings[template_name] = {}
            
        self.field_mappings[template_name][intake_field.strip()] = placeholder_field.strip()
        self._save_json(self.mappings_file, self.field_mappings)
        return f"Mapped '{intake_field}' -> '{placeholder_field}' for template '{template_name}'."

    def get_field_mappings(self, template_name=None):
        if template_name:
            return self.field_mappings.get(template_name.lower().strip(), {})
        return dict(self.field_mappings)

    # --- Production History ---
    def log_production(self, input_file, template_used, output_file, extracted_fields=None, status="success"):
        record = {
            "timestamp": datetime.now().isoformat(),
            "input_file": input_file,
            "template_used": template_used,
            "output_file": output_file,
            "extracted_fields": extracted_fields or {},
            "status": status
        }
        self.production_history.append(record)
        self._save_json(self.history_file, self.production_history)

    def get_production_history(self, limit=10):
        return self.production_history[-limit:]

    # --- System Prompt Injection Helper ---
    def get_system_prompt_summary(self):
        lines = []
        
        # User Preferences
        if self.preferences:
            lines.append("PERSISTENT USER PREFERENCES & PRODUCTION RULES:")
            for idx, pref in enumerate(self.preferences, 1):
                lines.append(f"  {idx}. {pref}")
        else:
            lines.append("PERSISTENT USER PREFERENCES: None set yet.")
            
        # Field Mappings
        if self.field_mappings:
            lines.append("\nLEARNED TEMPLATE FIELD MAPPINGS:")
            for t_name, mappings in self.field_mappings.items():
                m_str = ", ".join(f"'{k}' -> '{v}'" for k, v in mappings.items())
                lines.append(f"  • Template [{t_name}]: {m_str}")
                
        # Recent Production History
        if self.production_history:
            lines.append("\nRECENT PRODUCTION AUDIT LOG (Last 3):")
            for item in self.production_history[-3:]:
                ts = item.get("timestamp", "")[:19].replace("T", " ")
                lines.append(f"  • [{ts}] Template: {item.get('template_used')} -> Output: {os.path.basename(item.get('output_file', ''))} (Status: {item.get('status')})")

        return "\n".join(lines)
