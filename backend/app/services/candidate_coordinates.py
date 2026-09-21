"""Shared read-only validation of stored candidate coordinate pairs."""
import math

def candidate_coordinates(metadata):
    """Read existing coordinate pairs only; never geocode or expose raw metadata."""
    if not isinstance(metadata, dict):
        return None, None
    for record in (metadata, metadata.get('normalized_row')):
        if not isinstance(record, dict):
            continue
        values = [record.get('latitude'), record.get('longitude')]
        if any(isinstance(v, bool) or not isinstance(v, (str, int, float)) for v in values):
            continue
        try:
            lat, lon = map(float, values)
        except (ValueError, TypeError, OverflowError):
            continue
        if math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180:
            return lat, lon
    return None, None
