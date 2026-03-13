from __future__ import annotations

from hh_monitor.classifier import classify_vacancy
from hh_monitor.models import TrackAssessment, Vacancy


def classify_track(vacancy: Vacancy) -> TrackAssessment:
    return classify_vacancy(vacancy)
