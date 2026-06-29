from services.news_intelligence import assess_news, deduplicate_stories


def test_news_assessment_deduplicates_and_flags_uncertain_single_source():
    stories = [
        {
            "title": "Unconfirmed BTC hack rumor claims guaranteed 100x crash",
            "source": "telegram",
            "url": "https://example.test/rumor",
        },
        {
            "headline": "Unconfirmed BTC hack rumor claims guaranteed 100x crash",
            "provider": "telegram",
            "url": "https://example.test/rumor",
        },
    ]

    unique = deduplicate_stories(stories)
    assessment = assess_news(stories, {"asset": "BTCUSDT"})

    assert len(unique) == 1
    assert assessment["story_count"] == 1
    assert "BTC" in assessment["affected_assets"]
    assert assessment["fake_news_risk"]["score"] >= 0.7
    assert assessment["signal_action"] == "suppress"


def test_news_assessment_allows_reliable_low_impact_context():
    assessment = assess_news(
        [
            {
                "title": "Reuters: euro trades steady before ECB speakers",
                "source": "reuters",
                "summary": "Markets wait for central bank remarks.",
            }
        ],
        {"asset": "EURUSD"},
    )

    assert assessment["source_reliability"] >= 0.9
    assert "EURUSD" in assessment["affected_assets"]
    assert assessment["signal_action"] in {"allow", "delay"}
