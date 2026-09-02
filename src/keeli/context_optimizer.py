"""
Keeli v7.0 - Context Window Monitoring and Optimization

This module provides intelligent context window management for LLMs.
It monitors token usage, optimizes context delivery, and provides intelligent
compression to maximize LLM effectiveness within token limits.

Core Philosophy: "Maximum value within minimum tokens"
"""

import tiktoken
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import deque


@dataclass
class ContextSnapshot:
    """A snapshot of context at a point in time."""
    timestamp: datetime
    total_tokens: int
    components: Dict[str, int]  # component_name -> token_count
    quality_score: float  # 0.0 to 1.0
    compression_ratio: float  # original_tokens / compressed_tokens


@dataclass
class ContextComponent:
    """A component of context (task, memory, knowledge, etc.)."""
    name: str
    content: str
    priority: float  # 0.0 to 1.0
    recency_score: float  # 0.0 to 1.0
    relevance_score: float  # 0.0 to 1.0
    token_count: int = 0
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ContextWindowMonitor:
    """
    Monitor and optimize context window usage for LLMs.
    
    This provides:
    - Token counting and budgeting
    - Context component prioritization
    - Intelligent compression
    - Usage pattern analysis
    """
    
    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")
        self._usage_history: deque = deque(maxlen=100)
        self._snapshots: List[ContextSnapshot] = []
        self._current_components: Dict[str, ContextComponent] = {}
        
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the appropriate encoding."""
        return len(self.encoding.encode(text))
    
    def add_component(self, name: str, content: str, priority: float = 0.5) -> None:
        """Add a context component with automatic token counting."""
        token_count = self.count_tokens(content)
        
        component = ContextComponent(
            name=name,
            content=content,
            priority=priority,
            recency_score=1.0,  # Fresh content
            relevance_score=0.5,  # Will be updated based on usage
            token_count=token_count
        )
        
        self._current_components[name] = component
    
    def update_component_priority(self, name: str, priority: float) -> None:
        """Update the priority of an existing component."""
        if name in self._current_components:
            self._current_components[name].priority = priority
            self._current_components[name].last_accessed = datetime.now(timezone.utc)
    
    def get_total_tokens(self) -> int:
        """Get total token count of all components."""
        return sum(comp.token_count for comp in self._current_components.values())
    
    def is_over_budget(self) -> bool:
        """Check if current context exceeds token budget."""
        return self.get_total_tokens() > self.max_tokens
    
    def get_optimized_context(self, target_tokens: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Get optimized context within token budget.
        
        Returns (optimized_content, metadata) tuple.
        """
        target = target_tokens or self.max_tokens
        
        if not self._current_components:
            return "", {"tokens": 0, "components": 0}
        
        # Sort components by composite score
        scored_components = self._score_components()
        
        # Select components until budget is reached
        selected_components = []
        current_tokens = 0
        
        for component, score in scored_components:
            if current_tokens + component.token_count <= target:
                selected_components.append(component)
                current_tokens += component.token_count
            else:
                # Try to include a partial version
                remaining_tokens = target - current_tokens
                if remaining_tokens > 100:  # Only if meaningful space remains
                    partial_content = self._compress_to_tokens(component.content, remaining_tokens)
                    if partial_content:
                        partial_component = ContextComponent(
                            name=component.name + " (partial)",
                            content=partial_content,
                            priority=component.priority,
                            recency_score=component.recency_score,
                            relevance_score=component.relevance_score,
                            token_count=remaining_tokens
                        )
                        selected_components.append(partial_component)
                        current_tokens += remaining_tokens
                break
        
        # Build optimized context
        optimized_content = self._build_context_string(selected_components)
        
        metadata = {
            "tokens": current_tokens,
            "components": len(selected_components),
            "total_available": len(self._current_components),
            "compression_ratio": self.get_total_tokens() / max(current_tokens, 1),
            "quality_score": self._calculate_quality_score(selected_components)
        }
        
        # Record snapshot
        self._record_snapshot(current_tokens, metadata)
        
        return optimized_content, metadata
    
    def _score_components(self) -> List[Tuple[ContextComponent, float]]:
        """Score components based on priority, recency, and relevance."""
        scored = []
        
        for component in self._current_components.values():
            # Update recency score based on time since last access
            time_since_access = (datetime.now(timezone.utc) - component.last_accessed).total_seconds()
            component.recency_score = max(0, 1.0 - (time_since_access / 3600))  # Decay over 1 hour
            
            # Composite score
            composite_score = (
                component.priority * 0.5 +
                component.recency_score * 0.3 +
                component.relevance_score * 0.2
            )
            
            scored.append((component, composite_score))
        
        # Sort by composite score (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored
    
    def _compress_to_tokens(self, content: str, target_tokens: int) -> str:
        """Compress content to fit within target token limit."""
        if self.count_tokens(content) <= target_tokens:
            return content
        
        # Simple compression: truncate intelligently by lines
        lines = content.split('\n')
        compressed_lines = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self.count_tokens(line)
            if current_tokens + line_tokens <= target_tokens - 50:  # Leave buffer
                compressed_lines.append(line)
                current_tokens += line_tokens
            else:
                break
        
        result = '\n'.join(compressed_lines)
        
        # Edge case: if no lines fit (first line too long), fall back to character-based truncation
        if not result:
            # Use character-level truncation: roughly 4 chars per token
            max_chars = (target_tokens - 50) * 4
            result = content[:max_chars]
            if len(result) < len(content):
                result += "\n... [truncated]"
        
        if result and self.count_tokens(result) < target_tokens:
            result += "\n... [content truncated to fit token budget]"
        
        return result
    
    def _build_context_string(self, components: List[ContextComponent]) -> str:
        """Build a formatted context string from components."""
        if not components:
            return ""
        
        context_parts = []
        for component in components:
            context_parts.append(f"## {component.name}\n{component.content}")
        
        return "\n\n".join(context_parts)
    
    def _calculate_quality_score(self, selected_components: List[ContextComponent]) -> float:
        """Calculate quality score of selected components."""
        if not selected_components:
            return 0.0
        
        total_priority = sum(comp.priority for comp in selected_components)
        max_possible_priority = len(selected_components)  # Perfect score would be all 1.0
        
        return min(total_priority / max(max_possible_priority, 1), 1.0)
    
    def _record_snapshot(self, token_count: int, metadata: Dict[str, Any]) -> None:
        """Record a context snapshot for analysis."""
        snapshot = ContextSnapshot(
            timestamp=datetime.now(timezone.utc),
            total_tokens=token_count,
            components={comp.name: comp.token_count for comp in self._current_components.values()},
            quality_score=metadata.get("quality_score", 0.0),
            compression_ratio=metadata.get("compression_ratio", 1.0)
        )
        
        self._snapshots.append(snapshot)
        
        # Keep only last 50 snapshots
        if len(self._snapshots) > 50:
            self._snapshots = self._snapshots[-50:]
    
    def get_usage_statistics(self) -> Dict[str, Any]:
        """Get statistics about context window usage."""
        if not self._snapshots:
            return {
                "total_snapshots": 0,
                "avg_tokens": 0,
                "avg_quality": 0.0,
                "avg_compression": 1.0
            }
        
        total_tokens = sum(s.total_tokens for s in self._snapshots)
        avg_tokens = total_tokens / len(self._snapshots)
        
        total_quality = sum(s.quality_score for s in self._snapshots)
        avg_quality = total_quality / len(self._snapshots)
        
        total_compression = sum(s.compression_ratio for s in self._snapshots)
        avg_compression = total_compression / len(self._snapshots)
        
        return {
            "total_snapshots": len(self._snapshots),
            "avg_tokens": avg_tokens,
            "avg_quality": avg_quality,
            "avg_compression": avg_compression,
            "current_components": len(self._current_components),
            "current_total_tokens": self.get_total_tokens(),
            "budget_utilization": self.get_total_tokens() / self.max_tokens
        }
    
    def suggest_optimizations(self) -> List[str]:
        """Suggest optimizations based on usage patterns."""
        suggestions = []
        
        current_usage = self.get_total_tokens()
        budget_ratio = current_usage / self.max_tokens
        
        if budget_ratio > 0.9:
            suggestions.append("⚠️ Token budget nearly exhausted. Consider removing low-priority components.")
        elif budget_ratio > 0.7:
            suggestions.append("📊 Token usage is high. Monitor component priorities.")
        
        # Check for large components
        large_components = [
            (name, comp.token_count) 
            for name, comp in self._current_components.items() 
            if comp.token_count > 500
        ]
        
        if large_components:
            suggestions.append(f"📦 Large components detected: {', '.join([f'{name} ({tokens} tokens)' for name, tokens in large_components])}")
        
        # Check for low-priority components
        low_priority = [
            name for name, comp in self._current_components.items() 
            if comp.priority < 0.3
        ]
        
        if low_priority:
            suggestions.append(f"🔻 Low-priority components: {', '.join(low_priority)}. Consider removing if not needed.")
        
        # Quality score analysis
        stats = self.get_usage_statistics()
        if stats["avg_quality"] < 0.6:
            suggestions.append("📉 Context quality score is low. Review component priorities and relevance.")
        
        if not suggestions:
            suggestions.append("✅ Context usage looks optimal!")
        
        return suggestions


class IntelligentContextBuilder:
    """
    Intelligent context builder that works with the LLM interface.
    
    This provides smart context assembly based on LLM needs and patterns.
    """
    
    def __init__(self, max_tokens: int = 4000):
        self.monitor = ContextWindowMonitor(max_tokens)
        self._learning_patterns: Dict[str, float] = {}  # pattern -> effectiveness_score
        
    def build_context_for_request(self, request: str, available_context: Dict[str, str]) -> Tuple[str, Dict[str, Any]]:
        """
        Build optimized context for a specific request.
        
        This analyzes the request and selects the most relevant context components.
        """
        # Clear previous components
        self.monitor._current_components.clear()
        
        # Analyze request to determine component priorities
        request_lower = request.lower()
        
        # Add components with intelligent priorities
        for name, content in available_context.items():
            priority = self._calculate_component_priority(name, content, request_lower)
            self.monitor.add_component(name, content, priority)
        
        # Get optimized context
        optimized_content, metadata = self.monitor.get_optimized_context()
        
        return optimized_content, metadata
    
    def _calculate_component_priority(self, name: str, content: str, request: str) -> float:
        """Calculate priority of a component based on request."""
        request_terms = set(request.split())
        content_terms = set(content.lower().split())
        
        # Simple term overlap for relevance
        overlap = len(request_terms & content_terms)
        relevance = min(overlap / max(len(request_terms), 1), 1.0)
        
        # Base priority based on component type
        base_priority = 0.5
        if "task" in name.lower():
            base_priority = 0.7
        elif "active" in name.lower():
            base_priority = 0.8
        elif "memory" in name.lower():
            base_priority = 0.6
        elif "knowledge" in name.lower():
            base_priority = 0.5
        
        # Combine base priority with relevance
        final_priority = base_priority * 0.6 + relevance * 0.4
        
        return min(final_priority, 1.0)
    
    def get_context_health_report(self) -> str:
        """Get a comprehensive context health report."""
        stats = self.monitor.get_usage_statistics()
        suggestions = self.monitor.suggest_optimizations()
        
        report = f"""
📊 **Context Window Health Report**

**Usage Statistics:**
• Current tokens: {stats['current_total_tokens']} / {self.monitor.max_tokens}
• Budget utilization: {stats['budget_utilization']:.1%}
• Active components: {stats['current_components']}
• Average quality score: {stats['avg_quality']:.2f}
• Average compression ratio: {stats['avg_compression']:.2f}x

**Optimization Suggestions:**
{chr(10).join(f"• {s}" for s in suggestions)}

**Recommendations:**
• Aim for budget utilization between 60-80%
• Keep quality score above 0.7
• Remove large, low-priority components
• Update component priorities based on current task
"""
        return report