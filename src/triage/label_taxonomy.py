"""Kyverno label taxonomy mapping.

Maps between the classifier's output categories and the actual labels
used in the kyverno/kyverno repository.
"""

# Mapping from classifier output -> actual GitHub labels
KIND_LABEL_MAP = {
    "kind/bug": ["kind/bug", "bug"],
    "kind/feature": ["kind/feature", "feature", "enhancement"],
    "kind/question": ["kind/question"],
    "kind/cleanup": ["kind/cleanup", "cleanup", "chore", "refactor"],
}

AREA_LABEL_MAP = {
    "area/engine": ["area/engine"],
    "area/cli": ["area/cli"],
    "area/webhooks": ["area/webhooks"],
    "area/api": ["area/api", "area/admission-policy"],
    "area/documentation": ["area/documentation", "documentation", "docs"],
    "area/reports": ["area/reports", "area/reports-controller"],
    "area/cleanup": ["area/cleanup", "area/cleanup-controller"],
    "area/image-verify": ["area/image-verify", "area/image-verification"],
    "area/cel": ["area/cel"],
    "area/helm": ["area/helm"],
    "area/background": ["area/background", "area/background-controller"],
    "area/controllers": ["area/controllers"],
}

# Reverse mapping: actual GitHub label -> classifier category
def _build_reverse_map(forward_map: dict[str, list[str]]) -> dict[str, str]:
    reverse = {}
    for category, labels in forward_map.items():
        for label in labels:
            reverse[label.lower()] = category
    return reverse

REVERSE_KIND_MAP = _build_reverse_map(KIND_LABEL_MAP)
REVERSE_AREA_MAP = _build_reverse_map(AREA_LABEL_MAP)


def normalize_label(label: str) -> tuple[str | None, str]:
    """Normalize a GitHub label to a classifier category.
    
    Args:
        label: The actual GitHub label string.
    
    Returns:
        (category, label_type) where label_type is 'kind', 'area', or 'other'
    """
    label_lower = label.lower()
    
    if label_lower in REVERSE_KIND_MAP:
        return REVERSE_KIND_MAP[label_lower], "kind"
    if label_lower in REVERSE_AREA_MAP:
        return REVERSE_AREA_MAP[label_lower], "area"
    
    return None, "other"


def extract_ground_truth(labels: list[str]) -> dict[str, str | None]:
    """Extract ground truth kind and area from a list of GitHub labels.
    
    Args:
        labels: List of label strings from a GitHub issue.
    
    Returns:
        {'kind': 'kind/bug' or None, 'area': 'area/engine' or None}
    """
    result: dict[str, str | None] = {"kind": None, "area": None}
    
    for label in labels:
        category, label_type = normalize_label(label)
        if category and label_type in result and result[label_type] is None:
            result[label_type] = category
    
    return result
