"""
Keeli v7.0 - Workflow Templates for Common LLM Tasks

This module provides pre-built workflow templates for common LLM tasks.
These templates encapsulate best practices and optimal workflows for specific scenarios.

Core Philosophy: "Learn once, apply everywhere - templates for efficiency"
"""

from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class TaskComplexity(Enum):
    """Complexity levels for tasks."""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class TaskDomain(Enum):
    """Domains for tasks."""
    FRONTEND = "frontend"
    BACKEND = "backend"
    DEVOPS = "devops"
    DATA = "data"
    SECURITY = "security"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


@dataclass
class WorkflowStep:
    """A single step in a workflow template."""
    step_number: int
    title: str
    description: str
    estimated_time: str  # e.g., "5-10 minutes"
    required: bool = True
    dependencies: List[int] = field(default_factory=list)  # step numbers this depends on
    substeps: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    common_pitfalls: List[str] = field(default_factory=list)


@dataclass
class WorkflowTemplate:
    """A complete workflow template."""
    template_id: str
    name: str
    description: str
    domain: TaskDomain
    complexity: TaskComplexity
    estimated_total_time: str
    steps: List[WorkflowStep]
    prerequisites: List[str] = field(default_factory=list)
    deliverables: List[str] = field(default_factory=list)
    related_templates: List[str] = field(default_factory=list)


class WorkflowTemplateLibrary:
    """
    Library of pre-built workflow templates for common LLM tasks.
    
    These templates provide structured guidance for recurring task types.
    """
    
    def __init__(self):
        self._templates: Dict[str, WorkflowTemplate] = {}
        self._initialize_templates()
    
    def _initialize_templates(self) -> None:
        """Initialize the template library with common workflows."""
        
        # Bug Fixing Template
        bug_fix_template = WorkflowTemplate(
            template_id="bug_fix_simple",
            name="Simple Bug Fix",
            description="Template for fixing straightforward bugs with clear reproduction steps",
            domain=TaskDomain.GENERAL,
            complexity=TaskComplexity.SIMPLE,
            estimated_total_time="15-30 minutes",
            steps=[
                WorkflowStep(
                    step_number=1,
                    title="Understand the Bug",
                    description="Analyze the bug report and understand the expected vs actual behavior",
                    estimated_time="2-5 minutes",
                    substeps=[
                        "Read the bug description carefully",
                        "Identify the expected behavior",
                        "Understand the actual behavior",
                        "Check for error messages or stack traces"
                    ],
                    success_criteria=["Bug is clearly understood", "Reproduction steps are identified"],
                    common_pitfalls=["Skipping error logs", "Not verifying bug exists"]
                ),
                WorkflowStep(
                    step_number=2,
                    title="Locate the Issue",
                    description="Find the specific code location causing the bug",
                    estimated_time="5-10 minutes",
                    dependencies=[1],
                    substeps=[
                        "Search for relevant code files",
                        "Use error messages to locate the issue",
                        "Set breakpoints if needed",
                        "Trace the code execution path"
                    ],
                    success_criteria=["Specific file and line identified", "Root cause understood"],
                    common_pitfalls=["Looking in wrong files", "Missing related code"]
                ),
                WorkflowStep(
                    step_number=3,
                    title="Implement Fix",
                    description="Apply the minimal fix to resolve the issue",
                    estimated_time="5-10 minutes",
                    dependencies=[2],
                    substeps=[
                        "Make the minimal code change",
                        "Don't refactor unrelated code",
                        "Add comments if the fix is non-obvious",
                        "Test the fix locally"
                    ],
                    success_criteria=["Bug is resolved", "No new issues introduced"],
                    common_pitfalls=["Over-engineering the fix", "Breaking existing functionality"]
                ),
                WorkflowStep(
                    step_number=4,
                    title="Validate and Document",
                    description="Test thoroughly and document the changes",
                    estimated_time="3-5 minutes",
                    dependencies=[3],
                    substeps=[
                        "Test the original bug scenario",
                        "Test related functionality",
                        "Add/update tests if needed",
                        "Document the fix in commit message"
                    ],
                    success_criteria=["All tests pass", "Changes are documented"],
                    common_pitfalls=["Skipping validation", "Poor documentation"]
                )
            ],
            prerequisites=["Bug report with reproduction steps", "Access to codebase"],
            deliverables=["Fixed code", "Updated tests", "Documentation"],
            related_templates=["bug_fix_complex", "debugging_investigation"]
        )
        
        # Feature Development Template
        feature_template = WorkflowTemplate(
            template_id="feature_development_moderate",
            name="Feature Development",
            description="Template for developing new features with proper planning and implementation",
            domain=TaskDomain.GENERAL,
            complexity=TaskComplexity.MODERATE,
            estimated_total_time="1-3 hours",
            steps=[
                WorkflowStep(
                    step_number=1,
                    title="Requirements Analysis",
                    description="Understand what needs to be built and why",
                    estimated_time="10-20 minutes",
                    substeps=[
                        "Clarify feature requirements",
                        "Identify user stories",
                        "Define acceptance criteria",
                        "Consider edge cases"
                    ],
                    success_criteria=["Clear requirements documented", "Acceptance criteria defined"],
                    common_pitfalls=["Ambiguous requirements", "Missing edge cases"]
                ),
                WorkflowStep(
                    step_number=2,
                    title="Design and Planning",
                    description="Plan the implementation approach",
                    estimated_time="15-30 minutes",
                    dependencies=[1],
                    substeps=[
                        "Design the solution architecture",
                        "Identify components to modify/create",
                        "Plan the implementation order",
                        "Consider integration points"
                    ],
                    success_criteria=["Implementation plan created", "Technical approach decided"],
                    common_pitfalls=["Over-complicating design", "Missing dependencies"]
                ),
                WorkflowStep(
                    step_number=3,
                    title="Core Implementation",
                    description="Implement the main functionality",
                    estimated_time="30-60 minutes",
                    dependencies=[2],
                    substeps=[
                        "Set up the basic structure",
                        "Implement core logic",
                        "Add error handling",
                        "Follow code conventions"
                    ],
                    success_criteria=["Core functionality works", "Code follows conventions"],
                    common_pitfalls=["Skipping error handling", "Not following conventions"]
                ),
                WorkflowStep(
                    step_number=4,
                    title="Integration and Testing",
                    description="Integrate with existing code and test thoroughly",
                    estimated_time="20-40 minutes",
                    dependencies=[3],
                    substeps=[
                        "Integrate with existing components",
                        "Write comprehensive tests",
                        "Test edge cases",
                        "Performance check if needed"
                    ],
                    success_criteria=["All tests pass", "Integration verified"],
                    common_pitfalls["Insufficient testing", "Integration issues"]
                ),
                WorkflowStep(
                    step_number=5,
                    title="Documentation and Cleanup",
                    description="Document the feature and clean up",
                    estimated_time="10-15 minutes",
                    dependencies=[4],
                    substeps=[
                        "Update relevant documentation",
                        "Add code comments",
                        "Clean up temporary code",
                        "Update API docs if needed"
                    ],
                    success_criteria=["Documentation updated", "Code is clean"],
                    common_pitfalls["Skipping documentation", "Leaving debug code"]
                )
            ],
            prerequisites=["Clear feature requirements", "Development environment setup"],
            deliverables=["Working feature", "Tests", "Documentation"],
            related_templates=["feature_development_complex", "api_development"]
        )
        
        # Code Review Template
        code_review_template = WorkflowTemplate(
            template_id="code_review_standard",
            name="Standard Code Review",
            description="Template for conducting thorough code reviews",
            domain=TaskDomain.GENERAL,
            complexity=TaskComplexity.SIMPLE,
            estimated_total_time="15-30 minutes",
            steps=[
                WorkflowStep(
                    step_number=1,
                    title="Understand Context",
                    description="Understand what the code changes are meant to accomplish",
                    estimated_time="3-5 minutes",
                    substeps=[
                        "Read the PR description",
                        "Understand the problem being solved",
                        "Review related issues or tickets",
                        "Check the scope of changes"
                    ],
                    success_criteria=["Purpose of changes understood", "Scope known"],
                    common_pitfalls["Skipping context", "Missing the big picture"]
                ),
                WorkflowStep(
                    step_number=2,
                    title="Code Quality Review",
                    description="Review code for quality, style, and best practices",
                    estimated_time="5-10 minutes",
                    dependencies=[1],
                    substeps=[
                        "Check code style and conventions",
                        "Look for potential bugs",
                        "Assess performance implications",
                        "Review error handling"
                    ],
                    success_criteria=["Code quality assessed", "Issues identified"],
                    common_pitfalls=["Being too pedantic", "Missing important issues"]
                ),
                WorkflowStep(
                    step_number=3,
                    title="Functionality Review",
                    description="Verify the code does what it's supposed to do",
                    estimated_time="5-10 minutes",
                    dependencies=[1],
                    substeps=[
                        "Verify logic correctness",
                        "Check edge cases",
                        "Assess test coverage",
                        "Review integration points"
                    ],
                    success_criteria=["Functionality verified", "Edge cases considered"],
                    common_pitfalls["Not testing mentally", "Missing edge cases"]
                ),
                WorkflowStep(
                    step_number=4,
                    title="Provide Feedback",
                    description="Provide clear, actionable feedback",
                    estimated_time="2-5 minutes",
                    dependencies=[2, 3],
                    substeps=[
                        "Group related comments",
                        "Provide specific suggestions",
                        "Explain the 'why' for changes",
                        "Balance positive and constructive feedback"
                    ],
                    success_criteria=["Clear feedback provided", "Actionable suggestions given"],
                    common_pitfalls["Vague comments", "Being overly critical"]
                )
            ],
            prerequisites=["Access to code changes", "Understanding of codebase"],
            deliverables=["Code review comments", "Approval or changes requested"],
            related_templates=["security_review", "performance_review"]
        )
        
        # Add templates to library
        self._templates[bug_fix_template.template_id] = bug_fix_template
        self._templates[feature_template.template_id] = feature_template
        self._templates[code_review_template.template_id] = code_review_template
        
        # Add more specialized templates
        self._add_specialized_templates()
    
    def _add_specialized_templates(self) -> None:
        """Add specialized templates for specific domains."""
        
        # API Development Template
        api_template = WorkflowTemplate(
            template_id="api_development",
            name="API Development",
            description="Template for developing RESTful API endpoints",
            domain=TaskDomain.BACKEND,
            complexity=TaskComplexity.MODERATE,
            estimated_total_time="2-4 hours",
            steps=[
                WorkflowStep(
                    step_number=1,
                    title="API Design",
                    description="Design the API endpoints and data structures",
                    estimated_time="20-30 minutes",
                    substeps=[
                        "Define endpoint routes and methods",
                        "Design request/response schemas",
                        "Plan error responses",
                        "Consider authentication/authorization"
                    ],
                    success_criteria=["API contract defined", "Schemas designed"],
                    common_pitfalls=["Inconsistent naming", "Missing error cases"]
                ),
                WorkflowStep(
                    step_number=2,
                    title="Implementation",
                    description="Implement the API endpoints",
                    estimated_time="60-90 minutes",
                    dependencies=[1],
                    substeps=[
                        "Set up routing",
                        "Implement request handlers",
                        "Add validation",
                        "Implement business logic"
                    ],
                    success_criteria=["Endpoints implemented", "Validation working"],
                    common_pitfalls["Missing validation", "Poor error handling"]
                ),
                WorkflowStep(
                    step_number=3,
                    title="Testing and Documentation",
                    description="Test the API and create documentation",
                    estimated_time="30-40 minutes",
                    dependencies=[2],
                    substeps=[
                        "Write unit tests",
                        "Write integration tests",
                        "Create API documentation",
                        "Test with example requests"
                    ],
                    success_criteria=["Tests pass", "Documentation complete"],
                    common_pitfalls["Insufficient testing", "Missing documentation"]
                )
            ],
            prerequisites=["API framework knowledge", "Backend development environment"],
            deliverables=["Working API", "Tests", "API documentation"],
            related_templates=["feature_development_moderate", "database_integration"]
        )
        
        self._templates[api_template.template_id] = api_template
    
    def get_template(self, template_id: str) -> Optional[WorkflowTemplate]:
        """Get a template by ID."""
        return self._templates.get(template_id)
    
    def list_templates(self, domain: Optional[TaskDomain] = None, complexity: Optional[TaskComplexity] = None) -> List[WorkflowTemplate]:
        """List available templates, optionally filtered by domain or complexity."""
        templates = list(self._templates.values())
        
        if domain:
            templates = [t for t in templates if t.domain == domain]
        
        if complexity:
            templates = [t for t in templates if t.complexity == complexity]
        
        return templates
    
    def find_matching_template(self, natural_request: str) -> Optional[WorkflowTemplate]:
        """Find the best matching template based on natural language request."""
        request_lower = natural_request.lower()
        
        # Simple keyword matching
        if "bug" in request_lower or "fix" in request_lower:
            return self._templates.get("bug_fix_simple")
        
        if "feature" in request_lower or "implement" in request_lower or "add" in request_lower:
            return self._templates.get("feature_development_moderate")
        
        if "api" in request_lower or "endpoint" in request_lower:
            return self._templates.get("api_development")
        
        if "review" in request_lower or "pr" in request_lower:
            return self._templates.get("code_review_standard")
        
        return None
    
    def format_template_for_display(self, template: WorkflowTemplate) -> str:
        """Format a template for display to LLMs."""
        output = f"""
📋 **Template: {template.name}**
**Domain:** {template.domain.value} | **Complexity:** {template.complexity.value}
**Estimated Time:** {template.estimated_total_time}

**Description:**
{template.description}

**Prerequisites:**
{chr(10).join(f"• {p}" for p in template.prerequisites) if template.prerequisites else "None"}

**Steps:**
"""
        
        for step in template.steps:
            output += f"""
**Step {step.step_number}: {step.title}** ({step.estimated_time})
{step.description}

• Substeps:
{chr(10).join(f"  - {s}" for s in step.substeps) if step.substeps else "  None"}
• Success Criteria:
{chr(10).join(f"  ✓ {c}" for c in step.success_criteria) if step.success_criteria else "  None"}
• Common Pitfalls:
{chr(10).join(f"  ⚠️ {p}" for p in step.common_pitfalls) if step.common_pitfalls else "  None"}
"""
        
        output += f"""
**Deliverables:**
{chr(10).join(f"• {d}" for d in template.deliverables) if template.deliverables else "None"}

**Related Templates:**
{chr(10).join(f"• {t}" for t in template.related_templates) if template.related_templates else "None"}
"""
        
        return output