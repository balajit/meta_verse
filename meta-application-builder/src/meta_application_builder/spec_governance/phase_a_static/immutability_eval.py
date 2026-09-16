from __future__ import annotations

import logging
from typing import List, Sequence

from meta_application_builder.spec_governance.schemas.det_schema import (
    DomainEntityTemplate,
    ImmutabilityTier,
)
from meta_application_builder.spec_governance.schemas.rfc7807_error import (
    ProblemDetails,
    ValidationErrorDetail,
)

logger = logging.getLogger("meta_application_builder.spec_governance.immutability_eval")


class GovernanceImmutabilityError(Exception):
    """Raised when an inheritance rule or immutability tier contract is violated."""

    def __init__(self, problem: ProblemDetails) -> None:
        super().__init__(problem.detail)
        self.problem = problem


class ImmutabilityEvaluator:
    """Evaluates parent vs child DET model differences to guarantee immutability contracts."""

    @classmethod
    def evaluate_inheritance(
        cls, parent: DomainEntityTemplate, child: DomainEntityTemplate, instance_uri: str
    ) -> None:
        """Direct parent-child pair immutability verification without stack recursion[cite: 6]."""
        logger.info("Evaluating immutability governance: parent='%s', child='%s'", parent.urn, child.urn)
        violations: List[ValidationErrorDetail] = []

        if parent.immutability_tier == ImmutabilityTier.FINAL:
            logger.error("Cannot extend FINAL parent specification URN: '%s'", parent.urn)
            violations.append(
                ValidationErrorDetail(
                    field_path="parent_urn",
                    code="MBR-005",
                    message=f"Parent specification '{parent.urn}' has FINAL immutability tier and cannot be extended.",
                )
            )

        # Validate parent attribute invariants
        for attr_name, parent_attr in parent.attributes.items():
            child_attr = child.attributes.get(attr_name)

            if parent_attr.immutability_tier in (ImmutabilityTier.FINAL, ImmutabilityTier.EXTENDABLE):
                if child_attr is None:
                    logger.error("Child removed non-overridable attribute '%s' from parent '%s'", attr_name, parent.urn)
                    violations.append(
                        ValidationErrorDetail(
                            field_path=f"attributes.{attr_name}",
                            code="MBR-006",
                            message=f"Attribute '{attr_name}' is '{parent_attr.immutability_tier}' in parent and cannot be deleted.",
                        )
                    )
                    continue

            if parent_attr.immutability_tier == ImmutabilityTier.FINAL:
                if parent_attr != child_attr:
                    logger.error("Child altered FINAL attribute '%s' inherited from '%s'", attr_name, parent.urn)
                    violations.append(
                        ValidationErrorDetail(
                            field_path=f"attributes.{attr_name}",
                            code="MBR-007",
                            message=f"Attribute '{attr_name}' is FINAL in parent and cannot be modified.",
                        )
                    )

        if violations:
            problem = ProblemDetails.create(
                status=422,
                title="Immutability Inheritance Violation",
                detail="Child template violates parent immutability tier governance specifications.",
                instance=instance_uri,
                invalid_params=violations,
            )
            raise GovernanceImmutabilityError(problem)

        logger.info("Immutability tier evaluation passed successfully for child: '%s'", child.urn)

    @classmethod
    def evaluate_inheritance_chain(
        cls, chain: Sequence[DomainEntityTemplate], instance_uri: str
    ) -> None:
        """Iteratively evaluates an ordered hierarchy chain (root to leaf) to eliminate stack recursion overhead."""
        if len(chain) < 2:
            return

        logger.info("Evaluating non-recursive inheritance chain of depth %d", len(chain))
        for idx in range(len(chain) - 1):
            parent = chain[idx]
            child = chain[idx + 1]
            cls.evaluate_inheritance(parent, child, instance_uri)