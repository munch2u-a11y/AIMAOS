import os
import json
import logging
from datetime import datetime


def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p


AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()

logger = logging.getLogger(__name__)

CATEGORY_SKILLS_DIR = os.path.join(AIMAOS_ROOT, "comms", "category_skills")

def get_category_slug(category_name):
    if not category_name:
        return "general"
    clean = str(category_name).lower().replace(" ", "_").replace("-", "_")
    return clean

class CategorySkillRepository:
    """
    Cross-Case Category Knowledge Store.
    Allows CaseManagers working on the same case category (e.g., name_change, estate_planning, probate)
    to share procedural skills and takeaways without overloading individual case files with unrelated case details.
    """
    def __init__(self, base_dir=CATEGORY_SKILLS_DIR):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def get_skills_file(self, category_name):
        slug = get_category_slug(category_name)
        return os.path.join(self.base_dir, f"{slug}.json")

    def load_category_skills(self, category_name):
        """Loads shared category skills for a given practice area."""
        filepath = self.get_skills_file(category_name)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load category skills for {category_name}: {e}")
        return []

    def add_category_skill(self, category_name, skill_statement, source_client=None):
        """Saves a learned skill into the category repository so peer case managers inherit it."""
        filepath = self.get_skills_file(category_name)
        skills = self.load_category_skills(category_name)
        
        # Check for duplicates
        for s in skills:
            if s.get("statement", "").lower().strip() == skill_statement.lower().strip():
                return False  # Already exists

        entry = {
            "id": f"skill_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "statement": skill_statement,
            "category": get_category_slug(category_name),
            "source_client": source_client,
            "added_at": datetime.now().isoformat()
        }
        skills.append(entry)
        
        try:
            with open(filepath, "w") as f:
                json.dump(skills, f, indent=2)
            logger.info(f"Saved category skill for [{category_name}]: '{skill_statement[:80]}...'")
            return True
        except Exception as e:
            logger.warning(f"Could not save category skill: {e}")
            return False
