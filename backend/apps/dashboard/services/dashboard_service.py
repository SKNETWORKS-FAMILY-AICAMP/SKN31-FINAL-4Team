def get_dashboard_context():
    return {
        "stats": {
            "collected_today": 12480,
            "success_rate": 96.8,
            "normalize_pending": 1245,
            "term_candidates": 37,
        },
        "sources": [
            {"name": "Musinsa", "status": "healthy", "count": 8421},
            {"name": "Zigzag", "status": "healthy", "count": 3012},
            {"name": "YouTube", "status": "warning", "count": 1047},
        ],
        "pipeline": [
            {"name": "Collection", "count": 12480, "status": "success"},
            {"name": "Raw / S3", "count": 12421, "status": "success"},
            {"name": "Normalize", "count": 11973, "status": "success"},
            {"name": "Term Match", "count": 10842, "status": "success"},
            {"name": "Trend Metric", "count": 10611, "status": "running"},
        ],
        "recent_errors": [
            {"time": "10:02", "source": "Musinsa", "message": "Target 62 request timeout"},
            {"time": "09:51", "source": "YouTube", "message": "API quota warning"},
            {"time": "09:36", "source": "Normalizer", "message": "3 unresolved category aliases"},
        ],
    }
