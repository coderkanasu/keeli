import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.keeli.workflow_templates import WorkflowTemplateLibrary
from src.keeli.workflow_orchestrator import WorkflowOrchestrator, WorkflowStage


def test_data_integrity_template_matching():
    library = WorkflowTemplateLibrary()

    template = library.find_matching_template("Fix missing sector data integrity issue in scan results")

    assert template is not None
    assert template.template_id == "data_integrity_remediation"
    assert len(template.steps) == 6
    assert template.steps[0].title == "Baseline Integrity"
    assert template.steps[-1].title == "Instrument Prevention"


def test_bug_fixing_guidance_enforces_evidence_loop():
    orchestrator = WorkflowOrchestrator(interface=None)

    context_guidance = orchestrator._bug_fixing_guidance(WorkflowStage.CONTEXT_GATHERING)
    validation_guidance = orchestrator._bug_fixing_guidance(WorkflowStage.VALIDATION)

    assert "Baseline the Problem" in context_guidance
    assert "keeli_memory set" in context_guidance
    assert "Re-run the original baseline check" in validation_guidance
    assert "downstream outputs or consumers" in validation_guidance