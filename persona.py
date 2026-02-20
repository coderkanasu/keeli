#!/usr/bin/env python3
import os
import argparse
from pathlib import Path

COPILOT_INSTRUCTIONS = """# GitHub Copilot Custom Instructions

## Core Philosophy
You are operating under a strict Three-Persona Architecture. Your primary goals are security governance, responsible AI use, and zero hallucination. You must act as a team of three distinct personas to complete any task.

## The Three Personas

### 1. @architect
- **Role:** System design, strategy, and task breakdown.
- **Responsibilities:** Thoroughly dissect the user's request. Create a step-by-step strategy and actionable tasks for the @developer. Ensure the architecture aligns with the project's goals and security standards.

### 2. @developer
- **Role:** Execution and implementation.
- **Responsibilities:** Execute the tasks defined by the @architect efficiently. Ask clarifying questions about programming choices or project specifics. If the scope is large or ambiguous, STOP and engage the human-in-the-loop for clarification before proceeding.

### 3. @security
- **Role:** Security governance and responsible AI.
- **Responsibilities:** Review all proposed architectures and code for vulnerabilities, compliance, and responsible AI practices. Ensure no hallucinations are introduced into the codebase.

## Workflow Rules
1. **Task Initiation:** Every task must start with the @architect dissecting the requirements and creating a plan.
2. **Handoff:** The @architect hands the plan over to the @developer for execution.
3. **Review:** The @security persona must review the implementation for safety and governance.
4. **Human-in-the-Loop:** If at any point the scope is large or requirements are unclear, the @developer must ask the user for clarification.

## Memory and Logging
You must maintain a continuous audit trail and project state:
- **docs/project.md:** If you learn new information about the project (e.g., tech stack, architecture choices) or if a new decision is made, you MUST update `docs/project.md`.
- **docs/tasks.md:** The @architect must create and track all tasks here. The @developer must update the status of tasks as they are worked on and completed.
- **docs/ai_log.md:** For audit purposes, log every action, reasoning, and new piece of information you process into `docs/ai_log.md`.
"""

def init_persona(force=False):
    print("Initializing Persona CLI...")
    
    try:
        # Create .github directory
        github_dir = Path(".github")
        github_dir.mkdir(exist_ok=True)
        
        # Create docs directory
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        
        # Create copilot-instructions.md
        instructions_file = github_dir / "copilot-instructions.md"
        if not instructions_file.exists() or force:
            instructions_file.write_text(COPILOT_INSTRUCTIONS)
            print(f"✅ {'Overwrote' if force and instructions_file.exists() else 'Created'} {instructions_file}")
        else:
            print(f"⚠️ {instructions_file} already exists. Use --force to overwrite.")
            
        # Create project.md
        project_file = docs_dir / "project.md"
        if not project_file.exists() or force:
            project_file.write_text("# Project Documentation\n\nThis file contains the current state, architecture decisions, and learned information about the project.\n")
            print(f"✅ {'Overwrote' if force and project_file.exists() else 'Created'} {project_file}")
        else:
            print(f"⚠️ {project_file} already exists. Use --force to overwrite.")
            
        # Create tasks.md
        tasks_file = docs_dir / "tasks.md"
        if not tasks_file.exists() or force:
            tasks_file.write_text("# Task Tracker\n\nThis file tracks all tasks created by the @architect and executed by the @developer.\n\n## Backlog\n\n## In Progress\n\n## Completed\n")
            print(f"✅ {'Overwrote' if force and tasks_file.exists() else 'Created'} {tasks_file}")
        else:
            print(f"⚠️ {tasks_file} already exists. Use --force to overwrite.")
            
        # Create ai_log.md
        ai_log_file = docs_dir / "ai_log.md"
        if not ai_log_file.exists() or force:
            ai_log_file.write_text("# AI Audit Log\n\nThis file logs all AI actions, reasoning, and new information processed for audit purposes.\n")
            print(f"✅ {'Overwrote' if force and ai_log_file.exists() else 'Created'} {ai_log_file}")
        else:
            print(f"⚠️ {ai_log_file} already exists. Use --force to overwrite.")
            
        # Update .gitignore
        gitignore_file = Path(".gitignore")
        gitignore_entry = "\n# Persona CLI\ndocs/ai_log.md\n"
        if gitignore_file.exists():
            content = gitignore_file.read_text()
            if "docs/ai_log.md" not in content:
                with gitignore_file.open("a") as f:
                    f.write(gitignore_entry)
                print(f"✅ Added docs/ai_log.md to {gitignore_file}")
        else:
            gitignore_file.write_text(gitignore_entry.lstrip())
            print(f"✅ Created {gitignore_file} and ignored docs/ai_log.md")
            
        print("\n🎉 Initialization complete! GitHub Copilot is now configured with the Three-Persona Architecture.")
    except PermissionError as e:
        print(f"\n❌ Permission Error: Unable to create files or directories. Please check your permissions.\nDetails: {e}")
    except Exception as e:
        print(f"\n❌ An unexpected error occurred during initialization.\nDetails: {e}")

def status_persona():
    print("Checking Persona CLI status...\n")
    
    files_to_check = [
        Path(".github/copilot-instructions.md"),
        Path("docs/project.md"),
        Path("docs/tasks.md"),
        Path("docs/ai_log.md")
    ]
    
    all_exist = True
    for file_path in files_to_check:
        if file_path.exists():
            print(f"✅ Found: {file_path}")
        else:
            print(f"❌ Missing: {file_path}")
            all_exist = False
            
    print("\nStatus: " + ("🟢 Healthy" if all_exist else "🔴 Incomplete (Run 'persona init' to fix)"))

def clear_log():
    ai_log_file = Path("docs/ai_log.md")
    if ai_log_file.exists():
        ai_log_file.write_text("# AI Audit Log\n\nThis file logs all AI actions, reasoning, and new information processed for audit purposes.\n")
        print(f"✅ Cleared {ai_log_file}")
    else:
        print(f"⚠️ {ai_log_file} does not exist. Run 'persona init' first.")

def main():
    parser = argparse.ArgumentParser(description="Persona CLI - Enforce a Three-Persona Architecture for AI Agents.")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize the .github Copilot instructions and logging files.")
    init_parser.add_argument("-f", "--force", action="store_true", help="Force overwrite existing files.")
    
    # Status command
    subparsers.add_parser("status", help="Check if the Persona architecture files are present.")
    
    # Clear log command
    subparsers.add_parser("clear-log", help="Clear the contents of the AI audit log.")
    
    args = parser.parse_args()
    
    if args.command == "init":
        init_persona(force=args.force)
    elif args.command == "status":
        status_persona()
    elif args.command == "clear-log":
        clear_log()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
