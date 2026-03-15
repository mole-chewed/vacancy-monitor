from __future__ import annotations

from vacancy_monitor.classifier import classify_vacancy
from vacancy_monitor.models import TrackAssessment, Vacancy


def classify_track(vacancy: Vacancy) -> TrackAssessment:
    return classify_vacancy(vacancy)
