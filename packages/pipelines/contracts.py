"""Structured-output contracts shared by extraction pipelines and tests."""

CLASSIFICATION_SCHEMA = {
    "title": "source_classification",
    "type": "object",
    "properties": {
        "is_relevant": {"type": "boolean"},
        "reasoning": {"type": "string"},
    },
    "required": ["is_relevant", "reasoning"],
    "additionalProperties": False,
}


FACT_EXTRACTION_SCHEMA = {
    "title": "komponist_fact_extraction",
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["Decision", "Goal", "Constraint", "Project"],
                    },
                    "statement": {"type": "string"},
                    "detail": {"type": "string"},
                    "excerpt": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "modality": {
                        "type": "string",
                        "enum": [
                            "fact",
                            "decision",
                            "goal",
                            "required",
                            "planned",
                            "conditional",
                        ],
                    },
                    "relations_hint": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "relation": {
                                    "type": "string",
                                    "enum": [
                                        "ADVANCES",
                                        "AFFECTS",
                                        "DEPENDS_ON",
                                        "SUPERSEDES",
                                        "CONSTRAINS",
                                        "RELATES_TO",
                                    ],
                                },
                                "target_hint": {"type": "string"},
                            },
                            "required": ["relation", "target_hint"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "type",
                    "statement",
                    "detail",
                    "excerpt",
                    "confidence",
                    "modality",
                    "relations_hint",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}
