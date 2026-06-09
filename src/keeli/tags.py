"""
Tag and skill management for Keeli work items.

Replaces persona-based categorization with flexible tagging system.
"""

import json
from typing import Literal


# Common tag categories
TagCategory = Literal[
    "type",          # implementation, design, test, doc, refactor
    "risk",          # low, medium, high, critical
    "security",      # auth, payment, pii, secrets
    "performance",   # optimization, scaling, latency
    "breaking",      # api-change, schema-change, contract-change
    "urgent",        # hotfix, p0, blocking
]


# Common skills that tasks might require
COMMON_SKILLS = [
    "architecture",
    "backend",
    "frontend",
    "database",
    "security",
    "testing",
    "devops",
    "performance",
    "documentation",
    "api-design",
    "ui-ux",
]


def parse_tags(tags_json: str | None) -> list[str]:
    """Parse JSON tags array, return empty list if invalid."""
    if not tags_json:
        return []
    try:
        result = json.loads(tags_json)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def serialize_tags(tags: list[str]) -> str:
    """Serialize tags list to JSON string."""
    return json.dumps(tags)


def add_tag(tags_json: str | None, tag: str) -> str:
    """Add a tag to existing tags JSON, avoiding duplicates."""
    tags = parse_tags(tags_json)
    tag_normalized = tag.strip().lower()
    if tag_normalized and tag_normalized not in tags:
        tags.append(tag_normalized)
    return serialize_tags(tags)


def remove_tag(tags_json: str | None, tag: str) -> str:
    """Remove a tag from existing tags JSON."""
    tags = parse_tags(tags_json)
    tag_normalized = tag.strip().lower()
    tags = [t for t in tags if t != tag_normalized]
    return serialize_tags(tags)


def has_tag(tags_json: str | None, tag: str) -> bool:
    """Check if a specific tag exists."""
    tags = parse_tags(tags_json)
    tag_normalized = tag.strip().lower()
    return tag_normalized in tags


def match_any_tag(tags_json: str | None, search_tags: list[str]) -> bool:
    """Check if any of the search tags match."""
    tags = parse_tags(tags_json)
    search_normalized = [t.strip().lower() for t in search_tags]
    return any(t in search_normalized for t in tags)


def infer_tags_from_content(title: str, objective: str = "") -> list[str]:
    """
    Infer tags from task title and objective content.
    
    This provides basic auto-tagging. Can be enhanced with ML/embeddings later.
    """
    text = f"{title} {objective}".lower()
    tags = []
    
    # Type detection
    if any(word in text for word in ["implement", "add", "create", "build"]):
        tags.append("type:implementation")
    elif any(word in text for word in ["design", "architecture", "plan"]):
        tags.append("type:design")
    elif any(word in text for word in ["test", "verify", "validate"]):
        tags.append("type:test")
    elif any(word in text for word in ["document", "docs", "readme"]):
        tags.append("type:doc")
    elif any(word in text for word in ["refactor", "cleanup", "simplify"]):
        tags.append("type:refactor")
    elif any(word in text for word in ["fix", "bug", "issue"]):
        tags.append("type:bugfix")
    
    # Risk detection
    if any(word in text for word in ["critical", "urgent", "p0", "hotfix"]):
        tags.append("risk:critical")
    elif any(word in text for word in ["breaking", "migration", "deprecate"]):
        tags.append("risk:high")
    
    # Security detection
    if any(word in text for word in ["auth", "login", "oauth", "jwt", "token", "session"]):
        tags.append("security:auth")
    elif any(word in text for word in ["payment", "billing", "checkout", "stripe"]):
        tags.append("security:payment")
    elif any(word in text for word in ["encrypt", "decrypt", "secret", "credential", "api key"]):
        tags.append("security:secrets")
    elif any(word in text for word in ["pii", "gdpr", "privacy", "personal data"]):
        tags.append("security:pii")
    
    # Performance detection
    if any(word in text for word in ["performance", "optimize", "speed", "slow", "latency"]):
        tags.append("performance:optimization")
    elif any(word in text for word in ["scale", "scaling", "throughput", "capacity"]):
        tags.append("performance:scaling")
    
    # API detection
    if any(word in text for word in ["api", "endpoint", "route", "graphql", "rest"]):
        tags.append("api-change")
    
    # Database detection
    if any(word in text for word in ["database", "migration", "schema", "sql", "query"]):
        tags.append("database")
    
    return tags


def migrate_persona_to_tags(persona: str | None) -> list[str]:
    """
    Convert legacy persona field to tags for backward compatibility.
    
    Maps:
    - @po → type:requirements, skill:product
    - @architect → type:design, skill:architecture
    - @developer → type:implementation, skill:backend
    - @qa → type:test, skill:testing
    - @security → security:review, skill:security
    - @author → type:doc, skill:documentation
    """
    if not persona:
        return []
    
    persona_map = {
        "po": ["type:requirements", "skill:product"],
        "architect": ["type:design", "skill:architecture"],
        "developer": ["type:implementation", "skill:backend"],
        "qa": ["type:test", "skill:testing"],
        "security": ["security:review", "skill:security"],
        "author": ["type:doc", "skill:documentation"],
    }
    
    return persona_map.get(persona.strip().lower(), [])


def suggest_required_skills(tags: list[str]) -> list[str]:
    """
    Suggest skills required based on task tags.
    
    Returns a list of skill identifiers that should review/approve this task.
    """
    skills = set()
    
    for tag in tags:
        if tag.startswith("security:"):
            skills.add("security")
        if tag.startswith("performance:"):
            skills.add("performance")
        if tag in ["api-change", "breaking"]:
            skills.add("architecture")
        if tag == "database":
            skills.add("database")
        if tag.startswith("type:test"):
            skills.add("testing")
        if tag.startswith("type:design"):
            skills.add("architecture")
    
    return list(skills)
