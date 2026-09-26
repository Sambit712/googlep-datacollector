"""Unit tests for V1 Research Taxonomy Configuration Loader."""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from src.config_loader import ConfigError, load_taxonomy, TaxonomyConfig, TaxonomyCategory


def test_load_valid_default_taxonomy():
    """Verify loading the project's config/taxonomy.yaml works and populates all categories."""
    taxonomy = load_taxonomy("config/taxonomy.yaml")
    assert isinstance(taxonomy, TaxonomyConfig)
    assert taxonomy.version == "1.0"
    assert "vague-memory" in taxonomy.description.lower()

    # Relevance criteria and classes
    assert len(taxonomy.relevance_criteria) >= 3
    assert any("visual media" in r.lower() for r in taxonomy.relevance_criteria)
    relevance_classes = taxonomy.get_relevance_class_ids()
    assert "relevant" in relevance_classes
    assert "possibly_relevant" in relevance_classes
    assert "irrelevant" in relevance_classes

    # Memory cues
    cue_ids = taxonomy.get_memory_cue_ids()
    assert "person" in cue_ids
    assert "relationship" in cue_ids
    assert "place_location" in cue_ids
    assert "event_occasion" in cue_ids
    assert "temporal_epoch" in cue_ids
    assert "object" in cue_ids
    assert "visual_details" in cue_ids
    assert "text_in_image" in cue_ids
    assert "activity_action" in cue_ids
    assert "ambient_context" in cue_ids

    # Retrieval failure stages (5-stage cognitive breakdown)
    stage_ids = taxonomy.get_failure_stage_ids()
    assert len(stage_ids) == 5
    assert "memory_to_query" in stage_ids
    assert "query_to_system" in stage_ids
    assert "system_to_candidate" in stage_ids
    assert "candidate_to_recognition" in stage_ids
    assert "search_refinement" in stage_ids
    assert taxonomy.is_valid_failure_stage("memory_to_query")
    assert not taxonomy.is_valid_failure_stage("nonexistent_stage")

    # Failure points
    failure_ids = taxonomy.get_failure_point_ids()
    assert "vocabulary_mismatch" in failure_ids
    assert "temporal_fuzziness" in failure_ids
    assert "missing_metadata" in failure_ids
    assert "visual_semantic_gap" in failure_ids
    assert "screenshot_clutter" in failure_ids
    assert "volume_overload" in failure_ids

    # Target media types
    assert "personal_photo" in taxonomy.target_media_types
    assert "screenshot" in taxonomy.target_media_types
    assert "video_clip" in taxonomy.target_media_types

    # Workarounds
    workaround_ids = taxonomy.get_workaround_ids()
    assert "endless_scrolling" in workaround_ids
    assert "peer_inquiry" in workaround_ids
    assert "abandonment" in workaround_ids

    # Friction types
    assert "time_wasted" in taxonomy.friction_types
    assert "frustration_with_search_tool" in taxonomy.friction_types

    # Groq analysis configuration
    assert taxonomy.groq_analysis.model == "llama-3.3-70b-versatile"
    assert taxonomy.groq_analysis.temperature == 0.1
    assert taxonomy.groq_analysis.max_retries == 3


def test_taxonomy_file_not_found_raises():
    """Verify loading a nonexistent file raises ConfigError."""
    with pytest.raises(ConfigError, match="not found"):
        load_taxonomy("nonexistent/taxonomy_path.yaml")


def test_taxonomy_malformed_yaml_raises(tmp_path: Path):
    """Verify malformed YAML raises ConfigError."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("relevance_criteria: [unclosed list", encoding="utf-8")
    with pytest.raises(ConfigError, match="Malformed YAML"):
        load_taxonomy(bad_yaml)


def test_taxonomy_not_a_mapping_raises(tmp_path: Path):
    """Verify top-level non-mapping raises ConfigError."""
    bad_yaml = tmp_path / "scalar.yaml"
    bad_yaml.write_text("- item1\n- item2", encoding="utf-8")
    with pytest.raises(ConfigError, match="must contain a top-level dictionary/mapping"):
        load_taxonomy(bad_yaml)


def test_missing_relevance_criteria_raises(tmp_path: Path):
    """Verify missing relevance_criteria raises ConfigError."""
    yaml_content = {
        "memory_cues": [{"id": "person", "description": "People"}],
        "retrieval_failure_points": [{"id": "vol", "description": "Overload"}],
        "target_media_types": ["photo"],
        "workaround_types": [{"id": "scroll", "description": "Scrolling"}],
        "friction_types": ["time_wasted"],
    }
    p = tmp_path / "test.yaml"
    p.write_text(yaml.dump(yaml_content), encoding="utf-8")
    with pytest.raises(ConfigError, match="relevance_criteria"):
        load_taxonomy(p)


def test_missing_memory_cues_raises(tmp_path: Path):
    """Verify missing memory_cues raises ConfigError."""
    yaml_content = {
        "relevance_criteria": ["Criteria 1"],
        "retrieval_failure_points": [{"id": "vol", "description": "Overload"}],
        "target_media_types": ["photo"],
        "workaround_types": [{"id": "scroll", "description": "Scrolling"}],
        "friction_types": ["time_wasted"],
    }
    p = tmp_path / "test.yaml"
    p.write_text(yaml.dump(yaml_content), encoding="utf-8")
    with pytest.raises(ConfigError, match="memory_cues"):
        load_taxonomy(p)


def test_duplicate_category_id_raises(tmp_path: Path):
    """Verify duplicate category IDs in a section raise ConfigError."""
    yaml_content = {
        "relevance_criteria": ["Criteria 1"],
        "memory_cues": [
            {"id": "person", "description": "People 1"},
            {"id": "person", "description": "People 2 (duplicate)"},
        ],
        "retrieval_failure_points": [{"id": "vol", "description": "Overload"}],
        "target_media_types": ["photo"],
        "workaround_types": [{"id": "scroll", "description": "Scrolling"}],
        "friction_types": ["time_wasted"],
    }
    p = tmp_path / "test.yaml"
    p.write_text(yaml.dump(yaml_content), encoding="utf-8")
    with pytest.raises(ConfigError, match="Duplicate category id 'person'"):
        load_taxonomy(p)


def test_missing_target_media_types_raises(tmp_path: Path):
    """Verify missing target_media_types raises ConfigError."""
    yaml_content = {
        "relevance_criteria": ["Criteria 1"],
        "memory_cues": [{"id": "person", "description": "People"}],
        "retrieval_failure_points": [{"id": "vol", "description": "Overload"}],
        "target_media_types": [],
        "workaround_types": [{"id": "scroll", "description": "Scrolling"}],
        "friction_types": ["time_wasted"],
    }
    p = tmp_path / "test.yaml"
    p.write_text(yaml.dump(yaml_content), encoding="utf-8")
    with pytest.raises(ConfigError, match="target_media_types"):
        load_taxonomy(p)


def test_taxonomy_helper_methods():
    """Verify helper lookup and validation methods on TaxonomyConfig."""
    taxonomy = load_taxonomy("config/taxonomy.yaml")

    # Positive validations
    assert taxonomy.is_valid_memory_cue("person") is True
    assert taxonomy.is_valid_failure_point("temporal_fuzziness") is True
    assert taxonomy.is_valid_target_media("personal_photo") is True
    assert taxonomy.is_valid_workaround("endless_scrolling") is True
    assert taxonomy.is_valid_friction("time_wasted") is True

    # Negative validations
    assert taxonomy.is_valid_memory_cue("nonexistent_cue") is False
    assert taxonomy.is_valid_failure_point("fake_failure") is False
    assert taxonomy.is_valid_target_media("hologram") is False
    assert taxonomy.is_valid_workaround("magic") is False
    assert taxonomy.is_valid_friction("ecstasy") is False

    # Description getters
    assert "face" in taxonomy.get_cue_description("person").lower()
    assert taxonomy.get_cue_description("nonexistent") is None
    assert "timeline" in taxonomy.get_failure_description("temporal_fuzziness").lower()
    assert taxonomy.get_failure_description("nonexistent") is None
    assert "timeline" in taxonomy.get_workaround_description("endless_scrolling").lower()
    assert taxonomy.get_workaround_description("nonexistent") is None


def test_taxonomy_supports_flat_list_and_nested_dict(tmp_path: Path):
    """Verify both list and {categories: [...]} structures are parsed identically."""
    yaml_nested = {
        "relevance_criteria": ["Criteria 1"],
        "memory_cues": {"categories": [{"id": "c1", "description": "Desc 1"}]},
        "retrieval_failure_points": [{"id": "f1", "description": "Desc f1"}],
        "target_media_types": ["photo"],
        "workaround_types": {"categories": [{"id": "w1", "description": "Desc w1"}]},
        "friction_types": ["frict1"],
    }
    p = tmp_path / "nested.yaml"
    p.write_text(yaml.dump(yaml_nested), encoding="utf-8")
    cfg = load_taxonomy(p)
    assert cfg.get_memory_cue_ids() == ["c1"]
    assert cfg.get_workaround_ids() == ["w1"]
