"""Unit tests for adaptive binning algorithm in corporate dashboard."""

from app.repositories.analytics import (
    _format_cohort_label,
    calcular_step_amigavel,
    gerar_histograma_adaptativo,
)


def test_calcular_step_amigavel():
    assert calcular_step_amigavel(1000) == 2500
    assert calcular_step_amigavel(2500) == 2500
    assert calcular_step_amigavel(3000) == 5000
    assert calcular_step_amigavel(5000) == 5000
    assert calcular_step_amigavel(7000) == 10000
    assert calcular_step_amigavel(10000) == 10000
    assert calcular_step_amigavel(15000) == 20000
    assert calcular_step_amigavel(20000) == 20000
    assert calcular_step_amigavel(23000) == 25000
    assert calcular_step_amigavel(25000) == 25000
    assert calcular_step_amigavel(35000) == 50000
    assert calcular_step_amigavel(50000) == 50000
    # Gigantic scales
    assert calcular_step_amigavel(75000) == 80000
    assert calcular_step_amigavel(120000) == 200000


def test_format_cohort_label():
    assert _format_cohort_label(0, 10000) == "0-10k"
    assert _format_cohort_label(10000, 20000) == "10k-20k"
    assert _format_cohort_label(0, 2500) == "0-2.5k"
    assert _format_cohort_label(2500, 5000) == "2.5k-5k"
    assert _format_cohort_label(50000, 75000) == "50k-75k"


def test_adaptive_histogram_empty():
    assert gerar_histograma_adaptativo([], []) == []


def test_adaptive_histogram_minimal_variation():
    # Lots varying by less than 5000 birds
    curr = [
        {"chickens": 21000, "cost": 100000.0},
        {"chickens": 22500, "cost": 110000.0},
    ]
    prev = [
        {"chickens": 23000, "cost": 95000.0},
    ]
    result = gerar_histograma_adaptativo(curr, prev)
    assert len(result) == 1
    bucket = result[0]
    assert bucket["cohort"] == "20k-30k"
    assert bucket["min_birds"] == 20000
    assert bucket["max_birds"] == 30000
    assert bucket["current_year_cost"] == 210000.0
    assert bucket["current_year_lots"] == 2
    assert bucket["previous_year_cost"] == 95000.0
    assert bucket["previous_year_lots"] == 1


def test_adaptive_histogram_small_producer_distribution():
    # Typical poultry integration: lot sizes 10k to 45k birds
    curr = [
        {"received_chickens": 12000, "cost": 60000.0},
        {"received_chickens": 14000, "cost": 70000.0},
        {"received_chickens": 22000, "cost": 110000.0},
        {"received_chickens": 31000, "cost": 155000.0},
        {"received_chickens": 42000, "cost": 210000.0},
    ]
    prev = [
        {"received_chickens": 11000, "cost": 50000.0},
        {"received_chickens": 24000, "cost": 115000.0},
        {"received_chickens": 33000, "cost": 160000.0},
        {"received_chickens": 44000, "cost": 200000.0},
    ]

    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)
    # Range: 11000 to 44000 (span = 33000)
    # Step = 10000
    # Bins generated: 10k-20k, 20k-30k, 30k-40k, 40k-50k
    assert len(result) == 4
    cohort_names = [b["cohort"] for b in result]
    assert cohort_names == ["10k-20k", "20k-30k", "30k-40k", "40k-50k"]

    # 10k-20k has 12k, 14k (curr=2) and 11k (prev=1)
    b10_20 = result[0]
    assert b10_20["current_year_lots"] == 2
    assert b10_20["current_year_cost"] == 130000.0
    assert b10_20["previous_year_lots"] == 1
    assert b10_20["previous_year_cost"] == 50000.0

    # 40k-50k has 42k (curr=1) and 44k (prev=1)
    b40_50 = result[3]
    assert b40_50["current_year_lots"] == 1
    assert b40_50["current_year_cost"] == 210000.0
    assert b40_50["previous_year_lots"] == 1
    assert b40_50["previous_year_cost"] == 200000.0


def test_adaptive_histogram_large_industrial_operation():
    # Megafarms with lots from 100k to 240k birds
    curr = [
        {"chickens": 110000, "cost": 800000.0},
        {"chickens": 160000, "cost": 1200000.0},
        {"chickens": 235000, "cost": 1800000.0},
    ]
    prev = [
        {"chickens": 105000, "cost": 750000.0},
        {"chickens": 190000, "cost": 1400000.0},
    ]

    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)
    # Range: 105000 to 235000 (span = 130000)
    # step_bruto = 26000 -> step = 50000
    # Bins: 100k-150k, 150k-200k, 200k-250k
    assert len(result) >= 2
    for b in result:
        assert b["previous_year_lots"] > 0 or b["current_year_lots"] > 0
        assert b["min_birds"] >= 100000
