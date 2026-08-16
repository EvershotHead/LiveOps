"""提示词版本注册表。"""

from . import v1

REGISTRY: dict[str, str] = {
    "annotate": v1.ANNOTATE_VERSION,
    "report_claims": v1.REPORT_CLAIMS_VERSION,
}

__all__ = ["REGISTRY", "v1"]
