from navigator import dominates, navigate, pareto_frontier


def _routes():
    return [
        {
            "compiler": "minterm",
            "dense_parameter_count": 100,
            "dense_multiply_slots": 40,
            "hidden_relu_units": 6,
            "depth": 4,
        },
        {
            "compiler": "direct_dag",
            "dense_parameter_count": 90,
            "dense_multiply_slots": 50,
            "hidden_relu_units": 4,
            "depth": 3,
        },
        {
            "compiler": "live_dag",
            "dense_parameter_count": 120,
            "dense_multiply_slots": 60,
            "hidden_relu_units": 7,
            "depth": 5,
        },
    ]


def test_pareto_frontier_preserves_incomparable_storage_and_compute_routes():
    frontier = pareto_frontier(_routes())
    assert [route["compiler"] for route in frontier] == ["minterm", "direct_dag"]
    assert dominates(_routes()[0], _routes()[2])
    assert dominates(_routes()[1], _routes()[2])
    assert not dominates(_routes()[0], _routes()[1])
    assert not dominates(_routes()[1], _routes()[0])


def test_independent_objectives_choose_different_routes_without_weighted_score():
    candidates = _routes()
    storage = navigate(candidates, objective="storage")
    compute = navigate(candidates, objective="dense_compute")
    assert storage["selected_routes"] == ["direct_dag"]
    assert compute["selected_routes"] == ["minterm"]
    assert storage["aggregation"] == "none; hard constraints plus explicit independent objective"


def test_hard_resource_budgets_filter_before_pareto_navigation():
    result = navigate(
        _routes(),
        objective="pareto",
        max_dense_parameter_slots=95,
        max_dense_multiply_slots=55,
    )
    assert result["feasible_routes"] == ["direct_dag"]
    assert result["selected_routes"] == ["direct_dag"]


def test_infeasible_budget_returns_no_route_instead_of_relaxing_constraints():
    result = navigate(
        _routes(),
        objective="storage",
        max_dense_parameter_slots=80,
    )
    assert result["status"] == "infeasible"
    assert result["feasible_routes"] == []
    assert result["selected_routes"] == []


def test_single_objective_preserves_exact_ties():
    candidates = [
        {
            "compiler": "route_a",
            "dense_parameter_count": 20,
            "dense_multiply_slots": 30,
            "hidden_relu_units": 4,
            "depth": 2,
        },
        {
            "compiler": "route_b",
            "dense_parameter_count": 20,
            "dense_multiply_slots": 30,
            "hidden_relu_units": 4,
            "depth": 2,
        },
    ]
    assert navigate(candidates, objective="storage")["selected_routes"] == [
        "route_a",
        "route_b",
    ]


def test_unknown_objective_and_invalid_budgets_are_rejected():
    try:
        navigate(_routes(), objective="combined-score")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown objective was accepted")

    try:
        navigate(_routes(), max_dense_parameter_slots=-1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative budget was accepted")
