from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enrichment import GridRetailTerritory, ProjectEnrichmentSnapshot
from app.models.project import Project
from app.schemas.enrichment import ProjectEnrichmentResponse


class EnrichmentService:
    def __init__(self, db: Session):
        self.db = db

    def load_hifld_retail_territories(self, feature_collection: dict) -> int:
        features = feature_collection.get("features", []) if isinstance(feature_collection, dict) else []
        loaded_count = 0
        for feature in features:
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry")
            properties = feature.get("properties") or {}
            if not isinstance(geometry, dict) or not isinstance(properties, dict):
                continue
            utility_name = _extract_utility_name(properties)
            if utility_name is None:
                continue
            self.db.add(
                GridRetailTerritory(
                    utility_name=utility_name,
                    source="HIFLD",
                    source_feature_id=_extract_source_feature_id(properties),
                    geometry_json=geometry,
                )
            )
            loaded_count += 1
        self.db.commit()
        return loaded_count

    def enrich_project(self, project_id: uuid.UUID) -> ProjectEnrichmentResponse:
        project = self.db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if project.latitude is None or project.longitude is None:
            snapshot = self._create_snapshot(project_id, utility_name=None, confidence=None)
            return self._to_response(snapshot)

        utility_name = self._find_containing_retail_territory(project.longitude, project.latitude)
        snapshot = self._create_snapshot(
            project_id,
            utility_name=utility_name,
            confidence="medium" if utility_name else None,
        )
        return self._to_response(snapshot)

    def _find_containing_retail_territory(self, longitude: float, latitude: float) -> str | None:
        territories = self.db.execute(select(GridRetailTerritory)).scalars().all()
        for territory in territories:
            if _geometry_contains_point(territory.geometry_json, longitude, latitude):
                return territory.utility_name
        return None

    def _create_snapshot(
        self,
        project_id: uuid.UUID,
        *,
        utility_name: str | None,
        confidence: str | None,
    ) -> ProjectEnrichmentSnapshot:
        snapshot = ProjectEnrichmentSnapshot(
            project_id=project_id,
            retail_utility_name=utility_name,
            confidence=confidence,
            source="HIFLD",
        )
        self.db.add(snapshot)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def _to_response(self, snapshot: ProjectEnrichmentSnapshot) -> ProjectEnrichmentResponse:
        return ProjectEnrichmentResponse(
            utility=snapshot.retail_utility_name,
            confidence=snapshot.confidence,
            source=snapshot.source or "HIFLD",
        )


def _geometry_contains_point(geometry: dict | list | None, longitude: float, latitude: float) -> bool:
    if not isinstance(geometry, dict):
        return False

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return _polygon_contains_point(coordinates, longitude, latitude)
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return any(_polygon_contains_point(polygon, longitude, latitude) for polygon in coordinates)
    return False


def _extract_utility_name(properties: dict) -> str | None:
    for key in ["utility_name", "UTILITY_NAME", "Utility_Name", "name", "NAME", "utility", "UTILITY"]:
        value = properties.get(key)
        if value:
            return str(value)
    return None


def _extract_source_feature_id(properties: dict) -> str | None:
    for key in ["OBJECTID", "objectid", "FID", "fid", "ID", "id"]:
        value = properties.get(key)
        if value is not None:
            return str(value)
    return None


def _polygon_contains_point(polygon: list, longitude: float, latitude: float) -> bool:
    if not polygon:
        return False
    outer_ring = polygon[0]
    if not _ring_contains_point(outer_ring, longitude, latitude):
        return False
    holes = polygon[1:]
    return not any(_ring_contains_point(hole, longitude, latitude) for hole in holes)


def _ring_contains_point(ring: list, longitude: float, latitude: float) -> bool:
    if len(ring) < 4:
        return False

    inside = False
    previous = ring[-1]
    for current in ring:
        if not _valid_coordinate_pair(previous) or not _valid_coordinate_pair(current):
            previous = current
            continue

        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if _point_on_segment(longitude, latitude, x1, y1, x2, y2):
            return True
        if (y1 > latitude) != (y2 > latitude):
            crossing_x = ((x2 - x1) * (latitude - y1) / (y2 - y1)) + x1
            if longitude < crossing_x:
                inside = not inside
        previous = current
    return inside


def _valid_coordinate_pair(value: object) -> bool:
    return isinstance(value, list | tuple) and len(value) >= 2


def _point_on_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
    if abs(cross) > 1e-9:
        return False
    within_x = min(x1, x2) - 1e-9 <= px <= max(x1, x2) + 1e-9
    within_y = min(y1, y2) - 1e-9 <= py <= max(y1, y2) + 1e-9
    return within_x and within_y
