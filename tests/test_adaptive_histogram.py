"""Unit tests for adaptive binning algorithm in corporate dashboard."""

from app.repositories.analytics import (
    _alocar_lote,
    _calcular_percentil,
    _format_cohort_label,
    calcular_passo_amigavel,
    calcular_step_amigavel,
    gerar_histograma_adaptativo,
)


def test_calcular_passo_amigavel():
    assert calcular_passo_amigavel(0) == 5000
    assert calcular_passo_amigavel(-100) == 5000
    # Micro-scales (e.g. 1500 to 7000: amplitude 5500, 5 bins -> raw 1100 -> step 2000)
    assert calcular_passo_amigavel(5500, 5) == 2000
    # Standard scale (11k to 44k: amplitude 33000, 5 bins -> raw 6600 -> step 10000)
    assert calcular_passo_amigavel(33000, 5) == 10000
    # Mega-scale (105k to 235k: amplitude 130000, 5 bins -> raw 26000 -> step 50000)
    assert calcular_passo_amigavel(130000, 5) == 50000
    # Financial million scale (amplitude 3.0M, 6 bins -> raw 500k -> step 500k)
    assert calcular_passo_amigavel(3_000_000, 6) == 500000


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
    assert _format_cohort_label(1_000_000, 2_000_000) == "1.0M-2.0M"


def test_adaptive_histogram_empty():
    assert gerar_histograma_adaptativo([], []) == []


def test_adaptive_histogram_minimal_variation():
    # Lots varying by small amounts (21k to 23k birds)
    curr = [
        {"chickens": 21000, "cost": 100000.0},
        {"chickens": 22500, "cost": 110000.0},
    ]
    prev = [
        {"chickens": 23000, "cost": 95000.0},
    ]
    result = gerar_histograma_adaptativo(curr, prev)
    assert len(result) == 2
    cohort_names = [b["cohort"] for b in result]
    assert cohort_names == ["21k-22k", "22k-23k"]
    # 21k-22k has 21000 (curr=1, cost=100k)
    assert result[0]["current_year_lots"] == 1
    assert result[0]["current_year_cost"] == 100000.0
    # 22k-23k has 22500 (curr=1, cost=110k) and 23000 (prev=1, cost=95k)
    assert result[1]["current_year_lots"] == 1
    assert result[1]["current_year_cost"] == 110000.0
    assert result[1]["previous_year_lots"] == 1
    assert result[1]["previous_year_cost"] == 95000.0


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


def test_adaptive_histogram_micro_producer_operation():
    # Micro-scale operations: 1.500 to 7.000 birds
    curr = [
        {"received_chickens": 1500, "cost": 15000.0},
        {"received_chickens": 3500, "cost": 35000.0},
        {"received_chickens": 6800, "cost": 68000.0},
    ]
    prev = [
        {"received_chickens": 2000, "cost": 20000.0},
        {"received_chickens": 5000, "cost": 50000.0},
    ]
    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)
    # Range: 1500 to 6800 (span 5300) -> step = 2000
    # Does NOT condense into single 0-10k bucket
    assert len(result) >= 3
    for b in result:
        assert b["max_birds"] - b["min_birds"] == 2000


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


def test_adaptive_histogram_ignores_zero_or_null_birds():
    # Lots without chicken count must NOT pollute the histogram
    curr = [
        {"received_chickens": None, "cost": 500000.0},
        {"received_chickens": 0, "cost": 300000.0},
        {"received_chickens": 20000, "cost": 100000.0},
    ]
    prev = [
        {"received_chickens": None, "cost": 400000.0},
        {"received_chickens": 25000, "cost": 120000.0},
    ]
    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)
    assert len(result) >= 1
    # Check that 500k and 300k costs were NOT allocated to any bucket
    total_curr_cost = sum(b["current_year_cost"] for b in result)
    assert total_curr_cost == 100000.0
    total_prev_cost = sum(b["previous_year_cost"] for b in result)
    assert total_prev_cost == 120000.0


def test_adaptive_histogram_continuous_axis_with_valleys():
    # Lots in 10k-20k and 40k-50k; 20k-30k and 30k-40k must be kept with 0 lots/cost
    curr = [
        {"received_chickens": 15000, "cost": 75000.0},
        {"received_chickens": 45000, "cost": 225000.0},
    ]
    prev = [
        {"received_chickens": 12000, "cost": 60000.0},
    ]
    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)
    # Step = 10000
    cohort_names = [b["cohort"] for b in result]
    assert cohort_names == ["10k-20k", "20k-30k", "30k-40k", "40k-50k"]
    # Valleys have 0 lots and 0 cost
    assert result[1]["cohort"] == "20k-30k"
    assert result[1]["current_year_lots"] == 0
    assert result[1]["current_year_cost"] == 0.0
    assert result[2]["cohort"] == "30k-40k"
    assert result[2]["current_year_lots"] == 0
    assert result[2]["current_year_cost"] == 0.0


def test_calcular_percentil():
    assert _calcular_percentil([]) == 0.0
    assert _calcular_percentil([1000]) == 1000.0
    vals = [1000, 2000, 3000, 4000, 5000]
    assert _calcular_percentil(vals, 0.95) == 4000.0
    assert _calcular_percentil(vals, 0.50) == 3000.0
    assert _calcular_percentil(vals, 0.0) == 1000.0


def test_format_cohort_label_open_tail():
    assert _format_cohort_label(0, 10000) == "0-10k"
    assert _format_cohort_label(10000, 20000) == "10k-20k"
    assert _format_cohort_label(8000, None) == "8k+"
    assert _format_cohort_label(10000, None) == "10k+"
    assert _format_cohort_label(0, None) == "0+"
    assert _format_cohort_label(1_000_000, None) == "1.0M+"


def test_alocar_lote_open_and_closed_buckets():
    bucket_closed = {"min_birds": 6000, "max_birds": 8000}
    bucket_open = {"min_birds": 8000, "max_birds": None}

    # Closed bucket
    assert _alocar_lote(bucket_closed, 5999, is_last=False) is False
    assert _alocar_lote(bucket_closed, 6000, is_last=False) is True
    assert _alocar_lote(bucket_closed, 7500, is_last=False) is True
    assert _alocar_lote(bucket_closed, 8000, is_last=False) is False
    # If closed bucket is marked is_last, upper boundary is inclusive
    assert _alocar_lote(bucket_closed, 8000, is_last=True) is True

    # Open tail bucket (max_birds is None)
    assert _alocar_lote(bucket_open, 7999, is_last=True) is False
    assert _alocar_lote(bucket_open, 8000, is_last=True) is True
    assert _alocar_lote(bucket_open, 45000, is_last=True) is True
    # Zero or negative birds must be rejected
    assert _alocar_lote(bucket_open, 0, is_last=True) is False
    assert _alocar_lote(bucket_open, -5, is_last=True) is False


def test_adaptive_histogram_outlier_simulation_real_case():
    # 15 normal lots from 1.200 to 6.800 birds (costs R$ 50k to R$ 200k)
    # 1 outlier lot with 45.000 birds (cost R$ 12.500)
    curr = [
        {"received_chickens": 1500, "cost": 50000.0},
        {"received_chickens": 2200, "cost": 70000.0},
        {"received_chickens": 3100, "cost": 90000.0},
        {"received_chickens": 3900, "cost": 110000.0},
        {"received_chickens": 4800, "cost": 140000.0},
        {"received_chickens": 5500, "cost": 160000.0},
        {"received_chickens": 6200, "cost": 180000.0},
        {"received_chickens": 6800, "cost": 200000.0},
        {"received_chickens": 45000, "cost": 12500.0},  # Outlier
    ]
    prev = [
        {"received_chickens": 1200, "cost": 45000.0},
        {"received_chickens": 1800, "cost": 60000.0},
        {"received_chickens": 2500, "cost": 80000.0},
        {"received_chickens": 3400, "cost": 100000.0},
        {"received_chickens": 4200, "cost": 125000.0},
        {"received_chickens": 5100, "cost": 150000.0},
        {"received_chickens": 6500, "cost": 190000.0},
    ]

    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)

    # 4 regular bins covering 0-2k to 6k-8k, and 1 open bin 8k+
    cohort_names = [b["cohort"] for b in result]
    assert cohort_names == ["0-2k", "2k-4k", "4k-6k", "6k-8k", "8k+"]

    # Normal lots are distributed in the 4 regular bins
    assert result[0]["current_year_lots"] == 1
    assert result[0]["previous_year_lots"] == 2
    assert result[0]["current_year_cost"] == 50000.0
    assert result[0]["previous_year_cost"] == 105000.0

    assert result[1]["current_year_lots"] == 3
    assert result[1]["previous_year_lots"] == 2

    assert result[2]["current_year_lots"] == 2
    assert result[2]["previous_year_lots"] == 2

    assert result[3]["current_year_lots"] == 2
    assert result[3]["previous_year_lots"] == 1

    # Outlier falls in 8k+ with open tail (max_birds is None)
    tail = result[4]
    assert tail["cohort"] == "8k+"
    assert tail["min_birds"] == 8000
    assert tail["max_birds"] is None
    assert tail["current_year_lots"] == 1
    assert tail["current_year_cost"] == 12500.0
    assert tail["previous_year_lots"] == 0
    assert tail["previous_year_cost"] == 0.0

    # Ensure the first bucket does NOT concentrate 100% of data anymore
    total_curr_cost = sum(b["current_year_cost"] for b in result)
    assert result[0]["current_year_cost"] < total_curr_cost * 0.15


def test_adaptive_histogram_homogeneous_no_outliers():
    # Regular lots: 10k, 20k, 30k, 40k, 50k birds
    curr = [
        {"received_chickens": 10000, "cost": 50000.0},
        {"received_chickens": 20000, "cost": 100000.0},
        {"received_chickens": 40000, "cost": 200000.0},
    ]
    prev = [
        {"received_chickens": 30000, "cost": 150000.0},
        {"received_chickens": 50000, "cost": 250000.0},
    ]
    result = gerar_histograma_adaptativo(curr, prev, num_baldes=5)

    cohort_names = [b["cohort"] for b in result]
    # No tail bucket with '+'
    assert all("+" not in name for name in cohort_names)
    assert all(b["max_birds"] is not None for b in result)
    assert cohort_names == ["10k-20k", "20k-30k", "30k-40k", "40k-50k"]
