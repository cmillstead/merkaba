# tests/test_analyzer.py
import pytest
from merkaba.research.analyzer import (
    compute_demand_score,
    compute_competition_score,
    compute_price_metrics,
    compute_opportunity_score,
    generate_recommendation,
    analyze_listings
)


def test_compute_demand_score():
    listings = [
        {"favorites": 100, "estimated_sales": 50},
        {"favorites": 200, "estimated_sales": 100},
    ]
    score = compute_demand_score(listings)
    # avg_favorites = 150, avg_sales = 75
    # favorites_score = (150/1000)*100 = 15
    # sales_score = (75/500)*100 = 15
    # demand_score = 15*0.4 + 15*0.6 = 15
    assert score == pytest.approx(15.0, rel=0.01)


def test_compute_demand_score_empty():
    score = compute_demand_score([])
    assert score == 0


def test_compute_competition_score():
    listings = [{"shop_name": "Shop1"}, {"shop_name": "Shop2"}, {"shop_name": "Shop1"}]
    score = compute_competition_score(listings, total_results=100)
    # competition_score = (100/1000)*100 = 10
    assert score == pytest.approx(10.0, rel=0.01)


def test_compute_price_metrics():
    listings = [
        {"price": 4.99},
        {"price": 9.99},
        {"price": 2.99},
    ]
    metrics = compute_price_metrics(listings)
    assert metrics["price_min"] == 2.99
    assert metrics["price_max"] == 9.99
    assert metrics["avg_price"] == pytest.approx(5.99, rel=0.01)


def test_compute_price_metrics_empty():
    metrics = compute_price_metrics([])
    assert metrics["price_min"] == 0
    assert metrics["price_max"] == 0
    assert metrics["avg_price"] == 0


def test_compute_opportunity_score():
    score = compute_opportunity_score(
        demand_score=80,
        competition_score=30,
        avg_price=5.0
    )
    # competition_opportunity = 100 - 30 = 70
    # price_score = 100 (avg_price $5 is in $3-$10 optimal range)
    # opportunity_score = 80*0.4 + 70*0.4 + 100*0.2 = 32 + 28 + 20 = 80
    assert score == pytest.approx(80.0, rel=0.01)


def test_generate_recommendation_excellent():
    """Test excellent opportunity recommendation (score >= 80)."""
    rec = generate_recommendation(demand_score=90, competition_score=20, opportunity_score=85)
    assert "excellent" in rec.lower()


def test_generate_recommendation_good():
    """Test good opportunity recommendation (60 <= score < 80)."""
    rec = generate_recommendation(demand_score=70, competition_score=40, opportunity_score=65)
    assert "good" in rec.lower()


def test_generate_recommendation_moderate():
    """Test moderate opportunity recommendation (40 <= score < 60)."""
    rec = generate_recommendation(demand_score=50, competition_score=50, opportunity_score=50)
    assert "moderate" in rec.lower()


def test_generate_recommendation_challenging():
    """Test challenging market recommendation (20 <= score < 40)."""
    rec = generate_recommendation(demand_score=20, competition_score=80, opportunity_score=25)
    assert "challenging" in rec.lower()


def test_generate_recommendation_not_recommended():
    """Test not recommended recommendation (score < 20)."""
    rec = generate_recommendation(demand_score=10, competition_score=90, opportunity_score=15)
    assert "not recommended" in rec.lower()


def test_analyze_listings_full():
    listings = [
        {
            "favorites": 150,
            "estimated_sales": 75,
            "shop_name": "Shop1",
            "price": 4.99
        },
        {
            "favorites": 200,
            "estimated_sales": 100,
            "shop_name": "Shop2",
            "price": 6.99
        },
    ]

    result = analyze_listings(listings, total_results=50)

    assert "demand_score" in result
    assert "competition_score" in result
    assert "avg_price" in result
    assert "price_min" in result
    assert "price_max" in result
    assert "opportunity_score" in result
    assert "recommendation" in result
