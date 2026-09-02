"""
Keeli v7.0 - Semantic Search and Relationship Mapping

This module provides intelligent semantic search capabilities that understand
the meaning and relationships between tasks, context, and project elements.

Core Philosophy: "I understand what you mean, not just what you say"
"""

import re
import math
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from keeli.llm_interface import LLMInterface


@dataclass
class SemanticNode:
    """A node in the semantic knowledge graph."""
    id: str
    content: str
    node_type: str  # task, context, knowledge, file, concept
    metadata: Dict[str, Any] = field(default_factory=dict)
    embeddings: Optional[List[float]] = None  # Placeholder for future ML embeddings
    relationships: Dict[str, float] = field(default_factory=dict)  # related_node_id -> strength
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Relationship:
    """A relationship between semantic nodes."""
    source_id: str
    target_id: str
    relationship_type: str  # depends_on, related_to, similar_to, part_of, references
    strength: float  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SemanticKnowledgeGraph:
    """
    Semantic knowledge graph that understands relationships between project elements.
    
    This goes beyond simple key-value storage by understanding:
    - Semantic similarity between concepts
    - Dependency relationships
    - Temporal patterns
    - Cross-references and associations
    """
    
    def __init__(self):
        self._nodes: Dict[str, SemanticNode] = {}
        self._relationships: List[Relationship] = []
        self._term_index: Dict[str, Set[str]] = defaultdict(set)  # term -> node_ids
        self._access_patterns: Dict[str, List[datetime]] = defaultdict(list)
        
    # ── Node Management ──
    
    def add_node(self, node: SemanticNode) -> None:
        """Add a node to the knowledge graph."""
        self._nodes[node.id] = node
        self._index_node_content(node)
    
    def _index_node_content(self, node: SemanticNode) -> None:
        """Index the content of a node for semantic search."""
        # Extract terms from content
        terms = self._extract_terms(node.content)
        for term in terms:
            self._term_index[term].add(node.id)
    
    def _extract_terms(self, content: str) -> List[str]:
        """Extract meaningful terms from content."""
        # Simple term extraction - in production, this would use NLP
        words = re.findall(r'\b[a-zA-Z]{3,}\b', content.lower())
        
        # Filter common stop words
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been', 'will', 'with', 'this', 'that', 'from', 'they', 'would', 'there', 'their', 'what', 'about', 'which', 'when', 'make', 'like', 'into', 'year', 'your', 'just', 'over', 'also', 'such', 'because', 'these', 'first', 'being', 'through', 'most', 'some', 'those', 'than', 'only', 'were', 'said', 'each', 'does', 'could', 'should', 'might', 'must'}
        
        return [word for word in words if word not in stop_words and len(word) > 2]
    
    def get_node(self, node_id: str) -> Optional[SemanticNode]:
        """Get a node by ID."""
        if node_id in self._nodes:
            self._nodes[node_id].last_accessed = datetime.now(timezone.utc)
            self._access_patterns[node_id].append(datetime.now(timezone.utc))
            return self._nodes[node_id]
        return None
    
    # ── Relationship Management ──
    
    def add_relationship(self, relationship: Relationship) -> None:
        """Add a relationship between nodes."""
        self._relationships.append(relationship)
        
        # Update node relationships
        if relationship.source_id in self._nodes:
            self._nodes[relationship.source_id].relationships[relationship.target_id] = relationship.strength
        if relationship.target_id in self._nodes:
            self._nodes[relationship.target_id].relationships[relationship.source_id] = relationship.strength
    
    def add_dependency(self, source_id: str, target_id: str, strength: float = 0.8) -> None:
        """Add a dependency relationship."""
        relationship = Relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type="depends_on",
            strength=strength
        )
        self.add_relationship(relationship)
    
    def add_similarity(self, source_id: str, target_id: str, strength: float = 0.6) -> None:
        """Add a similarity relationship."""
        relationship = Relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type="similar_to",
            strength=strength
        )
        self.add_relationship(relationship)
    
    def get_related_nodes(self, node_id: str, relationship_type: Optional[str] = None, min_strength: float = 0.3) -> List[SemanticNode]:
        """Get nodes related to a given node."""
        if node_id not in self._nodes:
            return []
        
        related = []
        for rel in self._relationships:
            if rel.source_id == node_id or rel.target_id == node_id:
                if relationship_type and rel.relationship_type != relationship_type:
                    continue
                if rel.strength < min_strength:
                    continue
                
                target_id = rel.target_id if rel.source_id == node_id else rel.source_id
                if target_id in self._nodes:
                    related.append(self._nodes[target_id])
        
        return related
    
    # ── Semantic Search ──
    
    def semantic_search(self, query: str, max_results: int = 10, node_type: Optional[str] = None) -> List[Tuple[SemanticNode, float]]:
        """
        Perform semantic search based on query terms.
        
        Returns list of (node, relevance_score) tuples.
        """
        query_terms = self._extract_terms(query)
        if not query_terms:
            return []
        
        # Calculate relevance scores for each node
        relevance_scores = []
        
        for node_id, node in self._nodes.items():
            if node_type and node.node_type != node_type:
                continue
            
            score = self._calculate_relevance(query_terms, node)
            if score > 0:
                relevance_scores.append((node, score))
        
        # Sort by relevance score
        relevance_scores.sort(key=lambda x: x[1], reverse=True)
        
        return relevance_scores[:max_results]
    
    def _calculate_relevance(self, query_terms: List[str], node: SemanticNode) -> float:
        """Calculate relevance score for a node given query terms."""
        node_terms = self._extract_terms(node.content)
        
        # Term frequency scoring
        matching_terms = set(query_terms) & set(node_terms)
        if not matching_terms:
            return 0.0
        
        # Simple TF-IDF-like scoring
        term_score = len(matching_terms) / len(query_terms)
        
        # Boost for exact phrase matches
        query_lower = " ".join(query_terms)
        content_lower = node.content.lower()
        if query_lower in content_lower:
            term_score *= 1.5
        
        # Boost for recently accessed nodes
        time_since_access = (datetime.now(timezone.utc) - node.last_accessed).total_seconds()
        recency_boost = max(0, 1.0 - (time_since_access / 3600))  # Decay over 1 hour
        
        # Boost for nodes with strong relationships
        relationship_boost = sum(node.relationships.values()) / max(len(node.relationships), 1)
        
        final_score = term_score * 0.6 + recency_boost * 0.2 + relationship_boost * 0.2
        
        return min(final_score, 1.0)
    
    # ── Concept Discovery ──
    
    def discover_concepts(self, min_frequency: int = 3) -> List[Tuple[str, int]]:
        """Discover frequently occurring concepts across the knowledge graph."""
        term_frequencies = Counter()
        
        for node in self._nodes.values():
            terms = self._extract_terms(node.content)
            for term in terms:
                term_frequencies[term] += 1
        
        # Filter by minimum frequency
        frequent_concepts = [(term, freq) for term, freq in term_frequencies.items() if freq >= min_frequency]
        frequent_concepts.sort(key=lambda x: x[1], reverse=True)
        
        return frequent_concepts[:20]
    
    def find_clusters(self) -> List[List[str]]:
        """Find clusters of related nodes."""
        if not self._nodes:
            return []
        
        # Simple clustering based on relationships
        clusters = []
        visited = set()
        
        for node_id in self._nodes:
            if node_id in visited:
                continue
            
            # Start new cluster
            cluster = [node_id]
            visited.add(node_id)
            
            # BFS to find related nodes
            queue = [node_id]
            while queue:
                current = queue.pop(0)
                related = self.get_related_nodes(current, min_strength=0.5)
                
                for related_node in related:
                    if related_node.id not in visited:
                        visited.add(related_node.id)
                        cluster.append(related_node.id)
                        queue.append(related_node.id)
            
            if len(cluster) > 1:
                clusters.append(cluster)
        
        return clusters
    
    # ── Knowledge Graph Statistics ──
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get statistics about the knowledge graph."""
        node_types = Counter(node.node_type for node in self._nodes.values())
        relationship_types = Counter(rel.relationship_type for rel in self._relationships)
        
        return {
            "total_nodes": len(self._nodes),
            "total_relationships": len(self._relationships),
            "node_types": dict(node_types),
            "relationship_types": dict(relationship_types),
            "indexed_terms": len(self._term_index),
            "avg_relationships_per_node": len(self._relationships) / max(len(self._nodes), 1),
            "most_connected_nodes": self._get_most_connected_nodes(5)
        }
    
    def _get_most_connected_nodes(self, limit: int) -> List[Tuple[str, int]]:
        """Get the most connected nodes."""
        connection_counts = []
        
        for node_id, node in self._nodes.items():
            connection_count = len(node.relationships)
            connection_counts.append((node_id, connection_count))
        
        connection_counts.sort(key=lambda x: x[1], reverse=True)
        return connection_counts[:limit]


class SemanticSearchInterface:
    """
    High-level interface for semantic search capabilities.
    
    This provides easy-to-use methods for LLMs to leverage semantic understanding.
    """
    
    def __init__(self, interface: LLMInterface):
        self.interface = interface
        self.knowledge_graph = SemanticKnowledgeGraph()
        self._index_existing_content()
    
    def _index_existing_content(self) -> None:
        """Index existing content from the Keeli engine."""
        try:
            # Index tasks
            tasks = self.interface.engine.list_tasks()
            for task in tasks:
                node = SemanticNode(
                    id=task['id'],
                    content=f"{task['title']} {task.get('description', '')}",
                    node_type="task",
                    metadata={"status": task['status'], "priority": task['priority']}
                )
                self.knowledge_graph.add_node(node)
                
                # Extract dependencies
                if task.get('depends_on') and task['depends_on'] != '—':
                    deps = re.findall(r'[Tt]-?\d+', task['depends_on'])
                    for dep in deps:
                        dep_id = dep.upper() if dep.startswith('T-') else f"T-{dep[2:]}"
                        self.knowledge_graph.add_dependency(task['id'], dep_id)
            
            # Index working memory if session exists
            if self.interface._auto_session_id:
                memory_items = self.interface.engine.working_memory_list(self.interface._auto_session_id)
                for item in memory_items:
                    node = SemanticNode(
                        id=f"memory:{item['key']}",
                        content=item['value'],
                        node_type="context",
                        metadata={"key": item['key'], "ttl": item['ttl_minutes']}
                    )
                    self.knowledge_graph.add_node(node)
        
        except Exception as e:
            print(f"Error indexing existing content: {e}")
    
    def search(self, query: str, context: str = "") -> str:
        """
        Perform semantic search and return natural language results.
        
        This is the main method LLMs should use for finding related content.
        """
        results = self.knowledge_graph.semantic_search(query, max_results=5)
        
        if not results:
            return f"🔍 No results found for '{query}'. Try different terms or add more context."
        
        response = f"🔍 **Search results for '{query}':**\n\n"
        
        for node, score in results:
            relevance = "🔥" if score > 0.8 else "⭐" if score > 0.5 else "💡"
            response += f"{relevance} **{node.id}** ({node.node_type}) - Relevance: {score:.2f}\n"
            response += f"   {node.content[:100]}...\n"
            
            # Show related information
            if node.metadata:
                metadata_str = ", ".join(f"{k}={v}" for k, v in node.metadata.items())
                response += f"   *{metadata_str}*\n"
            
            response += "\n"
        
        # Suggest related concepts
        concepts = self.knowledge_graph.discover_concepts(min_frequency=2)
        if concepts:
            response += f"**Related concepts:** {', '.join([c[0] for c in concepts[:5]])}\n"
        
        return response
    
    def find_related(self, item_id: str) -> str:
        """Find items related to a specific task or context item."""
        node = self.knowledge_graph.get_node(item_id)
        if not node:
            return f"❓ Item '{item_id}' not found in knowledge graph."
        
        related = self.knowledge_graph.get_related_nodes(item_id, min_strength=0.3)
        
        if not related:
            return f"📭 No strong relationships found for '{item_id}'."
        
        response = f"🔗 **Items related to {item_id}:**\n\n"
        
        for related_node in related:
            strength = "🔗" if related_node.relationships.get(item_id, 0) > 0.7 else "📍"
            response += f"{strength} **{related_node.id}** ({related_node.node_type})\n"
            response += f"   {related_node.content[:80]}...\n\n"
        
        return response
    
    def discover_patterns(self) -> str:
        """Discover and report patterns in the knowledge graph."""
        stats = self.knowledge_graph.get_graph_stats()
        concepts = self.knowledge_graph.discover_concepts()
        clusters = self.knowledge_graph.find_clusters()
        
        response = "🧠 **Knowledge Graph Patterns:**\n\n"
        
        response += f"📊 **Graph Statistics:**\n"
        response += f"   • Total nodes: {stats['total_nodes']}\n"
        response += f"   • Total relationships: {stats['total_relationships']}\n"
        response += f"   • Node types: {stats['node_types']}\n"
        response += f"   • Avg relationships per node: {stats['avg_relationships_per_node']:.2f}\n\n"
        
        if concepts:
            response += f"💡 **Frequent Concepts:**\n"
            for concept, freq in concepts[:10]:
                response += f"   • {concept} ({freq} occurrences)\n"
            response += "\n"
        
        if clusters:
            response += f"🔗 **Discovered Clusters:**\n"
            for i, cluster in enumerate(clusters[:5]):
                response += f"   • Cluster {i+1}: {', '.join(cluster[:3])}{'...' if len(cluster) > 3 else ''}\n"
            response += "\n"
        
        if stats['most_connected_nodes']:
            response += f"⭐ **Most Connected Nodes:**\n"
            for node_id, count in stats['most_connected_nodes']:
                response += f"   • {node_id} ({count} connections)\n"
        
        return response
    
    def add_context_to_graph(self, key: str, content: str, context_type: str = "context") -> str:
        """Add new context to the knowledge graph."""
        node = SemanticNode(
            id=f"{context_type}:{key}",
            content=content,
            node_type=context_type,
            metadata={"key": key}
        )
        self.knowledge_graph.add_node(node)
        
        # Try to find and create relationships with existing nodes
        self._auto_create_relationships(node)
        
        return f"✅ Added '{key}' to knowledge graph with {len(node.relationships)} auto-discovered relationships."
    
    def _auto_create_relationships(self, new_node: SemanticNode) -> None:
        """Automatically create relationships based on content similarity."""
        new_terms = set(self.knowledge_graph._extract_terms(new_node.content))
        
        for existing_id, existing_node in self.knowledge_graph._nodes.items():
            if existing_id == new_node.id:
                continue
            
            existing_terms = set(self.knowledge_graph._extract_terms(existing_node.content))
            
            # Calculate Jaccard similarity
            intersection = len(new_terms & existing_terms)
            union = len(new_terms | existing_terms)
            
            if union > 0:
                similarity = intersection / union
                if similarity > 0.3:  # Threshold for similarity
                    self.knowledge_graph.add_similarity(new_node.id, existing_id, strength=similarity)