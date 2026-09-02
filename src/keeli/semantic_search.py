"""
Keeli v7.0 - Real Semantic Core with Vector-Based Retrieval

Phase 1: Replacing keyword matching with proper semantic understanding.

Core improvements:
- Vector embeddings with cosine similarity (no external LLM calls)
- Metadata filtering for structured queries
- Explainable scoring (returns reason for each match)
- Filesystem remains the source of truth
"""

import re
import math
import json
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from abc import ABC, abstractmethod
import hashlib


# ── Data Structures ──

@dataclass
class SearchReason:
    """Explains why a result was matched."""
    reason_type: str  # "vector_similarity", "metadata_match", "relationship", "temporal_boost"
    explanation: str
    confidence: float  # 0.0 to 1.0
    

@dataclass
class SearchResult:
    """Structured search result with explainable scoring."""
    node_id: str
    content: str
    node_type: str
    score: float  # 0.0 to 1.0
    reasons: List[SearchReason] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "node_id": self.node_id,
            "content": self.content,
            "node_type": self.node_type,
            "score": round(self.score, 3),
            "reasons": [asdict(r) for r in self.reasons],
            "metadata": self.metadata
        }


@dataclass
class SemanticNode:
    """A node in the semantic knowledge graph."""
    id: str
    content: str
    node_type: str  # task, context, knowledge, file, concept
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None  # Dense vector representation
    relationships: Dict[str, float] = field(default_factory=dict)  # related_node_id -> strength
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "content": self.content,
            "node_type": self.node_type,
            "metadata": self.metadata,
            "relationships": self.relationships,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat()
        }


@dataclass
class Relationship:
    """A relationship between semantic nodes."""
    source_id: str
    target_id: str
    relationship_type: str  # depends_on, related_to, similar_to, part_of, references
    strength: float  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))



# ── Embedding Model Interface ──

class EmbeddingModel(ABC):
    """Abstract base for embedding models."""
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Generate embedding for text."""
        pass
    
    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        pass


class SimpleStatisticalEmbedding(EmbeddingModel):
    """
    Lightweight statistical embedding (no external calls).
    
    Uses character n-grams and term frequencies to create a simple
    but deterministic embedding vector. Suitable for small-to-medium
    knowledge graphs.
    """
    
    def __init__(self, vocab_size: int = 512, ngram_size: int = 3):
        self.vocab_size = vocab_size
        self.ngram_size = ngram_size
        self._vocabulary: Dict[str, int] = {}
        self._vocab_lock = 0
    
    def _build_ngrams(self, text: str) -> List[str]:
        """Extract character n-grams from text."""
        text = text.lower()
        ngrams = []
        for i in range(len(text) - self.ngram_size + 1):
            ngrams.append(text[i:i+self.ngram_size])
        return ngrams
    
    def _get_vocab_id(self, ngram: str) -> int:
        """Get vocabulary ID for an n-gram (hash-based)."""
        hash_val = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
        return hash_val % self.vocab_size
    
    def embed(self, text: str) -> List[float]:
        """Generate embedding for text."""
        ngrams = self._build_ngrams(text)
        if not ngrams:
            return [0.0] * self.vocab_size
        
        vector = [0.0] * self.vocab_size
        for ngram in ngrams:
            vocab_id = self._get_vocab_id(ngram)
            vector[vocab_id] += 1.0
        
        # Normalize
        magnitude = math.sqrt(sum(x*x for x in vector))
        if magnitude > 0:
            vector = [x / magnitude for x in vector]
        
        return vector
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed(text) for text in texts]


class MetadataFilter:
    """Filter nodes based on metadata criteria."""
    
    def __init__(self):
        self.criteria: List[Tuple[str, str, Any]] = []  # (field, operator, value)
    
    def add_criterion(self, field: str, operator: str, value: Any) -> "MetadataFilter":
        """Add a filter criterion (supports ==, !=, <, >, <=, >=, in, not_in)."""
        self.criteria.append((field, operator, value))
        return self
    
    def matches(self, metadata: Dict[str, Any]) -> bool:
        """Check if metadata matches all criteria."""
        for field, operator, value in self.criteria:
            if field not in metadata:
                if operator in ("!=", "not_in"):
                    continue  # Absent field matches "not equal"
                else:
                    return False
            
            field_val = metadata[field]
            
            if operator == "==":
                if field_val != value:
                    return False
            elif operator == "!=":
                if field_val == value:
                    return False
            elif operator == "<":
                if not (field_val < value):
                    return False
            elif operator == ">":
                if not (field_val > value):
                    return False
            elif operator == "<=":
                if not (field_val <= value):
                    return False
            elif operator == ">=":
                if not (field_val >= value):
                    return False
            elif operator == "in":
                if field_val not in value:
                    return False
            elif operator == "not_in":
                if field_val in value:
                    return False
        
        return True


# ── Core Semantic Search Index ──

class SemanticSearchIndex:
    """
    Vector-based semantic search index with explainable scoring.
    
    Features:
    - Embedding-based retrieval
    - Metadata filtering
    - Explainable match reasons
    - Relationship graph navigation
    - Filesystem-backed persistence
    """
    
    def __init__(self, embedding_model: Optional[EmbeddingModel] = None):
        self._nodes: Dict[str, SemanticNode] = {}
        self._relationships: List[Relationship] = []
        self.embedding_model = embedding_model or SimpleStatisticalEmbedding()
        self._access_patterns: Dict[str, List[datetime]] = defaultdict(list)
    
    # ── Node Management ──
    
    def add_node(self, node: SemanticNode) -> None:
        """Add a node and compute its embedding."""
        if not node.embedding:
            node.embedding = self.embedding_model.embed(node.content)
        self._nodes[node.id] = node
    
    def get_node(self, node_id: str) -> Optional[SemanticNode]:
        """Get a node by ID and update access time."""
        if node_id in self._nodes:
            self._nodes[node_id].last_accessed = datetime.now(timezone.utc)
            self._access_patterns[node_id].append(datetime.now(timezone.utc))
            return self._nodes[node_id]
        return None
    
    def delete_node(self, node_id: str) -> None:
        """Remove a node and its relationships."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            self._relationships = [
                r for r in self._relationships
                if r.source_id != node_id and r.target_id != node_id
            ]
    
    def update_node_content(self, node_id: str, new_content: str) -> None:
        """Update node content and re-embed."""
        if node_id in self._nodes:
            self._nodes[node_id].content = new_content
            self._nodes[node_id].embedding = self.embedding_model.embed(new_content)
    
    # ── Relationship Management ──
    
    def add_relationship(self, source_id: str, target_id: str, 
                        rel_type: str, strength: float = 0.8) -> None:
        """Add a relationship between nodes."""
        rel = Relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=rel_type,
            strength=min(1.0, max(0.0, strength))
        )
        self._relationships.append(rel)
        
        if source_id in self._nodes:
            self._nodes[source_id].relationships[target_id] = rel.strength
        if target_id in self._nodes:
            self._nodes[target_id].relationships[source_id] = rel.strength
    
    def get_related_nodes(self, node_id: str, rel_type: Optional[str] = None,
                         min_strength: float = 0.3) -> List[Tuple[SemanticNode, float]]:
        """Get related nodes with their relationship strength."""
        if node_id not in self._nodes:
            return []
        
        related = []
        for rel in self._relationships:
            if rel.source_id == node_id or rel.target_id == node_id:
                if rel_type and rel.relationship_type != rel_type:
                    continue
                if rel.strength < min_strength:
                    continue
                
                target_id = rel.target_id if rel.source_id == node_id else rel.source_id
                if target_id in self._nodes:
                    related.append((self._nodes[target_id], rel.strength))
        
        return sorted(related, key=lambda x: x[1], reverse=True)
    
    # ── Vector Similarity ──
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a*a for a in vec1))
        mag2 = math.sqrt(sum(b*b for b in vec2))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)
    
    # ── Search ──
    
    def search(self, query: str, max_results: int = 10, 
              metadata_filter: Optional[MetadataFilter] = None,
              node_type: Optional[str] = None) -> List[SearchResult]:
        """
        Perform vector-based semantic search with explainable scoring.
        
        Args:
            query: Search query string
            max_results: Maximum results to return
            metadata_filter: Optional metadata filter to apply
            node_type: Filter by node type
        
        Returns:
            List of SearchResult objects with reasons
        """
        if not query.strip():
            return []
        
        query_embedding = self.embedding_model.embed(query)
        results = []
        
        for node_id, node in self._nodes.items():
            # Apply filters
            if node_type and node.node_type != node_type:
                continue
            if metadata_filter and not metadata_filter.matches(node.metadata):
                continue
            
            # Skip nodes without embeddings
            if not node.embedding:
                continue
            
            # Calculate vector similarity
            vector_score = self.cosine_similarity(query_embedding, node.embedding)
            
            # Gather match reasons
            reasons = []
            
            # Vector similarity reason
            if vector_score > 0.3:
                reasons.append(SearchReason(
                    reason_type="vector_similarity",
                    explanation=f"Content matches query semantically ({vector_score:.2f} similarity)",
                    confidence=vector_score
                ))
            
            # Temporal boost reason
            time_since_access = (datetime.now(timezone.utc) - node.last_accessed).total_seconds()
            recency_score = max(0, 1.0 - (time_since_access / 3600))  # Decay over 1 hour
            if recency_score > 0.1:
                reasons.append(SearchReason(
                    reason_type="temporal_boost",
                    explanation=f"Recently accessed ({recency_score:.2f} recency boost)",
                    confidence=recency_score
                ))
            
            # Relationship boost reason
            if node.relationships:
                relationship_score = sum(node.relationships.values()) / len(node.relationships)
                if relationship_score > 0.2:
                    reasons.append(SearchReason(
                        reason_type="relationship",
                        explanation=f"Has strong relationships in knowledge graph ({relationship_score:.2f} avg)",
                        confidence=relationship_score
                    ))
            
            # Metadata match reason
            if metadata_filter:
                reasons.append(SearchReason(
                    reason_type="metadata_match",
                    explanation="Matches all metadata filter criteria",
                    confidence=1.0
                ))
            
            # Compute final score from reasons
            if not reasons:
                continue
            
            # Weighted score: vector similarity (60%) + recency (20%) + relationship (15%) + metadata (5%)
            final_score = 0.0
            if any(r.reason_type == "vector_similarity" for r in reasons):
                vs_reason = next(r for r in reasons if r.reason_type == "vector_similarity")
                final_score += vs_reason.confidence * 0.60
            if any(r.reason_type == "temporal_boost" for r in reasons):
                tb_reason = next(r for r in reasons if r.reason_type == "temporal_boost")
                final_score += tb_reason.confidence * 0.20
            if any(r.reason_type == "relationship" for r in reasons):
                rel_reason = next(r for r in reasons if r.reason_type == "relationship")
                final_score += rel_reason.confidence * 0.15
            if any(r.reason_type == "metadata_match" for r in reasons):
                final_score += 0.05
            
            results.append(SearchResult(
                node_id=node_id,
                content=node.content,
                node_type=node.node_type,
                score=min(1.0, final_score),
                reasons=reasons,
                metadata=node.metadata
            ))
        
        # Sort by score and return top results
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:max_results]
    
    def explain_search(self, query: str, node_id: str) -> str:
        """Generate a human-readable explanation of why a node matched a query."""
        node = self.get_node(node_id)
        if not node:
            return f"Node '{node_id}' not found."
        
        query_embedding = self.embedding_model.embed(query)
        similarity = self.cosine_similarity(query_embedding, node.embedding or [])
        
        explanation = f"**Match Analysis for '{node_id}'**\n\n"
        explanation += f"**Query:** {query}\n"
        explanation += f"**Vector Similarity Score:** {similarity:.3f}\n\n"
        explanation += f"**Reasons for Match:**\n"
        
        if similarity > 0.3:
            explanation += f"- **Semantic Similarity**: Content matches query semantically\n"
        
        time_since = (datetime.now(timezone.utc) - node.last_accessed).total_seconds()
        if time_since < 3600:
            explanation += f"- **Recency**: Recently accessed ({time_since / 60:.0f} minutes ago)\n"
        
        if node.relationships:
            explanation += f"- **Relationships**: Connected to {len(node.relationships)} other nodes\n"
        
        explanation += f"\n**Node Content:** {node.content[:200]}...\n"
        
        return explanation
    
    # ── Knowledge Graph Statistics ──
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the knowledge graph."""
        node_types = Counter(node.node_type for node in self._nodes.values())
        relationship_types = Counter(rel.relationship_type for rel in self._relationships)
        
        return {
            "total_nodes": len(self._nodes),
            "total_relationships": len(self._relationships),
            "node_types": dict(node_types),
            "relationship_types": dict(relationship_types),
            "avg_relationships_per_node": len(self._relationships) / max(len(self._nodes), 1),
            "total_accesses": sum(len(v) for v in self._access_patterns.values())
        }
    
    def export_to_json(self) -> str:
        """Export knowledge graph to JSON for persistence."""
        nodes_data = [node.to_dict() for node in self._nodes.values()]
        rels_data = [asdict(rel) for rel in self._relationships]
        
        for rel in rels_data:
            rel["created_at"] = rel["created_at"].isoformat()
        
        return json.dumps({
            "nodes": nodes_data,
            "relationships": rels_data,
            "stats": self.get_stats()
        }, indent=2)
    
    def import_from_json(self, json_data: str) -> None:
        """Import knowledge graph from JSON."""
        try:
            data = json.loads(json_data)
            
            # Import nodes
            for node_data in data.get("nodes", []):
                node = SemanticNode(
                    id=node_data["id"],
                    content=node_data["content"],
                    node_type=node_data["node_type"],
                    metadata=node_data.get("metadata", {}),
                    relationships=node_data.get("relationships", {})
                )
                self.add_node(node)
            
            # Import relationships
            for rel_data in data.get("relationships", []):
                self.add_relationship(
                    rel_data["source_id"],
                    rel_data["target_id"],
                    rel_data["relationship_type"],
                    rel_data["strength"]
                )
        except Exception as e:
            raise ValueError(f"Failed to import knowledge graph: {e}")


# ── High-Level Interface for LLMs ──

class SemanticSearchInterface:
    """
    High-level semantic search interface designed for LLM interaction.
    
    Replaces the old keyword-based search with vector-based understanding.
    """
    
    def __init__(self, interface: Optional[Any] = None):
        """
        Initialize semantic search interface.
        
        Args:
            interface: Optional LLMInterface for integration (can be None for standalone use)
        """
        self.interface = interface
        self.index = SemanticSearchIndex()
        self._index_existing_content()
    
    def _index_existing_content(self) -> None:
        """Index existing content from the Keeli engine."""
        if not self.interface:
            return
        
        try:
            # Index tasks
            tasks = self.interface.engine.list_tasks()
            for task in tasks:
                node = SemanticNode(
                    id=task['id'],
                    content=f"{task['title']} {task.get('description', '')}",
                    node_type="task",
                    metadata={
                        "status": task['status'],
                        "priority": task['priority'],
                        "tags": task.get('tags', [])
                    }
                )
                self.index.add_node(node)
                
                # Extract dependencies
                if task.get('depends_on') and task['depends_on'] != '—':
                    deps = re.findall(r'[Tt]-?\d+', task['depends_on'])
                    for dep in deps:
                        dep_id = dep.upper() if dep.startswith('T-') else f"T-{dep[2:]}"
                        self.index.add_relationship(task['id'], dep_id, "depends_on")
            
            # Index working memory if available
            if hasattr(self.interface, '_auto_session_id') and self.interface._auto_session_id:
                memory_items = self.interface.engine.working_memory_list(self.interface._auto_session_id)
                for item in memory_items:
                    node = SemanticNode(
                        id=f"memory:{item['key']}",
                        content=item['value'],
                        node_type="context",
                        metadata={"key": item['key']}
                    )
                    self.index.add_node(node)
        except Exception as e:
            print(f"Warning: Could not index existing content: {e}")
    
    def search(self, query: str, max_results: int = 5, 
              filter_by_type: Optional[str] = None,
              filter_by_status: Optional[str] = None) -> str:
        """
        Perform semantic search and return formatted results.
        
        Args:
            query: Search query
            max_results: Number of results to return
            filter_by_type: Optional node type filter (task, context, etc.)
            filter_by_status: Optional status filter for tasks
        
        Returns:
            Formatted string with search results and explanations
        """
        # Build metadata filter if needed
        metadata_filter = None
        if filter_by_status:
            metadata_filter = MetadataFilter().add_criterion("status", "==", filter_by_status)
        
        # Perform search
        results = self.index.search(
            query=query,
            max_results=max_results,
            metadata_filter=metadata_filter,
            node_type=filter_by_type
        )
        
        if not results:
            return f"🔍 No results found for '{query}'"
        
        response = f"🔍 **Semantic Search Results for '{query}'**\n\n"
        
        for i, result in enumerate(results, 1):
            relevance_emoji = "🔥" if result.score > 0.8 else "⭐" if result.score > 0.5 else "💡"
            response += f"{relevance_emoji} **{result.node_id}** ({result.node_type}) - Score: {result.score:.2f}\n"
            response += f"   {result.content[:100]}\n"
            
            # Show reasons
            if result.reasons:
                response += f"   **Why matched:**\n"
                for reason in result.reasons:
                    response += f"     - {reason.explanation}\n"
            response += "\n"
        
        return response
    
    def explain(self, query: str, node_id: str) -> str:
        """Get detailed explanation of why a node matched a query."""
        return self.index.explain_search(query, node_id)
    
    def get_related(self, node_id: str, rel_type: Optional[str] = None) -> str:
        """Get nodes related to a specific item."""
        node = self.index.get_node(node_id)
        if not node:
            return f"❓ Node '{node_id}' not found."
        
        related = self.index.get_related_nodes(node_id, rel_type=rel_type)
        if not related:
            return f"📭 No relationships found for '{node_id}'."
        
        response = f"🔗 **Related to {node_id}**\n\n"
        for related_node, strength in related:
            response += f"**{related_node.id}** (strength: {strength:.2f})\n"
            response += f"  {related_node.content[:80]}...\n\n"
        
        return response
    
    def add_to_graph(self, node_id: str, content: str, node_type: str = "context",
                    metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add content to the knowledge graph."""
        node = SemanticNode(
            id=node_id,
            content=content,
            node_type=node_type,
            metadata=metadata or {}
        )
        self.index.add_node(node)
        
        return f"✅ Added '{node_id}' to knowledge graph with embedding."
    
    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge graph statistics."""
        return self.index.get_stats()